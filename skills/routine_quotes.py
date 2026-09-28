"""Quotes via zenquotes.io."""
from __future__ import annotations
import json, random, urllib.request
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)

_LOCAL = [
    ("The only way to do great work is to love what you do.", "Steve Jobs"),
    ("Talk is cheap. Show me the code.", "Linus Torvalds"),
    ("Stay hungry, stay foolish.", "Steve Jobs"),
    ("The best way to predict the future is to invent it.", "Alan Kay"),
    ("Simplicity is the ultimate sophistication.", "Leonardo da Vinci"),
    ("Any sufficiently advanced technology is indistinguishable from magic.", "Arthur C. Clarke"),
    ("It always seems impossible until it's done.", "Nelson Mandela"),
    ("The journey of a thousand miles begins with a single step.", "Lao Tzu"),
]


@register("quote", [
    r"^(?:give\s+me\s+)?(?:a\s+)?(?:quote|motivation|inspiration)(?:\s+about\s+\w+)?[\?\.\!]?$",
    r"^motivate\s+me[\?\.\!]?$",
    r"^inspire\s+me[\?\.\!]?$",
], "Motivational quote")
def s_quote(text, m):
    try:
        req = urllib.request.Request("https://zenquotes.io/api/random",
                                     headers={"User-Agent": "JARVIS/1.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            d = json.loads(r.read().decode("utf-8"))
            if isinstance(d, list) and d:
                q = (d[0].get("q") or "").strip()
                a = (d[0].get("a") or "").strip()
                if q:
                    return f'"{q}" — {a}' if a else f'"{q}"'
    except Exception:
        pass
    q, a = random.choice(_LOCAL)
    return f'"{q}" — {a}'
