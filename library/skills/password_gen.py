"""Library pack: strong random passwords (crypto RNG)."""
import random
import secrets
from skills.registry import register

_LOWER = "abcdefghijkmnopqrstuvwxyz"
_UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ"
_DIGITS = "23456789"
_SYMBOLS = "!@#$%^&*()-_=+[]{};:,.?"


@register("password_gen", [
    r"^(?:generate|make|create|new)\s+(?:a\s+)?(?:strong\s+)?password(?:\s+(?:of\s+)?(?P<n>\d{1,3})\s*(?:chars|characters?)?)?[\?\.\!]?$",
    r"^password\s+(?P<n>\d{1,3})$",
], "Strong password: 'generate password 20'")
def skill_password(text, match):
    g = match.groupdict()
    n = int(g["n"]) if g.get("n") else 16
    n = max(8, min(64, n))
    chars = []
    chars.append(secrets.choice(_LOWER))
    chars.append(secrets.choice(_UPPER))
    chars.append(secrets.choice(_DIGITS))
    chars.append(secrets.choice(_SYMBOLS))
    pool = _LOWER + _UPPER + _DIGITS + _SYMBOLS
    while len(chars) < n:
        chars.append(secrets.choice(pool))
    random.SystemRandom().shuffle(chars)
    return "Your password: " + "".join(chars)
