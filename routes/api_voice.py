"""routes.api_voice — voices, speak/listen, transcribe, stop-speak."""
from routes._common import (
    ValidationError,
    VoiceError,
    all_voices,
    bp,
    current_voice,
    get_store,
    jsonify,
    listen_until_silence,
    log,
    request,
    set_voice_impl,
    speak_async,
)


# ---------- VOICES ----------
@bp.get("/voices")
def voices_list():
    try:
        return jsonify({"voices": all_voices(),
                        "active": current_voice()["key"]})
    except VoiceError:
        return jsonify({"voices": [], "active": "none",
                        "unavailable": True})


@bp.post("/voice")
def voice_set():
    d = request.get_json(silent=True) or {}
    key = (d.get("key") or "").strip()
    if not key:
        raise ValidationError("Missing 'key'.")
    v = set_voice_impl(key)
    if not v:
        raise ValidationError(f"Unknown voice: {key}")
    speak_async(f"Hello, I am {v['label']}. This is my voice.")
    return jsonify({"ok": True, "voice": current_voice()})


# ---------- VOICE ROUTES ----------
@bp.post("/speak")
def speak_route():
    d = request.get_json(silent=True) or {}
    text = (d.get("text") or "").strip()
    if not text:
        raise ValidationError("Empty text.")
    speak_async(text)
    return jsonify({"ok": True})


def _listen_hint() -> str:
    """Actionable reason for an empty /api/listen result.

    STT runs on Groq, so a missing key and a silent/muted mic look the
    same from the outside — say which one it most likely is.
    """
    try:
        from config import get_settings
        if not get_settings().groq_api_key:
            return ("Voice input needs GROQ_API_KEY — speech-to-text runs "
                    "on Groq. Add it to .env and restart JARVIS.")
    except Exception:
        pass
    return ("Heard nothing — make sure the mic is not muted, that Windows "
            "microphone access is allowed, then check logs/jarvis.log.")


@bp.post("/listen")
def listen_route():
    try:
        text = listen_until_silence(verbose=False)
    except Exception as exc:
        log.exception("Listen failed")
        return jsonify({"error": str(exc), "hint": "Check logs/jarvis.log"}), 500
    if text is None:
        return jsonify({"text": "", "empty": True, "hint": _listen_hint()})
    return jsonify({"text": text, "empty": not bool(text)})


@bp.post("/clear")
def clear():
    d = request.get_json(silent=True) or {}
    sid = d.get("session")
    if not sid:
        raise ValidationError("Missing session.")
    return jsonify({"ok": True, "cleared": get_store().clear(sid)})


# ---------- TRANSCRIBE ----------
@bp.post("/transcribe")
def transcribe_route():
    if "audio" not in request.files:
        raise ValidationError("Missing 'audio' file.")
    f = request.files["audio"]
    data = f.read()
    if not data:
        raise ValidationError("Empty audio.")
    from voice import transcribe_audio_bytes
    suffix = "." + (f.filename or "x.webm").rsplit(".", 1)[-1]
    text = transcribe_audio_bytes(data, suffix=suffix)
    return jsonify({"text": text or "", "empty": not bool(text)})


# ---------- STOP SPEAK ----------
@bp.post("/stop-speak")
def stop_speak_route():
    try:
        from voice import stop_speaking
        stop_speaking()
    except Exception:
        pass
    return jsonify({"ok": True})


