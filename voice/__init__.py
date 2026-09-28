from voice.output import (speak, speak_async, stop as stop_speaking, warmup,
                           apply_mood_voice, set_voice, current_voice,
                           is_speaking)
from voice.voices import all_voices, VOICES

try:
    from voice.input import listen, listen_until_silence, transcribe_audio_bytes
    _HAS_INPUT = True
except ImportError as exc:
    _HAS_INPUT = False
    from logger import get_logger
    get_logger(__name__).warning("Voice input unavailable: %s", exc)
    def listen(*a, **k): return None
    def listen_until_silence(*a, **k): return None
    def transcribe_audio_bytes(*a, **k): return None

__all__ = ["speak", "speak_async", "stop_speaking", "warmup",
           "apply_mood_voice", "set_voice", "current_voice", "is_speaking",
           "all_voices", "VOICES",
           "listen", "listen_until_silence", "transcribe_audio_bytes"]
