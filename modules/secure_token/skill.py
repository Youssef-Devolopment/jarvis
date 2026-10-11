"""Secure Token module — cryptographic randomness for keys and tokens."""
import secrets
from skills.registry import register


@register("secure_token", [
    r"generate\s+(?:a\s+)?secure\s+(?:token|api[\s_]?key|secret)",
    r"(?:make|create|give me|show me)\s+(?:a\s+)?secure\s+"
    r"(?:token|api[\s_]?key|random\s+key)",
], "Generate secure random tokens with the OS cryptographic RNG")
def skill_secure_token(text, match):
    return ("Here's a fresh 43-character token: "
            + secrets.token_urlsafe(24)
            + " — made with the OS cryptographic RNG, safe to use as "
              "an API key or session token.")
