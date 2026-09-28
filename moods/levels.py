"""8 escalation levels for JARVIS."""

from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum


class Level(IntEnum):
    INSTANT = 1      # no LLM, local skill
    QUICK = 2        # 1 fast model
    STANDARD = 3     # 1 chat model
    DEEP = 4         # 1 reasoner model
    COUNCIL = 5      # 3 models + moderator
    COUNCIL_PLUS = 6 # 5 models + moderator + validator
    COUNCIL_MAX = 7  # 7 models + moderator + validator + critic
    COUNCIL_XTREME = 8  # 10 models + full stack


@dataclass(frozen=True)
class LevelSpec:
    level: Level
    name: str
    model_count: int
    models: tuple
    moderator_model: str
    timeout_sec: int
    estimated_cost_usd: float


LEVEL_SPECS = {
    Level.INSTANT: LevelSpec(
        Level.INSTANT, "instant", 0, (), "", 1, 0.0),
    Level.QUICK: LevelSpec(
        Level.QUICK, "quick", 1,
        ("deepseek-v4.1-flash:free",),
        "", 8, 0.0005),
    Level.STANDARD: LevelSpec(
        Level.STANDARD, "standard", 1,
        ("deepseek-v4-flash:free",),
        "", 15, 0.002),
    Level.DEEP: LevelSpec(
        Level.DEEP, "deep", 1,
        ("deepseek-v3.2",),
        "", 30, 0.006),
    Level.COUNCIL: LevelSpec(
        Level.COUNCIL, "council", 3,
        ("deepseek-v4.1-flash:free",
         "deepseek-v4-pro",
         "gemini-3.8-flash"),
        "deepseek-v4-pro", 45, 0.02),
    Level.COUNCIL_PLUS: LevelSpec(
        Level.COUNCIL_PLUS, "council+", 5,
        ("deepseek-v4.1-flash:free",
         "deepseek-v4-pro",
         "gemini-3.8-flash",
         "gpt-6-astra",
         "mimo-v2.5:free"),
        "deepseek-v4-pro", 60, 0.05),
    Level.COUNCIL_MAX: LevelSpec(
        Level.COUNCIL_MAX, "council max", 7,
        ("deepseek-v4.1-flash:free",
         "deepseek-v4-flash:free",
         "deepseek-v4-pro",
         "gemini-3.8-flash",
         "gpt-6-astra",
         "claude-sonnet-5",
         "mimo-v2.5:free"),
        "deepseek-v4-pro", 75, 0.10),
    Level.COUNCIL_XTREME: LevelSpec(
        Level.COUNCIL_XTREME, "council xtreme", 10,
        ("deepseek-v4.1-flash:free",
         "deepseek-v4-flash:free",
         "deepseek-v3.2",
         "deepseek-v4-pro",
         "gemini-3.8-flash",
         "gpt-6-astra",
         "claude-sonnet-5",
         "mimo-v2.5:free",
         "mimo-v2.6-flash:free",
         "qwen3.8-flash:free"),
        "deepseek-v4-pro", 90, 0.15),
}
