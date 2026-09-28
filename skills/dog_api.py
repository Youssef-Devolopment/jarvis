"""Dog APIs: random images, facts, breeds."""
from __future__ import annotations
import json
import urllib.request
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)


def _get(url: str, timeout: float = 6.0):
    req = urllib.request.Request(url, headers={"User-Agent": "JARVIS/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


@register("dog_image", [
    r"^(?:show\s+me\s+a\s+)?(?:random\s+)?dog\s+(?:picture|image|photo)[\?\.\!]?$",
    r"^give\s+me\s+a\s+dog\s+picture[\?\.\!]?$",
], "Random dog image")
def s_dog_image(text, m):
    try:
        d = _get("https://dog.ceo/api/breeds/image/random")
        return f"Here is a random dog: {d.get('message', '')}"
    except Exception as exc:
        return f"Dog API failed: {str(exc)[:60]}"


@register("dog_fact", [
    r"^(?:tell\s+me\s+a\s+)?dog\s+fact[\?\.\!]?$",
    r"^random\s+dog\s+fact[\?\.\!]?$",
], "Random dog fact")
def s_dog_fact(text, m):
    try:
        d = _get("https://dogapi.dog/api/v2/facts")
        data = d.get("data", [])
        if data:
            return data[0].get("attributes", {}).get("body", "")
        return "No dog fact found."
    except Exception:
        return None


@register("dog_breed", [
    r"^(?:what\s+is\s+a\s+)?(?P<breed>\w+)\s+dog\s+breed[\?\.\!]?$",
    r"^tell\s+me\s+about\s+(?P<breed2>\w+)\s+dogs[\?\.\!]?$",
], "Dog breed info")
def s_dog_breed(text, m):
    gd = m.groupdict()
    breed = (gd.get("breed") or gd.get("breed2") or "").strip().lower()
    if not breed:
        return None
    try:
        d = _get(f"https://api.thedogapi.com/v1/breeds/search?q={breed}")
        if d:
            info = d[0]
            name = info.get("name", breed)
            temperament = info.get("temperament", "")
            life = info.get("life_span", "")
            weight = info.get("weight", {}).get("imperial", "")
            return f"{name}: {temperament[:100]}. Lifespan: {life}. Weight: {weight} lbs."
        return None
    except Exception:
        return None
