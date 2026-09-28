"""After each exchange, ask the LLM to extract memorable facts."""
from __future__ import annotations
import json, re
from logger import get_logger
from memory.store import remember

log = get_logger(__name__)

_PROMPT = (
    "Extract 0 to 3 short, durable facts about the user from this conversation. "
    "Only facts that would still be true in a week: name, location, job, "
    "preferences, projects, relationships, ongoing goals. "
    "Do NOT extract: greetings, one-off questions, feelings, jokes. "
    "Return ONLY a JSON array like: "
    '["User name is Ali", "User is building a JARVIS assistant"] '
    "If nothing is worth remembering, return []"
)

_SUMMARY_PROMPT = (
    "Distill 0 to 3 durable facts about the user from this past "
    "conversation session. Same rules: only week-durable facts "
    "(identity, preferences, projects, goals). No greetings or one-offs. "
    "Return ONLY a JSON array of strings, or []"
)


def _call_extract(model: str, messages: list, max_tokens: int) -> list:
    from ai.client import get_client
    c = get_client()
    last_err = None
    for _ in range(2):  # one retry
        try:
            resp = c._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.0, max_tokens=max_tokens,
            )
            raw = (resp.choices[0].message.content or "").strip()
            raw = re.sub(r"^```(?:json)?|```$", "", raw,
                         flags=re.MULTILINE).strip()
            try:
                facts = json.loads(raw)
            except Exception:
                m = re.search(r"\[.*?\]", raw, re.DOTALL)
                facts = json.loads(m.group(0)) if m else []
            if isinstance(facts, list):
                return [f for f in facts if isinstance(f, str)]
            return []
        except Exception as exc:
            last_err = exc
    log.debug("Memory extraction failed after retry: %s", last_err)
    return []


def _store(facts: list, source: str) -> int:
    n = 0
    for f in facts[:3]:
        if isinstance(f, str) and len(f.strip()) > 3:
            try:
                if remember(f.strip(), category="auto", source=source):
                    n += 1
            except Exception:
                continue
    return n


def extract_and_store(user_text: str, assistant_text: str) -> int:
    try:
        from moods.router import FAST_MODEL
        facts = _call_extract(FAST_MODEL, [
            {"role": "system", "content": _PROMPT},
            {"role": "user",
             "content": f"USER: {user_text}\n\nASSISTANT: {assistant_text}"},
        ], max_tokens=200)
        return _store(facts, "auto_extract")
    except Exception as exc:
        log.debug("Memory extraction skipped: %s", exc)
        return 0


def summarize_and_store(messages: list) -> int:
    """Distill durable facts from a closing chat session."""
    try:
        msgs = [m for m in (messages or [])
                if m.get("role") in ("user", "assistant") and m.get("content")]
        if len(msgs) < 2:
            return 0
        lines = []
        for m in msgs[-30:]:
            who = "USER" if m["role"] == "user" else "JARVIS"
            lines.append(f"{who}: {str(m['content'])[:500]}")
        transcript = "\n".join(lines)[:6000]
        if not transcript.strip():
            return 0
        from moods.router import FAST_MODEL
        facts = _call_extract(FAST_MODEL, [
            {"role": "system", "content": _SUMMARY_PROMPT},
            {"role": "user", "content": transcript},
        ], max_tokens=250)
        return _store(facts, "session_summary")
    except Exception as exc:
        log.debug("Session summary skipped: %s", exc)
        return 0
