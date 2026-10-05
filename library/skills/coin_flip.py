"""Library pack: coin flip."""
import random
from skills.registry import register


@register("coin_flip", [
    r"^(?:flip\s+)?a\s+coin$",
    r"^flip\s+(?:the\s+)?coin$",
    r"^heads\s+or\s+tails[\?\.\!]?$",
], "Flip a coin: heads or tails")
def skill_coin(text, match):
    return "Heads!" if random.random() < 0.5 else "Tails!"
