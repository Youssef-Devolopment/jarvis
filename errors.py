from __future__ import annotations
import traceback
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException
from logger import get_logger

log = get_logger(__name__)


class JarvisError(Exception):
    status_code = 500
    public_message = "Internal system error."
    def __init__(self, message: str = "", *, detail: str = ""):
        super().__init__(message or self.public_message)
        self.detail = detail


class ConfigError(JarvisError):
    status_code = 500
    public_message = "Server is misconfigured."


class AIError(JarvisError):
    status_code = 502
    public_message = "AI backend is unreachable."


class ValidationError(JarvisError):
    status_code = 400
    public_message = "Invalid request."


class VoiceError(JarvisError):
    status_code = 500
    public_message = "Voice processing failed."


class BrowserError(JarvisError):
    status_code = 500
    public_message = "Browser operation failed."


class SkillError(JarvisError):
    status_code = 500
    public_message = "A skill failed to execute."


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(JarvisError)
    def _handle_jarvis(err):
        log.error("JarvisError on %s %s -> %s | detail=%s",
                  request.method, request.path, err, err.detail)
        return jsonify({"error": err.public_message, "detail": err.detail,
                        "type": err.__class__.__name__}), err.status_code

    @app.errorhandler(HTTPException)
    def _handle_http(err):
        log.warning("HTTP %s on %s %s", err.code, request.method, request.path)
        return jsonify({"error": err.name, "detail": err.description}), err.code

    @app.errorhandler(Exception)
    def _handle_uncaught(err):
        tb = traceback.format_exc()
        log.critical("Uncaught on %s %s\n%s", request.method, request.path, tb)
        return jsonify({"error": "Unhandled exception.", "detail": str(err),
                        "where": _first_app_frame(tb)}), 500


def _first_app_frame(tb: str) -> str:
    for line in tb.strip().splitlines()[::-1]:
        if "site-packages" in line or "/lib/python" in line:
            continue
        s = line.strip()
        if s.startswith("File "):
            return s
    return "unknown"
