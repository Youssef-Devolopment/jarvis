"""Remember a fact — persists it into the core SQLite memory store.

Writes text + timestamp + source into memory/jarvis_memory.db (facts
table) so it survives restarts and is recalled automatically:
  - `facts_block()` injects recent facts into the LLM system prompt
    (ai/client.py), and
  - `memory.recall(query)` ranks them for "what did I tell you about X".
If the database is unreachable, a JSON sidecar
(memory/user_notes.json) keeps the note so nothing is ever lost.
"""
from skills.registry import register


@register("remember", [
    r"(?i)^\s*(?:please\s+)?rem(?:ember|ind me)(?:\s+that)?\s*[:,]?\s*(?P<fact>.+?)\s*$",
    r"(?i)^\s*(?:please\s+)?(?:make a note|note|keep in mind)(?:\s+that)?\s*[:,]?\s*(?P<fact>.+?)\s*$",
    r"(?i)^\s*(?:don'?t forget|never forget)\s*[:,]?\s*(?P<fact>.+?)\s*$",
], "Persists a fact the user asks to store (core memory database)")
def remember(text, match):
    fact = (match.group("fact") or "").strip(" .,!?:;-")
    if not fact:
        return None
    if len(fact) > 500:
        fact = fact[:500].rstrip() + "..."
    try:
        from memory import remember as store_remember
        fid = store_remember(fact, category="general",
                             source="skill:remember")
        if fid:
            return f'Saved to memory: "{fact}". I\'ll recall it later.'
        return None    # too short to store — let other skills handle it
    except Exception:
        # Durable fallback: append to a JSON sidecar in memory/
        try:
            import json
            from datetime import datetime
            from pathlib import Path
            p = Path(__file__).resolve().parents[2] / "memory" / \
                "user_notes.json"
            notes = []
            if p.exists():
                notes = json.loads(p.read_text(encoding="utf-8"))
            notes.append({"fact": fact,
                          "ts": datetime.now().isoformat(
                              timespec="seconds"),
                          "source": "skill:remember"})
            p.write_text(json.dumps(notes, ensure_ascii=False, indent=1),
                         encoding="utf-8")
            return f'Noted (JSON fallback): "{fact}".'
        except Exception:
            return "I could not store that — memory write failed."
