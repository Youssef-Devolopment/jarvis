"""Toggle the durable auto-approve gate for new skills.

Reads/writes the `auto_approve_skills` pref in the core configuration
store (memory prefs -> memory/jarvis_memory.db), the SAME flag
skills/auto_generator checks before registering a candidate:

  ON  -> code that passes validation + the isolation test registers
         immediately (LLM drafts and app-learner skills alike);
         anything failing a test still waits for explicit approval.
  OFF -> every new skill waits for "approve skill <name>".

State survives restarts; the previous in-memory flag is gone.
"""
from skills.registry import register

_OFF_WORDS = ("disable", "turn off", "switch off", "deactivate",
              "stop", "don't", "do not", "cancel", "require approval",
              "no auto")
_ON_WORDS = ("enable", "turn on", "switch on", "activate",
             "allow auto", "start auto")


@register("auto_approve_skills", [
    r"\bauto[- ]?approv\w*\b.*\bskills?\b",
    r"\bskills?\b.*\bauto[- ]?approv\w*\b",
    r"\bapprove\s+(?:all\s+)?new\s+skills?\b",
], "Enable/disable auto-approval of new skills (durable setting)")
def auto_approve_skills(text, match):
    from skills.auto_generator import (auto_approve_enabled,
                                       set_auto_approve_enabled)
    t = (text or "").lower()

    if any(w in t for w in _OFF_WORDS):
        set_auto_approve_enabled(False)
        return ("Auto-approval for new skills is now OFF. "
                "Every new skill will wait for your explicit "
                "'approve skill <name>' confirmation.")

    if any(w in t for w in _ON_WORDS):
        set_auto_approve_enabled(True)
        return ("Auto-approval for new skills is ON. New skills that "
                "pass validation and testing register immediately; "
                "anything failing a test still asks you first.")

    status = "ON" if auto_approve_enabled() else "OFF"
    return (f"Auto-approval for new skills is currently {status}. "
            f"Say 'enable auto approve skills' or "
            f"'disable auto approve skills' to change it.")
