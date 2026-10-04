from skills.base import Skill
from skills.registry import (all_skills, dispatch, get_skill, toggle_skill,
                             unregister)

from skills import web_search      # noqa: F401
from skills import clock           # noqa: F401
from skills import math_skill      # noqa: F401
from skills import system          # noqa: F401
from skills import system_control  # noqa: F401
from skills import browser_keyboard   # noqa: F401
from skills import desktop_keyboard   # noqa: F401
from skills import desktop_mouse      # noqa: F401
from skills import vision             # noqa: F401
from skills import app_launcher       # noqa: F401
from skills import app_closer         # noqa: F401
from skills import weather      # noqa: F401
from skills import wiki         # noqa: F401
from skills import crypto       # noqa: F401
from skills import translate    # noqa: F401
from skills import routine_dictionary     # noqa: F401
from skills import routine_fx             # noqa: F401
from skills import routine_quotes         # noqa: F401
from skills import routine_timers         # noqa: F401
from skills import routine_notes          # noqa: F401
from skills import routine_todo           # noqa: F401
from skills import routine_convert        # noqa: F401
from skills import routine_news           # noqa: F401
from skills import dog_api          # noqa: F401
from skills import whatsapp_web     # noqa: F401
from skills import gmail_api        # noqa: F401
from skills import vscode_open      # noqa: F401
from skills import todoist_api      # noqa: F401
from skills import mcp_manager      # noqa: F401
from skills import clawbot_bridge   # noqa: F401
from skills import openhands_bridge # noqa: F401
from skills import code_mode       # noqa: F401
from skills import opencode_bridge # noqa: F401
from skills import interpreter_hand # noqa: F401
from skills import web_open         # noqa: F401
from skills import web_read        # noqa: F401
from skills import web_screenshot  # noqa: F401
from skills import folder_sentinel # noqa: F401
from skills import win_target      # noqa: F401
from skills import bridge_skill    # noqa: F401
from skills import app_finder      # noqa: F401
from skills import site_finder     # noqa: F401
from skills import quick_capture_skill     # noqa: F401
from skills import screen_ocr_skill        # noqa: F401
from skills import screen_context_skill    # noqa: F401
from skills import focus_lock_skill        # noqa: F401
from skills import snippets_skill          # noqa: F401
from skills import auto_generated  # noqa: F401
from plugins import load_plugins as _load_community_plugins  # noqa: F401

__all__ = ["Skill", "all_skills", "dispatch", "get_skill", "toggle_skill",
           "unregister"]