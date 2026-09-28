"""Voice output — Piper (primary) with edge-tts fallback."""
from __future__ import annotations
import asyncio
import hashlib
import os
import re
import threading
import time
from pathlib import Path

import pygame

from config import get_settings
from logger import get_logger
from voice.voices import get_voice as get_edge_voice, VOICES as EDGE_VOICES

log = get_logger(__name__)
_settings = get_settings()

_CACHE_DIR = Path(__file__).resolve().parent.parent / ".voice_cache"
_CACHE_DIR.mkdir(exist_ok=True)

_lock = threading.Lock()
_init_done = False
_is_speaking = threading.Event()

# Active engine: "piper" or "edge" (VOICE_ENGINE env, default edge = Ryan)
_engine = "piper" if os.getenv("VOICE_ENGINE", "edge").lower() == "piper" else "edge"

# Current edge voice (used only if Piper fails)
_edge_key = "oliver"
for k, v in EDGE_VOICES.items():
    if v["id"] == _settings.voice_name:
        _edge_key = k
        break

_edge_voice = {
    "key":    _edge_key,
    "name":   _settings.voice_name,
    "rate":   _settings.voice_rate,
    "pitch":  _settings.voice_pitch,
    "volume": _settings.voice_volume,
}


def _init_mixer():
    global _init_done
    if not _init_done:
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=256)
        _init_done = True


def _try_piper():
    global _engine
    if os.getenv("VOICE_ENGINE", "edge").lower() != "piper":
        _engine = "edge"
        log.info("Voice engine: edge-tts (VOICE_ENGINE=%s)",
                 os.getenv("VOICE_ENGINE", "edge"))
        return False
    from voice.piper_engine import available
    if available():
        _engine = "piper"
        log.info("Voice engine: Piper (local)")
        return True
    _engine = "edge"
    log.info("Voice engine: edge-tts (fallback)")
    return False


def apply_mood_voice(rate=None, pitch=None):
    if rate:  _edge_voice["rate"]  = rate
    if pitch: _edge_voice["pitch"] = pitch


def set_voice(key):
    """Switch edge voice (used only if Piper is unavailable)."""
    v = get_edge_voice(key)
    if not v:
        return None
    _edge_voice["key"]    = key
    _edge_voice["name"]   = v["id"]
    _edge_voice["rate"]   = v.get("rate", "-5%")
    _edge_voice["pitch"]  = v.get("pitch", "-2Hz")
    _edge_voice["volume"] = _settings.voice_volume
    return v


def current_voice():
    if _engine == "piper":
        return {"key": "alan", "name": "piper-alan", "label": "Alan (Piper)",
                "rate": "1.0", "pitch": "0Hz"}
    v = get_edge_voice(_edge_voice["key"]) or {}
    return {"key": _edge_voice["key"], "name": _edge_voice["name"],
            "label": v.get("label", "Unknown"),
            "rate": _edge_voice["rate"], "pitch": _edge_voice["pitch"]}


def is_speaking() -> bool:
    return _is_speaking.is_set()


# ---------- Piper path ----------
def _piper_synth(text: str) -> Path | None:
    from voice import piper_engine
    key = hashlib.sha256(("piper|" + text).encode("utf-8")).hexdigest()[:24]
    path = _CACHE_DIR / f"{key}.wav"
    if path.exists() and path.stat().st_size > 0:
        return path
    tmp = path.with_suffix(".tmp.wav")
    ok = piper_engine.synthesize(text, tmp)
    if not ok:
        return None
    tmp.replace(path)
    return path


# ---------- edge-tts path (fallback) ----------
def _edge_cache_path(text: str) -> Path:
    key = f"{_edge_voice['name']}|{_edge_voice['rate']}|{_edge_voice['pitch']}|{_edge_voice['volume']}|{text}"
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return _CACHE_DIR / f"{h}.mp3"


async def _edge_synth_async(text: str, path: Path):
    import edge_tts
    await edge_tts.Communicate(
        text, voice=_edge_voice["name"], rate=_edge_voice["rate"],
        pitch=_edge_voice["pitch"], volume=_edge_voice["volume"],
    ).save(str(path))


def _edge_synth(text: str) -> Path | None:
    path = _edge_cache_path(text)
    if path.exists() and path.stat().st_size > 0:
        return path
    tmp = path.with_suffix(".tmp.mp3")
    try:
        asyncio.run(_edge_synth_async(text, tmp))
        tmp.replace(path)
        return path
    except Exception as exc:
        log.exception("edge-tts failed: %s", exc)
        return None


def _synth(text: str) -> tuple[Path | None, str]:
    """Try Piper, fall back to edge-tts."""
    if _engine == "piper":
        p = _piper_synth(text)
        if p:
            return p, "piper"
        log.warning("Piper failed for one line — falling back to edge-tts")
    p = _edge_synth(text)
    return p, "edge"


# ---------- sentence splitting ----------
_SENT_END = re.compile(r"(?<=[.!?])\s+")
_ABBREV = re.compile(r"\b(?:Mr|Mrs|Ms|Dr|Prof|vs|etc|e\.g|i\.e|U\.S|U\.K)\.$",
                     re.IGNORECASE)


def split_sentences(text):
    if not text:
        return []
    t = re.sub(r"\s+", " ", text.strip())
    parts = _SENT_END.split(t)
    out = []
    buf = ""
    for p in parts:
        buf = (buf + " " + p).strip() if buf else p
        if _ABBREV.search(buf):
            continue
        if len(buf) < 10:
            continue
        out.append(buf)
        buf = ""
    if buf:
        out.append(buf)
    return out or [t]


# ---------- public API ----------
def speak(text: str):
    """Speak text with sentence pipelining. Piper first, edge fallback."""
    if not text or not text.strip():
        return
    clean = text.strip()
    for ch in ["**", "*", "`", "#"]:
        clean = clean.replace(ch, "")
    clean = clean.strip()

    sentences = split_sentences(clean)
    if not sentences:
        return

    _is_speaking.set()
    try:
        from system.audio_duck import duck
        duck()
    except Exception:
        pass
    try:
        with _lock:
            paths = [None] * len(sentences)

            def synth_one(i, s):
                try:
                    p, used = _synth(s)
                    paths[i] = p
                except Exception as e:
                    log.warning("synth %d failed: %s", i, e)

            t0 = time.time()
            threads = []
            for i, s in enumerate(sentences):
                th = threading.Thread(target=synth_one, args=(i, s), daemon=True)
                th.start()
                threads.append(th)

            _init_mixer()
            threads[0].join(timeout=30)
            first_time = time.time() - t0

            if paths[0]:
                pygame.mixer.music.load(str(paths[0]))
                pygame.mixer.music.play()

            for i in range(1, len(sentences)):
                threads[i].join(timeout=30)
                if paths[i]:
                    while pygame.mixer.music.get_busy():
                        pygame.time.wait(20)
                    pygame.mixer.music.load(str(paths[i]))
                    pygame.mixer.music.play()

            while pygame.mixer.music.get_busy():
                pygame.time.wait(20)
            try:
                pygame.mixer.music.unload()
            except Exception:
                pass

            total = time.time() - t0
            log.info("spoke %d sentence(s) [%s] — first %.2fs, total %.2fs",
                     len(sentences), _engine, first_time, total)
    finally:
        try:
            from system.audio_duck import restore
            restore()
        except Exception:
            pass
        _is_speaking.clear()


def speak_async(text: str):
    t = threading.Thread(target=speak, args=(text,), daemon=True)
    t.start()
    return t


def stop():
    try:
        if _init_done:
            pygame.mixer.music.stop()
        _is_speaking.clear()
    except Exception:
        pass
    try:
        from system.audio_duck import restore
        restore()
    except Exception:
        pass


def warmup():
    _try_piper()
    try:
        sentences = split_sentences("Ready.")
        if sentences:
            _synth(sentences[0])
    except Exception:
        pass
