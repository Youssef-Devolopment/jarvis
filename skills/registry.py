from __future__ import annotations
import re
from typing import Optional
from skills.base import Skill

_SKILLS = []


def register(name, patterns, description=""):
    compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
    def wrap(fn):
        _SKILLS.append(Skill(name=name, patterns=compiled, handler=fn,
                             description=description))
        return fn
    return wrap


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