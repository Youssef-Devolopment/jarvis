"""Shared imports, helpers and the single /api blueprint.

Every ``routes/api_*.py`` module imports what it needs from here
and registers its routes on ``bp``. This module is the deliberate
shared namespace for the API layer, so the imports below are
re-exports and are listed in ``__all__``.
"""
from __future__ import annotations

import json as json
import os as os
import sys as sys

from flask import Blueprint as Blueprint
from flask import Response as Response
from flask import jsonify as jsonify
from flask import request as request

from ai import extract_memory_async as extract_memory_async
from ai import get_client as get_client
from ai import get_store as get_store
from ai.tools import TOOL_SCHEMAS as TOOL_SCHEMAS
from config import VERSION as VERSION
from config import try_settings as try_settings
from errors import AIError as AIError
from errors import ConfigError as ConfigError
from errors import ValidationError as ValidationError
from errors import VoiceError as VoiceError
from logger import get_logger as get_logger
from mcp import add_server as mcp_add
from mcp import all_servers as mcp_list
from skills import all_skills as all_skills
from skills import dispatch as dispatch_skill
from skills import toggle_skill as toggle_skill
from tools import all_tools as all_tools
from tools import filtered_schemas as filtered_schemas
from tools import toggle_tool as toggle_tool

try:
    from voice import all_voices as all_voices
    from voice import current_voice as current_voice
    from voice import listen_until_silence as listen_until_silence
    from voice import set_voice as set_voice_impl
    from voice import speak_async as speak_async
except Exception as _voice_import_exc:
    # Skills-only (no-key) boot: voice/output.py reads settings at import.
    # Stub the entry points so text endpoints stay up; voice endpoints
    # fail loudly with a clear error instead of killing the import chain.
    # (Copied to a plain module global: `except ... as` names are
    # deleted when the block exits.)
    _voice_import_detail = str(_voice_import_exc)[:120]
    log = get_logger(__name__)
    log.warning("Voice subsystem unavailable (%s). Text chat and skills "
                "are unaffected.", _voice_import_detail)

    def _voice_down(*_a, **_k):
        raise VoiceError("Voice subsystem unavailable.",
                         detail=_voice_import_detail)
    speak_async = listen_until_silence = set_voice_impl = \
        current_voice = all_voices = _voice_down


def _speak_quiet(text: str) -> None:
    """Best-effort TTS for chat replies: a dead speaker must never
    turn a good text answer into a failed request."""
    try:
        speak_async(text)
    except Exception as exc:
        get_logger(__name__).warning("speak failed (reply kept): %s", exc)


def _to_int(value, default: int, lo: int | None = None,
            hi: int | None = None) -> int:
    """Parse user-supplied ints defensively: garbage becomes the
    default, extremes get clamped. Never raises."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v
import harness as harness
import memory as memory
import moods as moods
from ai import agents as agents
from ai import auto_format as auto_format
from ai import clipboard_watcher as clipboard_watcher
from ai import dream_mode as dream_mode
from ai import focus_lock as focus_lock
from ai import quick_capture as quick_capture
from ai import reality_check as reality_check
from ai import screen_text as screen_text
from ai import snippets as snippets
from ai import time_tracker as time_tracker
from ai import url_cleaner as url_cleaner
from ai import window_layouts as window_layouts
from memory import outcomes as outcomes
from moods.levels import LEVEL_SPECS as LEVEL_SPECS
from moods.levels import Level as Level
from moods.models import build_fallback_list as build_fallback_list
from moods.models import get_active as get_active
from moods.models import get_cache as get_cache
from moods.models import label_for as label_for
from moods.models import set_active as set_active
from moods.models import set_cache as set_cache
from moods.models import theme_for as theme_for
from moods.router import needs_reasoning as needs_reasoning

log = get_logger(__name__)
bp = Blueprint("api", __name__, url_prefix="/api")


def _theme_dict(model_name: str) -> dict:
    t = theme_for(model_name)
    return {"hue": t.hue, "accent": t.accent, "label": t.label}

__all__ = [
    "AIError",
    "Blueprint",
    "ConfigError",
    "LEVEL_SPECS",
    "Level",
    "Response",
    "TOOL_SCHEMAS",
    "VERSION",
    "ValidationError",
    "VoiceError",
    "agents",
    "all_skills",
    "all_tools",
    "all_voices",
    "auto_format",
    "build_fallback_list",
    "clipboard_watcher",
    "current_voice",
    "dispatch_skill",
    "dream_mode",
    "extract_memory_async",
    "filtered_schemas",
    "focus_lock",
    "get_active",
    "get_cache",
    "get_client",
    "get_logger",
    "get_store",
    "harness",
    "json",
    "jsonify",
    "label_for",
    "listen_until_silence",
    "mcp_add",
    "mcp_list",
    "memory",
    "moods",
    "needs_reasoning",
    "os",
    "outcomes",
    "quick_capture",
    "reality_check",
    "request",
    "screen_text",
    "set_active",
    "set_cache",
    "set_voice_impl",
    "snippets",
    "speak_async",
    "sys",
    "theme_for",
    "time_tracker",
    "toggle_skill",
    "toggle_tool",
    "try_settings",
    "url_cleaner",
    "window_layouts",
]
