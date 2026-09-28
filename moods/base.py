from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Mood:
    name: str
    description: str
    system_suffix: str
    temperature: float
    max_tokens: int
    voice_rate: str
    voice_pitch: str
    use_reasoner: bool = False
    prefer_fastest: bool = False
