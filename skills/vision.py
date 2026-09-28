"""Screen vision via DeepSeek's native multimodal model.

Uses deepseek-flash — accepts images alongside text. No external API needed.
Model detects image format from content, not filename.
Supports JPEG, PNG, GIF, WebP.
"""
from __future__ import annotations
import base64
import os
import time
from pathlib import Path

from skills.registry import register
from logger import get_logger

log = get_logger(__name__)

_SHOT_DIR = Path(__file__).resolve().parent.parent / "logs" / "screenshots"
_SHOT_DIR.mkdir(parents=True, exist_ok=True)

# DeepSeek's vision model (verified working with image input on TokenHarbor)
VISION_MODEL = os.getenv("VISION_MODEL", "deepseek-v4.1-flash:free")


def _capture() -> Path | None:
    """Take a screenshot of the full screen."""
    try:
        import pyautogui
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = _SHOT_DIR / f"vision_{ts}.png"
        img = pyautogui.screenshot()
        img.save(str(path))
        return path
    except Exception as exc:
        log.exception("Screenshot failed: %s", exc)
        return None


def _encode(path: Path) -> str:
    """Base64-encode an image file."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _analyze(prompt: str, max_tokens: int = 400) -> str:
    """Capture the screen and ask DeepSeek vision about it."""
    path = _capture()
    if not path:
        return "Could not capture the screen. Install pyautogui."

    try:
        from ai.client import get_client
        c = get_client()
        b64 = _encode(path)

        resp = c._client.chat.completions.create(
            model=VISION_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }],
            max_tokens=max_tokens,
            temperature=0.2,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        log.exception("Vision failed")
        return f"Vision failed: {str(exc)[:120]}"


# ---------- Skills ----------

@register("vision_describe", [
    r"^what(?:'s|\s+is)\s+on\s+(?:my|the)\s+screen[\?\.\!]?$",
    r"^look\s+at\s+(?:my|the)\s+screen[\?\.\!]?$",
    r"^describe\s+(?:my|the)\s+screen[\?\.\!]?$",
], "Describe the screen")
def s_describe(text, m):
    return _analyze(
        "Describe what is on this screen in 2 short sentences. "
        "Mention the main application, what content is visible, and any "
        "important notifications or errors. Be concise and spoken-friendly.")


@register("vision_read", [
    r"^read\s+(?:my|the)\s+screen[\?\.\!]?$",
    r"^what\s+does\s+(?:my|the)\s+screen\s+say[\?\.\!]?$",
], "Read text from screen")
def s_read(text, m):
    return _analyze(
        "Read the main text visible on this screen in 2-3 sentences. "
        "Summarize what the user is looking at.")


@register("vision_help", [
    r"^(?:help\s+me\s+(?:with\s+)?)?what\s+should\s+i\s+do[\?\.\!]?$",
    r"^i(?:'m|\s+am)\s+stuck[\?\.\!]?$",
], "Help with current screen")
def s_help(text, m):
    return _analyze(
        "The user is stuck and needs help. Look at their screen and tell "
        "them in 2-3 spoken sentences what to do next. Be specific about "
        "which button or field they should interact with.")


@register("vision_error", [
    r"^what(?:'s|\s+is)\s+(?:this|the)\s+error[\?\.\!]?$",
    r"^(?:explain|read)\s+(?:this|the)\s+error[\?\.\!]?$",
], "Explain on-screen error")
def s_error(text, m):
    return _analyze(
        "There is an error on the screen. Explain in 2 sentences what "
        "went wrong and how to fix it. If no error is visible, say so.")


@register("vision_screenshot", [
    r"^(?:take\s+(?:a\s+)?)?screenshot\s+and\s+tell\s+me\s+about\s+it[\?\.\!]?$",
], "Screenshot and analyze")
def s_screenshot_analyze(text, m):
    return _analyze(
        "Describe this screenshot in 3 sentences. Note any important "
        "details the user should know.")


@register("vision_compare", [
    r"^what\s+changed\s+(?:on\s+)?(?:my|the)\s+screen[\?\.\!]?$",
], "What changed on screen")
def s_compare(text, m):
    return _analyze(
        "Describe the current state of the screen in 2 sentences. "
        "Focus on what is most recently visible or in focus.")


@register("vision_find", [
    r"^where\s+is\s+(?:the\s+)?(?P<target>.+?)\s+on\s+(?:my|the)\s+screen[\?\.\!]?$",
], "Find element on screen")
def s_find(text, m):
    target = (m.group("target") or "").strip()
    if not target:
        return None
    return _analyze(
        f"Find '{target}' on this screen. Tell the user in one sentence "
        f"where it is located — top, bottom, left, right, or center — and "
        f"what color or shape it has.")
