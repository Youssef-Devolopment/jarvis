"""User preferences — persisted to SQLite."""
from __future__ import annotations
import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)

_DB = Path(__file__).resolve().parent / "jarvis_memory.db"
_lock = threading.Lock()

_DEFAULTS = {
    "accent": "#8b3fff",
    "hue": 290,
    "anim_intensity": "normal",
    "sound_effects": True,
    "wake_chime": False,
    "notify_toasts": True,
    "auto_scroll_log": True,
    "log_max": 100,
    "show_timestamps": True,
    "compact_mode": False,
    "font_scale": 1.0,
    "voice_rate_offset": 0,
    "dnd": False,
    "hotkey_enabled": True,
    "tray_enabled": True,
    "autostart_enabled": False,
    "wake_word_enabled": False,
    "personality": "balanced",
    "personality_preset": "default",
    "personality_formality": 50,
    "personality_humor": 50,
    "personality_verbosity": 50,
    "auto_summarize": True,
    "briefings_enabled": False,
    "briefing_hour": 8,
    "ducking_enabled": True,
    "duck_level": 0.25,
    "sentinel_enabled": False,
    "sentinel_folders": [],
    "autonomy_enabled": False,
    "autonomy_confirm_timeout": 120,
    "code_mode_enabled": False,
    "code_mode_allowed": [],
    "desktop_control_enabled": True,
    "opencode_model": "",
    "auto_gen_enabled": True,
}


def _conn():
    c = sqlite3.connect(str(_DB), check_same_thread=False)
    c.execute("""CREATE TABLE IF NOT EXISTS prefs (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL)""")
    c.commit()
    return c


def all_prefs() -> dict:
    with _lock:
        c = _conn()
        rows = c.execute("SELECT key, value FROM prefs").fetchall()
        c.close()
    out = dict(_DEFAULTS)
    for k, v in rows:
        try:
            out[k] = json.loads(v)
        except Exception:
            out[k] = v
    return out


def get_pref(key: str, default=None):
    prefs = all_prefs()
    return prefs.get(key, default)


def set_pref(key: str, value) -> bool:
    if key not in _DEFAULTS:
        return False
    with _lock:
        c = _conn()
        c.execute("""INSERT INTO prefs (key, value, updated_at) VALUES (?,?,?)
                     ON CONFLICT(key) DO UPDATE SET
                     value = excluded.value,
                     updated_at = excluded.updated_at""",
                  (key, json.dumps(value),
                   datetime.now().isoformat(timespec="seconds")))
        c.commit()
        c.close()
    log.info("Pref: %s = %r", key, value)
    return True


def reset_prefs() -> None:
    with _lock:
        c = _conn()
        c.execute("DELETE FROM prefs")
        c.commit()
        c.close()
