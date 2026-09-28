"""Screen OCR via Vision."""

from __future__ import annotations
import base64, time
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)
_ROOT = Path(__file__).resolve().parent.parent
_SHOTS = _ROOT / "logs" / "screenshots"
_SHOTS.mkdir(parents=True, exist_ok=True)


def _capture():
    try:
        from PIL import ImageGrab
        ts = time.strftime("%Y%m%d_%H%M%S")
        p = _SHOTS / f"ocr_{ts}.png"
        ImageGrab.grab().save(str(p))
        return p
    except Exception as exc:
        log.exception("Capture failed: %s", exc)
        return None


def extract_text(question="Extract all visible text from this screenshot. Preserve line breaks. Return only the text."):
    p = _capture()
    if not p: return "[error] could not capture screen"
    try:
        from ai.client import get_client
        c = get_client()
        with open(p, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        r = c._client.chat.completions.create(
            model="deepseek-v4.1-flash:free",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]}], max_tokens=1500, temperature=0.1)
        return (r.choices[0].message.content or "").strip()
    except Exception as exc:
        log.exception("OCR failed")
        return f"[error] {exc}"
    finally:
        try: p.unlink(missing_ok=True)
        except Exception: pass
