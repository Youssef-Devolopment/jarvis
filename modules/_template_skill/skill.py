"""Skill module template — copy this folder, rename it, make it yours.

RULES (enforced by the validator, violations are rejected with a
plain-English reason BEFORE the file is ever imported):
- The folder name must equal the manifest's "id" (lowercase, digits,
  underscores).
- At least one @register(name, patterns) skill; 1-5 regex patterns
  each, literal arguments, no catch-alls, no hijacking everyday
  utterances ("hello", "help", ...).
- Allowed imports ONLY: skills, logger, re, json, math, datetime,
  urllib, html, time, random, secrets.
- No eval/exec/open/subprocess — handlers take (text, match) and
  return a short spoken string or None.

Full guide: MODULES.md in the repo root.
"""
from skills.registry import register


@register("my_module_skill", [
    r"^my module go[\?\.\!]?$",
], "What this skill does")
def skill_mine(text, match):
    return "It works — now make it yours."
