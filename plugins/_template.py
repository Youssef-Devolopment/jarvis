"""JARVIS plugin template — copy me to my_plugin.py and edit.

RULES (enforced by the loader, violations are rejected with a reason):
- File must live directly in plugins/ (no subfolders).
- Must contain at least one @register skill.
- Skill name: lowercase letters, digits, underscores (max 30 chars).
- 1-5 regex patterns (literals, compiled at load).
- Allowed imports ONLY: re, json, math, datetime, urllib.parse, html,
  time, random, secrets, plus `from skills.registry import register`.
  No files, no subprocess, no eval, no network beyond urllib reads.
- Handler: def anything(text, match) -> returns short spoken string
  or None when the request does not apply.

This file starts with _ so the loader SKIPS it. Rename to activate.
"""
from skills.registry import register


@register("my_skill", [
    r"^do something cool[\?\.\!]?$",
], "What my skill does")
def skill_mine(text, match):
    return "It works — now make it yours."
