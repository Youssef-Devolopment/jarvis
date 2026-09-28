from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Callable, Optional
from logger import get_logger

log = get_logger(__name__)
Handler = Callable[[str, "re.Match"], Optional[str]]


@dataclass
class Skill:
    name: str
    patterns: list
    handler: Handler
    description: str = ""
    enabled: bool = True

    def match(self, text: str):
        for p in self.patterns:
            m = p.search(text)
            if m:
                return m
        return None

    def run(self, text: str, match) -> Optional[str]:
        try:
            r = self.handler(text, match)
            if r:
                log.info("skill=%-14s in=%r out=%r", self.name, text, r)
            return r
        except Exception:
            log.exception("Skill '%s' raised", self.name)
            return None
