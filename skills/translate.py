"""Translation via LibreTranslate (free public endpoint)."""
from __future__ import annotations
import json
import urllib.parse
import urllib.request
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)

# Simple language map
LANGS = {
    "english": "en", "en": "en",
    "arabic": "ar", "ar": "ar",
    "spanish": "es", "es": "es",
    "french": "fr", "fr": "fr",
    "german": "de", "de": "de",
    "italian": "it", "it": "it",
    "portuguese": "pt", "pt": "pt",
    "russian": "ru", "ru": "ru",
    "chinese": "zh", "zh": "zh",
    "japanese": "ja", "ja": "ja",
    "korean": "ko", "ko": "ko",
    "turkish": "tr", "tr": "tr",
    "hindi": "hi", "hi": "hi",
    "urdu": "ur", "ur": "ur",
    "persian": "fa", "farsi": "fa", "fa": "fa",
}

# Free public LibreTranslate mirrors (rotate on failure)
MIRRORS = [
    "https://libretranslate.com/translate",
    "https://translate.astian.org/translate",
    "https://libretranslate.de/translate",
]


def _translate_mymemory(text: str, target: str, source: str = "en") -> str | None:
    """Free MyMemory API (no key, ~5000 chars/day anon)."""
    try:
        url = ("https://api.mymemory.translated.net/get?"
               + urllib.parse.urlencode(
                   {"q": text, "langpair": f"{source}|{target}"}))
        req = urllib.request.Request(url, headers={"User-Agent": "JARVIS/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        out = ((data.get("responseData") or {}).get("translatedText") or "").strip()
        if out and "QUERY LENGTH LIMIT" not in out.upper():
            return out
    except Exception as exc:
        log.debug("MyMemory failed: %s", exc)
    return None


def _translate(text: str, target: str, source: str = "en") -> str | None:
    payload = json.dumps({
        "q": text, "source": source, "target": target, "format": "text",
    }).encode("utf-8")
    for url in MIRRORS:
        try:
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json",
                         "User-Agent": "JARVIS/1.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode("utf-8"))
                out = (data.get("translatedText") or "").strip()
                if out:
                    return out
        except Exception as exc:
            log.debug("Translate mirror failed (%s): %s", url, exc)
            continue
    return None


@register("translate", [
    r"^(?:translate|say)\s+[\"'](?P<text>.+?)[\"']\s+"
    r"(?:in(?:to)?|to)\s+(?P<lang>\w+)[\?\.\!]?$",
    r"^how\s+do\s+you\s+say\s+[\"'](?P<text2>.+?)[\"']\s+"
    r"in\s+(?P<lang2>\w+)[\?\.\!]?$",
], "Translate text")
def skill_translate(text, m):
    gd = m.groupdict()
    src_text = (gd.get("text") or gd.get("text2") or "").strip()
    lang_name = (gd.get("lang") or gd.get("lang2") or "").strip().lower()
    if not src_text or not lang_name:
        return None
    target = LANGS.get(lang_name)
    if not target:
        return f"I do not know the language: {lang_name}"
    result = _translate_mymemory(src_text, target) or _translate(src_text, target)
    if not result:
        return "Translation service is unavailable."
    return f"{lang_name.title()}: {result}"
