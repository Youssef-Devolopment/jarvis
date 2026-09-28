"""Model registry + themes + featured list."""
from __future__ import annotations
from dataclasses import dataclass
from threading import Lock
from logger import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class ModelTheme:
    hue: int
    accent: str
    label: str


# Only confirmed-working models
FEATURED = [
    {"id": "auto",                      "label": "Auto",     "hue": 290, "accent": "#8b3fff", "free": True,  "tag": "smart"},
    {"id": "qwen3.8-flash:free",        "label": "Qwen 3.8 ●", "hue": 345, "accent": "#f43f5e", "free": True,  "tag": "fastest"},
    {"id": "mimo-v2.6-flash:free",      "label": "Mimo 2.6 ●", "hue": 155, "accent": "#00c9a7", "free": True,  "tag": "fast"},
    {"id": "deepseek-v4.1-flash:free",  "label": "Flash ●",  "hue": 200, "accent": "#00d4ff", "free": True,  "tag": "fast"},
    {"id": "deepseek-v4-flash:free",    "label": "V4 ●",     "hue": 195, "accent": "#22d3ee", "free": True,  "tag": "fast"},
    {"id": "mimo-v2.5:free",            "label": "Mimo ●",   "hue": 155, "accent": "#00c9a7", "free": True,  "tag": "free"},
]


def featured_models() -> list[dict]:
    return [dict(m) for m in FEATURED]


SPEED_RANK = {
    "flash": 1, "turbo": 2, "mini": 3, "mimo": 3, "chat": 4,
    "v3": 5, "v4": 5, "qwen": 6, "llama": 6, "gemini": 7,
    "gpt": 8, "claude": 9, "coder": 10, "pro": 11,
    "reasoner": 99, "reason": 99, "o1": 99,
}

FALLBACK_MODELS = [
    "deepseek-v4.1-flash:free",
    "deepseek-v4-flash:free",
    "mimo-v2.5:free",
]

THEMES = {
    "default":  ModelTheme(hue=290, accent="#8b3fff", label="Default"),
    "flash":    ModelTheme(hue=200, accent="#00d4ff", label="Flash"),
    "turbo":    ModelTheme(hue=190, accent="#22d3ee", label="Turbo"),
    "mini":     ModelTheme(hue=175, accent="#14b8a6", label="Mini"),
    "chat":     ModelTheme(hue=290, accent="#8b3fff", label="Chat"),
    "v3":       ModelTheme(hue=270, accent="#a855f7", label="V3"),
    "v4":       ModelTheme(hue=280, accent="#9333ea", label="V4"),
    "reasoner": ModelTheme(hue=35,  accent="#ffb84d", label="Reasoner"),
    "reason":   ModelTheme(hue=35,  accent="#f59e0b", label="Reason"),
    "coder":    ModelTheme(hue=140, accent="#4ade80", label="Coder"),
    "pro":      ModelTheme(hue=320, accent="#e05cf4", label="Pro"),
    "free":     ModelTheme(hue=180, accent="#00e5b4", label="Free"),
    "vision":   ModelTheme(hue=260, accent="#a78bfa", label="Vision"),
    "claude":   ModelTheme(hue=25,  accent="#ff7f50", label="Claude"),
    "gpt":      ModelTheme(hue=160, accent="#10a37f", label="GPT"),
    "gemini":   ModelTheme(hue=225, accent="#4285f4", label="Gemini"),
    "llama":    ModelTheme(hue=210, accent="#3b82f6", label="Llama"),
    "qwen":     ModelTheme(hue=345, accent="#f43f5e", label="Qwen"),
    "mimo":     ModelTheme(hue=155, accent="#00c9a7", label="Mimo"),
}


def theme_for(model_name: str) -> ModelTheme:
    n = (model_name or "").lower()
    for key, t in THEMES.items():
        if key != "default" and key in n:
            return t
    return THEMES["default"]


def label_for(model_name: str) -> str:
    if not model_name:
        return "—"
    for f in FEATURED:
        if f["id"] == model_name:
            return f["label"]
    short = model_name.split("/")[-1]
    if ":" in short:
        short = short.split(":")[0]
    short = short.replace("deepseek-", "").replace("deepseek", "DS")
    return short


def is_free(model_id: str) -> bool:
    if not model_id:
        return False
    return ":free" in model_id.lower() or model_id.lower().endswith("-free")


def speed_rank(model_id: str) -> int:
    n = (model_id or "").lower()
    best = 50
    for key, rank in SPEED_RANK.items():
        if key in n and rank < best:
            best = rank
    return best


_lock = Lock()
_active = ""
_cache = []
_working = {}


def set_active(name: str) -> None:
    global _active
    with _lock:
        _active = name or ""


def get_active() -> str:
    with _lock:
        return _active


def set_cache(models: list) -> None:
    global _cache
    with _lock:
        _cache = list(models)


def get_cache() -> list:
    with _lock:
        return list(_cache)


def set_working(name: str, ok: bool, msg: str = "") -> None:
    with _lock:
        _working[name] = {"ok": ok, "msg": msg}


def get_working(name: str):
    with _lock:
        return _working.get(name)


def all_working() -> dict:
    with _lock:
        return dict(_working)


def build_fallback_list() -> list:
    out = []
    for mid in FALLBACK_MODELS:
        t = theme_for(mid)
        out.append({
            "id": mid, "label": label_for(mid),
            "hue": t.hue, "accent": t.accent,
            "fallback": True, "free": True,
            "rank": speed_rank(mid),
        })
    out.sort(key=lambda x: x["rank"])
    return out


def sort_models(models: list) -> list:
    return sorted(models, key=lambda m: (m.get("rank", 50), m.get("label", "")))
