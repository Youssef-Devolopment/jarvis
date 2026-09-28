"""Piper TTS — local, fast, high-quality British voice."""
from __future__ import annotations
import wave
from pathlib import Path
from threading import Lock
from typing import Optional

from logger import get_logger

log = get_logger(__name__)

_VOICES_DIR = Path(__file__).resolve().parent.parent / "voices"
_VOICES_DIR.mkdir(exist_ok=True)

# Model file names (must match files in voices/ folder)
PIPER_VOICES = {
    "alan":   {"model": "en_GB-alan-medium.onnx",
               "label": "Alan", "rate": 1.0},
    "alba":   {"model": "en_GB-alba-medium.onnx",
               "label": "Alba", "rate": 1.0},
    "northern": {"model": "en_GB-northern_english_male-medium.onnx",
                 "label": "Northern", "rate": 1.0},
}

DEFAULT_VOICE = "alan"

_voice_cache = {}
_lock = Lock()
_piper_available = None


def _check_piper() -> bool:
    """Check if piper-tts is installed."""
    global _piper_available
    if _piper_available is not None:
        return _piper_available
    try:
        from piper.voice import PiperVoice  # noqa: F401
        _piper_available = True
    except ImportError:
        try:
            from piper import PiperVoice  # noqa: F401
            _piper_available = True
        except ImportError:
            _piper_available = False
            log.warning("piper-tts not installed. Run: pip install piper-tts")
    return _piper_available


def _load_voice(key: str):
    """Lazy-load a voice model."""
    if not _check_piper():
        return None
    if key in _voice_cache:
        return _voice_cache[key]

    with _lock:
        if key in _voice_cache:
            return _voice_cache[key]
        spec = PIPER_VOICES.get(key)
        if not spec:
            return None
        model_path = _VOICES_DIR / spec["model"]
        if not model_path.exists():
            log.warning("Piper model missing: %s", model_path)
            return None
        try:
            try:
                from piper.voice import PiperVoice
            except ImportError:
                from piper import PiperVoice
            log.info("Loading Piper voice: %s", key)
            voice = PiperVoice.load(str(model_path))
            _voice_cache[key] = voice
            return voice
        except Exception as exc:
            log.exception("Failed to load Piper voice '%s': %s", key, exc)
            return None


def available() -> bool:
    """Is Piper ready with at least one working voice?"""
    if not _check_piper():
        return False
    return _load_voice(DEFAULT_VOICE) is not None


def synthesize(text: str, out_path: Path, voice_key: str = DEFAULT_VOICE) -> bool:
    """Synthesize text to a WAV file. Returns True on success."""
    voice = _load_voice(voice_key)
    if voice is None:
        return False
    try:
        rate = getattr(getattr(voice, "config", None), "sample_rate", 22050) or 22050
        with wave.open(str(out_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(rate)
            if hasattr(voice, "synthesize_wav"):
                voice.synthesize_wav(text, wav_file)
            else:  # older piper-tts API
                voice.synthesize(text, wav_file)
        return out_path.exists() and out_path.stat().st_size > 0
    except Exception as exc:
        log.exception("Piper synthesize failed: %s", exc)
        return False


def list_voices() -> list[dict]:
    """List voices that have their model files present."""
    out = []
    for key, spec in PIPER_VOICES.items():
        path = _VOICES_DIR / spec["model"]
        out.append({
            "key": key,
            "label": spec["label"],
            "ready": path.exists(),
        })
    return out
