"""Library pack: pick one option at random."""
import random
from skills.registry import register


@register("random_pick", [
    r"^(?:randomly\s+)?(?:pick|choose|select)\s+(?:one\s+)?(?:from|between)\s+(?P<items>.+)$",
    r"^(?:what\s+should\s+i\s+(?:pick|choose)\s+from)\s+(?P<items>.+)$",
], "Let chance decide: 'pick between pizza, sushi'")
def skill_pick(text, match):
    raw = match.group("items").strip().rstrip("?.!")
    items = [i.strip() for i in raw.replace(" or ", ",").split(",") if i.strip()]
    if len(items) < 2:
        return None
    return f"I'd pick {random.choice(items)}."
