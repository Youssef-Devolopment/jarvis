"""Dictionary via dictionaryapi.dev (Wiktionary fallback)."""
from __future__ import annotations
import json, re, urllib.parse, urllib.request
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "JARVIS/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


@register("dictionary", [
    r"^what\s+does\s+(?P<w1>\w+)\s+mean[\?\.\!]?$",
    r"^define\s+(?P<w2>\w+)[\?\.\!]?$",
    r"^definition\s+of\s+(?P<w3>\w+)[\?\.\!]?$",
], "Dictionary lookup")
def s_dict(text, m):
    gd = m.groupdict()
    word = (gd.get("w1") or gd.get("w2") or gd.get("w3") or "").strip()
    if not word:
        return None
    try:
        data = _get("https://api.dictionaryapi.dev/api/v2/entries/en/"
                    + urllib.parse.quote(word))
        if not isinstance(data, list) or not data:
            return f"No definition for '{word}'."
        meanings = data[0].get("meanings") or []
        if not meanings:
            return None
        first = meanings[0]
        part = first.get("partOfSpeech", "")
        defs = first.get("definitions") or []
        if not defs:
            return None
        definition = (defs[0].get("definition") or "").strip()
        if not definition:
            return None
        return f"{word} ({part}): {definition}"
    except Exception:
        pass
    # Fallback: Wiktionary REST API (fast, same infra as Wikipedia)
    try:
        data = _get("https://en.wiktionary.org/api/rest_v1/page/definition/"
                    + urllib.parse.quote(word.lower()))
        entries = data.get("en") or []
        for entry in entries:
            part = entry.get("partOfSpeech", "")
            for d in entry.get("definitions") or []:
                raw = (d.get("definition") or "").strip()
                if not raw:
                    continue
                clean = re.sub(r"<[^>]+>", "", raw).strip()
                clean = re.sub(r"\s+", " ", clean)
                if clean:
                    return f"{word} ({part}): {clean[:300]}"
        return None
    except Exception:
        return None
