from skills.registry import register

_STATE = {"auto": True}

@register("auto_approve_skills", [
    r"\bauto[- ]?approv\w*\b.*\bskills?\b",
    r"\bskills?\b.*\bauto[- ]?approv\w*\b",
    r"\bapprove\s+(?:all\s+)?new\s+skills?\b",
], "Enables or reports automatic approval of newly created skills")
def auto_approve_skills(text, match):
    t = text.lower()

    off_words = ("disable", "turn off", "deactivate", "stop", "don't",
                 "do not", "cancel", "no auto")
    on_words = ("enable", "turn on", "activate", "allow", "start",
                "set up", "make it", "auto approve", "auto-approve")

    if any(w in t for w in off_words):
        _STATE["auto"] = False
        return ("Auto-approval for new skills is now off. "
                "Each new skill will wait for your confirmation before it goes live.")

    if any(w in t for w in on_words):
        _STATE["auto"] = True
        return ("Auto-approval for new skills is on. "
                "Any skill I register from now on is approved immediately.")

    status = "on" if _STATE["auto"] else "off"
    return ("Auto-approval for new skills is currently {}. "
            "Say 'disable auto approve skills' or 'enable auto approve skills' to change it."
            ).format(status)