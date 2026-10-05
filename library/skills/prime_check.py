"""Library pack: primality check with smallest factor."""
import math
from skills.registry import register


def _factor(n):
    if n % 2 == 0:
        return 2
    i = 3
    while i <= math.isqrt(n):
        if n % i == 0:
            return i
        i += 2
    return None


@register("prime_check", [
    r"^(?:is\s+)?(?P<n>\d{1,9})\s+prime[\?\.\!]?$",
    r"^check\s+(?:if\s+)?(?:the\s+)?(?:number\s+)?(?P<n>\d{1,9})\s+is\s+prime$",
], "Primes: 'is 97 prime'")
def skill_prime(text, match):
    n = int(match.group("n"))
    if n < 2:
        return f"{n} is not prime (primes start at 2)."
    f = _factor(n)
    if f is None:
        return f"Yes — {n} is prime."
    other = n // f
    return f"No — {n} = {f} × {other}."
