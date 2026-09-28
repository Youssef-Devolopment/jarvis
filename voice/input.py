"""Speech input — records locally, transcribes via Groq. Verbose logging."""
from __future__ import annotations
import queue
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd

from config import get_settings
from logger import get_logger

log = get_logger(__name__)
_settings = get_settings()


def _write_wav(path: Path, audio: np.ndarray, rate: int) -> None:
    pcm = np.clip(audio, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm.tobytes())


def _rms(chunk: np.ndarray) -> float:
    if chunk.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))


def _transcribe_groq(wav_path: Path) -> Optional[str]:
    if not _settings.groq_api_key:
        log.error("STT: GROQ_API_KEY missing from .env")
        return None
    try:
        from groq import Groq
        client = Groq(api_key=_settings.groq_api_key, timeout=60)

        kwargs = {
            "file": (wav_path.name, open(wav_path, "rb").read()),
            "model": _settings.groq_stt_model,
            "response_format": "text",
            "prompt": ("The user may mix Arabic and English in the same "
                       "sentence. Transcribe both languages faithfully."),
        }
        # Only pass language if it's a real ISO code, not "auto"
        lang = (_settings.groq_stt_language or "").strip().lower()
        if lang and lang != "auto":
            kwargs["language"] = lang

        t0 = time.time()
        result = client.audio.transcriptions.create(**kwargs)
        elapsed = time.time() - t0
        text = str(result).strip()
        log.info("STT: Groq replied in %.2fs (lang=%s) — %r",
                 elapsed, lang or "auto", text[:80])
        return text or None
    except Exception as exc:
        log.exception("STT: Groq call failed: %s", exc)
        return None


def listen_until_silence(verbose: bool = True) -> Optional[str]:
    log.info("STT: entering listen_until_silence")
    if not _settings.groq_api_key:
        log.error("STT: Groq API key not set — cannot transcribe")
        return None

    log.info("STT: opening mic stream (samplerate=16000)")
    audio_q: queue.Queue = queue.Queue()
    recorded = []
    stop_flag = threading.Event()

    def callback(indata, frames, t, status):
        if status:
            log.debug("STT: audio status %s", status)
        if not stop_flag.is_set():
            audio_q.put(indata.copy())

    block_dur = 0.1
    block_size = int(16000 * block_dur)
    sil_need = max(1, int(_settings.silence_duration / block_dur))
    sil_count = 0
    total = 0.0
    started = False
    blocks_seen = 0

    try:
        try:
            from system.audio_duck import duck
            duck()
        except Exception:
            pass
        with sd.InputStream(samplerate=16000, channels=1, dtype="float32",
                            blocksize=block_size, callback=callback):
            log.info("STT: stream open, listening for speech...")
            while total < _settings.max_record_sec:
                try:
                    chunk = audio_q.get(timeout=1.0)
                except queue.Empty:
                    log.debug("STT: no audio block in 1s (total=%.1fs)", total)
                    if total > 2 and not started:
                        log.info("STT: 2s passed with no speech — giving up")
                        return None
                    continue
                blocks_seen += 1
                lvl = _rms(chunk)
                total += block_dur
                if lvl >= _settings.silence_threshold:
                    if not started:
                        log.info("STT: speech detected at %.1fs "
                                 "(level=%.4f, threshold=%.4f)",
                                 total, lvl, _settings.silence_threshold)
                    started = True
                    sil_count = 0
                    recorded.append(chunk)
                elif started:
                    sil_count += 1
                    recorded.append(chunk)
                    if sil_count >= sil_need:
                        log.info("STT: %.1fs of silence — stopping",
                                 sil_count * block_dur)
                        break
    except Exception as exc:
        log.exception("STT: mic stream failed: %s", exc)
        return None
    finally:
        stop_flag.set()
        try:
            from system.audio_duck import restore
            restore()
        except Exception:
            pass

    log.info("STT: recorded %d blocks, %d kept, total time %.1fs",
             blocks_seen, len(recorded), total)

    if not recorded:
        log.warning("STT: no audio kept — mic may be muted or blocked")
        return None

    audio = np.concatenate(recorded, axis=0).flatten()
    peak = float(np.max(np.abs(audio)))
    log.info("STT: peak amplitude %.4f (%.1f seconds)",
             peak, len(audio) / 16000)
    if peak < 0.005:
        log.warning("STT: signal very weak — check Windows mic permissions")

    energy = np.abs(audio)
    if len(energy) > 0:
        thr = np.max(energy) * 0.05
        idx = np.where(energy > thr)[0]
        if len(idx) > 0:
            audio = audio[max(0, idx[0] - 800): idx[-1] + 800]

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    tmp_path = Path(tmp.name)
    _write_wav(tmp_path, audio, 16000)
    log.info("STT: sending %d bytes to Groq...", tmp_path.stat().st_size)
    try:
        return _transcribe_groq(tmp_path)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


def listen() -> Optional[str]:
    return listen_until_silence()


def transcribe_audio_bytes(audio_bytes: bytes, suffix: str = ".webm") -> Optional[str]:
    """Transcribe raw audio bytes directly via Groq. No local recording."""
    if not audio_bytes:
        return None
    if not _settings.groq_api_key:
        log.error("STT: GROQ_API_KEY missing")
        return None
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(audio_bytes)
    tmp.close()
    tmp_path = Path(tmp.name)
    try:
        return _transcribe_groq(tmp_path)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
