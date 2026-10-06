"""System Guard suite — memory watchdog controls + mic pre-flight.

- *"ram guard status"* / *"guard report"* — live snapshot, threshold,
  how many times it fired.
- *"set ram guard to 85"* — retune the threshold (persisted pref).
- *"mic test"* — Smart Stream Controller: verifies the default input
  device exists and reads 0.4s of audio so a silent/dead mic is
  caught BEFORE you start dictating.
"""
from __future__ import annotations

import re

from skills.registry import register


@register("guard", [
    r"\b(?:ram|memory)\s+guard\b",
    r"\bguard\s+(?:status|report|threshold)\b",
    r"\bmemory\s+watch(?:er)?\b",
    r"\bset\s+(?:ram|memory)\s+guard\s+(?:to\s+)?(\d{2,3})\b",
], "Memory watchdog status and threshold", front=True)
def skill_guard(text, match):
    from system import guard
    thresh_match = re.search(r"(\d{2,3})\s*%?", text)
    if re.search(r"\bset\b|\bthreshold\b|\bto\s+\d", text) and thresh_match:
        val = int(thresh_match.group(1))
        if not 50 <= val <= 99:
            return "Guard threshold must be between 50 and 99 percent."
        from memory import set_pref
        set_pref("guard_ram_threshold", val)
        guard.run_once()  # re-evaluates with the new threshold
        return f"RAM guard threshold set to {val} percent."
    s = guard.status()
    if not s.get("enabled"):
        return ("RAM guard is off — turn it on in Settings → GENERAL "
                "(or say 'enable guard').")
    state = "armed and watching" if s.get("armed") else "already fired (waiting for RAM to settle)"
    fired = s.get("fired", 0)
    line = (f"RAM guard: {state}. Currently {s.get('percent', '?')}% used "
            f"({s.get('used_gb', '?')} of {s.get('total_gb', '?')} GB), "
            f"alerts at {s.get('threshold')}%, fired {fired} time"
            f"{'s' if fired != 1 else ''} this session.")
    return line


@register("mic_test", [
    r"\b(?:mic|microphone)\s+(?:test|check|level|status|works?)\b",
    r"\btest\s+(?:my\s+)?mic\b",
    r"\binput\s+(?:device|level)s?\b",
], "Verify the microphone before dictating")
def skill_mic_test(text, match):
    try:
        import sounddevice as sd
    except Exception as exc:
        return f"Mic test unavailable (audio module missing: {exc})."
    try:
        devs = sd.query_devices()
        default_in = sd.default.device[0]
        info = sd.query_devices(default_in, "input")
        name = info.get("name", "unknown device")
        rate = int(info.get("default_samplerate", 16000))
    except Exception as exc:
        return f"No input device found: {exc}. Check Windows sound settings."
    # Read a short burst and measure level (RMS of int16 samples).
    try:
        import numpy as np
        frames = int(rate * 0.4)
        rec = sd.rec(frames, samplerate=rate, channels=1, dtype="int16")
        sd.wait()
        arr = np.asarray(rec).flatten()
        peak = int(np.abs(arr).max()) if arr.size else 0
        rms = float(np.sqrt((arr.astype("float64") ** 2).mean())) if arr.size else 0.0
        pct = min(100, round(peak / 32767 * 100))
    except Exception as exc:
        return f"Mic found ({name}) but the test read failed: {exc}"
    if peak < 300:
        return (f"Mic detected ({name} @ {rate} Hz) but SILENT — "
                f"peak {pct}%: check Windows input volume/mute.")
    return (f"Mic OK: {name} @ {rate} Hz, peak level {pct}% "
            f"({'healthy' if 5 <= pct <= 95 else 'a bit ' + ('quiet' if pct < 5 else 'hot')}).")
