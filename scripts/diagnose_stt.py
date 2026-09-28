"""Diagnose Groq STT pipeline. Run: python scripts/diagnose_stt.py"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

print("=" * 60)
print("Groq STT Diagnostic")
print("=" * 60)

# 1. Check .env
env_path = Path(__file__).resolve().parent.parent / ".env"
print(f"\n[1] .env file at {env_path}")
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("GROQ_API_KEY"):
            parts = line.split("=", 1)
            if len(parts) == 2:
                val = parts[1].strip()
                print(f"    GROQ_API_KEY present, length={len(val)}, "
                      f"starts_gsk={val.startswith('gsk_')}, "
                      f"placeholder={'gsk_your' in val}")
            break
    else:
        print("    GROQ_API_KEY NOT FOUND in .env")
else:
    print("    .env file missing!")

# 2. Check config loads
print(f"\n[2] config.get_settings()")
try:
    from config import get_settings
    s = get_settings()
    k = s.groq_api_key or ""
    print(f"    groq_api_key length: {len(k)}")
    print(f"    starts with gsk_: {k.startswith('gsk_') if k else False}")
    print(f"    model: {s.groq_stt_model}")
    print(f"    language: {s.groq_stt_language}")
except Exception as exc:
    print(f"    CONFIG ERROR: {exc}")

# 3. Check sounddevice sees a mic
print(f"\n[3] sounddevice input devices")
try:
    import sounddevice as sd
    devices = sd.query_devices()
    inputs = [d for d in devices if d.get("max_input_channels", 0) > 0]
    print(f"    Found {len(inputs)} input device(s):")
    for d in inputs[:5]:
        print(f"      - {d['name']}")
    default = sd.query_devices(kind="input")
    print(f"    Default input: {default['name']}")
except Exception as exc:
    print(f"    SOUNDDEVICE ERROR: {exc}")

# 4. Check groq package
print(f"\n[4] groq package")
try:
    import groq
    print(f"    groq version: {groq.__version__}")
except Exception as exc:
    print(f"    GROQ IMPORT ERROR: {exc}")

# 5. Test recording (2 seconds, no transcription)
print(f"\n[5] Recording test (2 seconds — speak now)")
try:
    import numpy as np
    import sounddevice as sd
    print("    Starting...")
    audio = sd.rec(int(2 * 16000), samplerate=16000, channels=1,
                   dtype="float32")
    sd.wait()
    peak = float(np.max(np.abs(audio)))
    print(f"    Captured {len(audio)} samples, peak level: {peak:.4f}")
    if peak < 0.001:
        print("    WARNING: Mic captured silence — check Windows mic permissions")
    else:
        print("    Mic works.")
except Exception as exc:
    print(f"    RECORDING ERROR: {exc}")

# 6. Test Groq transcription with tiny silent audio
print(f"\n[6] Groq transcription test (5 sec silence)")
try:
    import tempfile
    import wave
    import numpy as np
    from config import get_settings
    s = get_settings()
    if not s.groq_api_key:
        print("    SKIPPED — no API key")
    else:
        audio = np.zeros(16000 * 5, dtype=np.float32)
        pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        with wave.open(tmp.name, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(pcm.tobytes())
        t0 = time.time()
        from groq import Groq
        client = Groq(api_key=s.groq_api_key, timeout=30)
        with open(tmp.name, "rb") as f:
            result = client.audio.transcriptions.create(
                file=(Path(tmp.name).name, f.read()),
                model=s.groq_stt_model,
                language=s.groq_stt_language,
                response_format="text",
            )
        elapsed = time.time() - t0
        print(f"    Groq responded in {elapsed:.2f}s")
        print(f"    Result: {repr(str(result)[:100])}")
        os.unlink(tmp.name)
except Exception as exc:
    print(f"    GROQ API ERROR: {exc}")

print("\n" + "=" * 60)
print("Done. Send this output to fix the issue.")
print("=" * 60)
