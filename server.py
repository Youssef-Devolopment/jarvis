from __future__ import annotations

import gzip
import hmac
import os
import time

from flask import Flask, g, jsonify, request

from config import Settings, ensure_flask_secret, get_settings
from errors import ConfigError, register_error_handlers
from logger import get_logger, setup_logging
from routes import api_bp, views_bp

log = get_logger(__name__)

# Requests slower than this get a WARNING line (tests patch this down).
SLOW_REQUEST_S = 2.0

_LOOPBACK = ("127.0.0.1", "::1")
_LAN_GUARDED_METHODS = ("POST", "PUT", "DELETE", "PATCH")


def _lan_guard():
    """Token gate for off-machine writers. Localhost always passes;
    reads always pass; anything else needs X-Jarvis-Token matching
    the JARVIS_TOKEN env value. Fail-closed. Never raises."""
    try:
        if request.method not in _LAN_GUARDED_METHODS:
            return None
        if not (request.path or "").startswith("/api"):
            return None
        remote = request.remote_addr or ""
        if remote in _LOOPBACK:
            return None
        want = os.getenv("JARVIS_TOKEN", "")
        got = request.headers.get("X-Jarvis-Token", "")
        if want and got and hmac.compare_digest(got.encode("utf-8"),
                                                want.encode("utf-8")):
            return None
        log.warning("Blocked LAN %s %s from %s (no valid token)",
                    request.method, request.path, remote)
        if not want:
            return jsonify({
                "error": "LAN API access needs JARVIS_TOKEN set in .env; "
                         "localhost is always allowed.",
                "detail": "Set JARVIS_TOKEN and retry with the "
                          "X-Jarvis-Token header.",
                "type": "AuthError"}), 403
        return jsonify({
            "error": "Invalid API token.",
            "detail": "Retry with the X-Jarvis-Token header matching "
                      "JARVIS_TOKEN.",
            "type": "AuthError"}), 401
    except Exception as exc:
        log.warning("LAN guard failed closed: %s", exc)
        return jsonify({"error": "Request refused.",
                        "detail": "Auth check unavailable.",
                        "type": "AuthError"}), 403

# Post-boot health glance (entry points schedule it; tests call the
# function directly with delay=0).
HEALTH_LOG_DELAY_S = 20.0


def _log_health_summary(delay: float = HEALTH_LOG_DELAY_S,
                        on_summary=None) -> None:
    """One line of health truth in the log shortly after boot.

    Waits for `delay` seconds so async services (MCP, voice warmup)
    have landed, then logs overall + degraded check names + config
    warning count. `on_summary` (optional) receives the same snapshot
    afterwards so console/toast verdicts derive from ONE source â€”
    failures there are logged, never raised.
    """
    try:
        if delay:
            time.sleep(delay)
        from system import health as _health
        snap = _health.snapshot()
        checks = snap.get("checks") or {}
        overall = snap.get("overall") or "unknown"
        line = f"Health after boot: {overall}"
        bad = sorted(k for k, v in checks.items()
                     if isinstance(v, dict) and v.get("status") == "degraded"
                     and k != "services")
        if bad:
            line += " â€” degraded: " + ", ".join(bad)
        svc = checks.get("services") or {}
        if svc.get("status") == "degraded":
            line += " â€” " + str(svc.get("detail") or "boot services degraded")
        warns = (checks.get("config") or {}).get("warnings") or []
        if warns:
            line += f" â€” {len(warns)} config warning(s)"
        pending = sorted(
            k for k, v in ((checks.get("services") or {}).get("items")
                           or {}).items()
            if (v or {}).get("detail") == "starting")
        if pending:
            line += " â€” still starting: " + ", ".join(pending)
        if overall == "ok" and not warns:
            log.info(line)
        else:
            log.warning(line)
        if on_summary is not None:
            try:
                on_summary(snap)
            except Exception as cb_exc:
                log.debug("on_summary callback failed: %s", cb_exc)
    except Exception as exc:
        log.debug("Health summary skipped: %s", exc)


def schedule_health_log(on_summary=None) -> None:
    """Fire _log_health_summary once on a daemon thread (never blocks)."""
    import threading
    threading.Thread(target=_log_health_summary,
                     kwargs={"on_summary": on_summary},
                     name="health-log", daemon=True).start()


# ---------- response optimisation -----------------------------------------
# Measured on a live boot: 212,237 bytes of HTML+CSS+JS went over the wire
# uncompressed (gzip: 48,948 â€” 76.9% smaller), and static carried
# Cache-Control: no-cache so the browser revalidated every asset on every
# load. Both are fixed here, in one place, without a dependency.
_COMPRESSIBLE = ("text/html", "text/css", "text/javascript",
                 "application/javascript", "application/json",
                 "text/plain", "image/svg+xml", "application/xml")
_COMPRESS_MIN = 512  # below this the gzip header costs more than it saves


def _gzip_response(resp) -> None:
    """Gzip a finished response in place. Never raises.

    Three shapes have to be told apart here, and getting it wrong either
    breaks streaming or silently drops the biggest win (app.js is 134KB):

    * SSE replies -- flushed as they are produced, so buffering one would
      hold every event until the stream ended. Left completely alone.
    * Other live streams -- also left alone, defensively.
    * Static files -- Werkzeug reports these as streamed too, but they
      arrive as a *file wrapper* (direct_passthrough), which is finite and
      safe to read whole. That flag also blocks get_data(), so it is
      cleared immediately before the read: we are replacing the wrapper
      with bytes anyway.
    """
    try:
        ctype = ((resp.headers.get("Content-Type") or "")
                 .split(";")[0].strip().lower())
        if ctype == "text/event-stream":
            return
        if resp.is_streamed and not resp.direct_passthrough:
            return
        if resp.headers.get("Content-Encoding"):
            return
        if "gzip" not in request.headers.get("Accept-Encoding", "").lower():
            return
        if not ctype.startswith(_COMPRESSIBLE):
            return  # binary payloads are not worth it
        resp.direct_passthrough = False
        data = resp.get_data()
        if len(data) < _COMPRESS_MIN:
            return  # the gzip header would cost more than it saves
        resp.set_data(gzip.compress(data, 6))
        resp.headers["Content-Encoding"] = "gzip"
        resp.headers["Vary"] = "Accept-Encoding"
    except Exception as exc:  # never break a response over a speedup
        log.debug("gzip skipped: %s", exc)


def _cache_static(resp) -> None:
    """Long-cache versioned static assets. Never raises.

    Every static link in index.html already carries ?v=<config.VERSION>,
    which is the cache-buster â€” so the browser can keep the copy and skip
    the revalidation round trip entirely.
    """
    try:
        if not request.path.startswith("/static/"):
            return
        if "v" not in request.args:
            return
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    except Exception as exc:
        log.debug("cache header skipped: %s", exc)


def create_app() -> Flask:
    try:
        s = get_settings()
    except ConfigError:
        s = Settings.load(require_key=False)
        log.warning("No API key â€” skills-only mode. Local skills work; "
                    "LLM chat needs DEEPSEEK_API_KEY in .env.")
    setup_logging(s.log_level)
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["SECRET_KEY"] = ensure_flask_secret()
    if s.host not in ("127.0.0.1", "localhost", "::1"):
        log.warning("Listening on %s â€” mutating API calls from off-machine "
                    "clients need the X-Jarvis-Token header matching "
                    "JARVIS_TOKEN in .env. Prefer 127.0.0.1 unless you know "
                    "what you are doing.", s.host)
    register_error_handlers(app)
    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp)
    app.config["NO_KEY_MODE"] = not s.has_key

    @app.before_request
    def _req_started():
        g._req_t0 = time.time()
        return _lan_guard()

    @app.after_request
    def _req_slow(resp):
        try:
            dt = time.time() - g._req_t0
        except Exception:
            return resp
        if dt >= SLOW_REQUEST_S:
            log.warning("Slow request: %s %s took %.2fs",
                        request.method, request.path, dt)
        return resp

    @app.after_request
    def _req_optimise(resp):
        """Shrink it, then let it be cached â€” see the notes on each."""
        _gzip_response(resp)
        _cache_static(resp)
        return resp

    try:  # static config-drift audit â€” warnings only, never blocks boot
        from config import audit_settings
        warns = audit_settings(s)
        for w in warns:
            log.warning("Config audit: %s", w)
        if warns:
            log.warning("Config audit: %d warning(s) â€” full list in "
                        "Settings > SYSTEM.", len(warns))
    except Exception as exc:
        log.debug("Config audit skipped: %s", exc)
    log.info("App created (skills-only: %s).", app.config["NO_KEY_MODE"])
    return app


app = create_app()
