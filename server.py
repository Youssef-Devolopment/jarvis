from __future__ import annotations
import time
from flask import Flask, g, request
from config import get_settings, Settings, ensure_flask_secret
from errors import register_error_handlers, ConfigError
from logger import get_logger, setup_logging
from routes import api_bp, views_bp

log = get_logger(__name__)

# Requests slower than this get a WARNING line (tests patch this down).
SLOW_REQUEST_S = 2.0

# Post-boot health glance (entry points schedule it; tests call the
# function directly with delay=0).
HEALTH_LOG_DELAY_S = 20.0


def _log_health_summary(delay: float = HEALTH_LOG_DELAY_S) -> None:
    """One line of health truth in the log shortly after boot.

    Waits for `delay` seconds so async services (MCP, voice warmup)
    have landed, then logs overall + degraded check names + config
    warning count. Never raises.
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
            line += " — degraded: " + ", ".join(bad)
        svc = checks.get("services") or {}
        if svc.get("status") == "degraded":
            line += " — " + str(svc.get("detail") or "boot services degraded")
        warns = (checks.get("config") or {}).get("warnings") or []
        if warns:
            line += f" — {len(warns)} config warning(s)"
        pending = sorted(
            k for k, v in ((checks.get("services") or {}).get("items")
                           or {}).items()
            if (v or {}).get("detail") == "starting")
        if pending:
            line += " — still starting: " + ", ".join(pending)
        if overall == "ok" and not warns:
            log.info(line)
        else:
            log.warning(line)
    except Exception as exc:
        log.debug("Health summary skipped: %s", exc)


def schedule_health_log() -> None:
    """Fire _log_health_summary once on a daemon thread (never blocks)."""
    import threading
    threading.Thread(target=_log_health_summary, name="health-log",
                     daemon=True).start()


def create_app() -> Flask:
    try:
        s = get_settings()
    except ConfigError:
        s = Settings.load(require_key=False)
        log.warning("No API key — skills-only mode. Local skills work; "
                    "LLM chat needs DEEPSEEK_API_KEY in .env.")
    setup_logging(s.log_level)
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["SECRET_KEY"] = ensure_flask_secret()
    if s.host not in ("127.0.0.1", "localhost", "::1"):
        log.warning("Listening on %s — the API has no auth. "
                    "Prefer 127.0.0.1 unless you know what you are doing.",
                    s.host)
    register_error_handlers(app)
    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp)
    app.config["NO_KEY_MODE"] = not s.has_key

    @app.before_request
    def _req_started():
        g._req_t0 = time.time()

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

    try:  # static config-drift audit — warnings only, never blocks boot
        from config import audit_settings
        warns = audit_settings(s)
        for w in warns:
            log.warning("Config audit: %s", w)
        if warns:
            log.warning("Config audit: %d warning(s) — full list in "
                        "Settings > SYSTEM.", len(warns))
    except Exception as exc:
        log.debug("Config audit skipped: %s", exc)
    log.info("App created (skills-only: %s).", app.config["NO_KEY_MODE"])
    return app


app = create_app()
