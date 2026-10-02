from __future__ import annotations
import re
from typing import Optional
from skills.base import Skill

_SKILLS = []


def register(name, patterns, description="", front=False):
    """Register a skill.

    front=True puts the skill at the FRONT of the dispatch order —
    used by auto-learned app skills so an exact "open <app>" match
    short-circuits the generic launch_app resolver.
    """
    compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
    def wrap(fn):
        skill = Skill(name=name, patterns=compiled, handler=fn,
                      description=description)
        if front:
            _SKILLS.insert(0, skill)
        else:
            _SKILLS.append(skill)
        return fn
    return wrap


def unregister(name):
    """Remove a skill by name (used when forgetting learned apps)."""
    before = len(_SKILLS)
    _SKILLS[:] = [s for s in _SKILLS if s.name != name]
    return len(_SKILLS) != before


def dispatch(text):
    for s in _SKILLS:
        if not s.enabled:
            continue
        m = s.match(text)
        if m:
            r = s.run(text, m)
            if r:
                return r
    return None


def all_skills():
    return list(_SKILLS)


def get_skill(name):
    for s in _SKILLS:
        if s.name == name:
            return s
    return None


def toggle_skill(name, enabled):
    s = get_skill(name)
    if not s:
        return False
    s.enabled = enabled
    return True