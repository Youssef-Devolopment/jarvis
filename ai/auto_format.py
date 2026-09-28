"""Auto-format — detect and reformat JSON, JSON-minify, etc."""

from __future__ import annotations
import json
import re


def detect(text):
    if not text: return "unknown"
    t = text.strip()
    if (t.startswith("{") and t.endswith("}")) or (t.startswith("[") and t.endswith("]")):
        try:
            json.loads(t); return "json"
        except Exception: pass
    if re.match(r"^-?\d+(\.\d+)?$", t): return "number"
    return "unknown"


def format_text(text, mode="auto"):
    kind = detect(text) if mode == "auto" else mode
    if kind == "json":
        try:
            return {"ok": True, "output": json.dumps(json.loads(text), indent=2, ensure_ascii=False)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": f"cannot format: {kind}"}


def minify(text):
    try:
        return {"ok": True, "output": json.dumps(json.loads(text), separators=(",", ":"), ensure_ascii=False)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
