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
