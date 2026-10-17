from __future__ import annotations

import re
from threading import Thread

from logger import get_logger

log = get_logger(__name__)
MAX_TURNS = 20

# Legacy reply-body plumbing banners (pre-1.20 the fallback notice was
# streamed as content, stored in history, and the model learned to
# echo it back verbatim — one old marker bred whole rows of copies).
_FALLBACK_MARK = re.compile(r"\[fallback to [^\]]+\]\s*")


def strip_plumbing(text: str) -> str:
    """Remove legacy bracket markers from a stored reply."""
    return _FALLBACK_MARK.sub("", text or "")


def clean_messages(rows) -> list[dict]:
    """Strip legacy bracket markers from stored rows; drop assistant
    rows that were nothing but markers. Extra keys (created_at…) and
    the original order are preserved."""
    out = []
    for m in rows:
        if m.get("role") not in ("user", "assistant"):
            continue
        body = strip_plumbing(m.get("content", ""))
        if m.get("role") == "assistant" and not body.strip():
            continue
        row = dict(m)
        row["content"] = body
        out.append(row)
    return out


class ConversationStore:
    def messages_for(self, sid: str, user_text: str) -> list[dict]:
        from memory import ensure_session, load_recent_messages, save_message
        ensure_session(sid)
        save_message(sid, "user", user_text)
        history = load_recent_messages(sid, limit=MAX_TURNS)
        clean = clean_messages(history)
        if len(clean) > MAX_TURNS:
            clean = clean[-MAX_TURNS:]
        return [{"role": "system", "content": ""}, *clean]

    def record_reply(self, sid: str, reply: str) -> None:
        reply = strip_plumbing(reply)
        if not reply:
            return
        from memory import save_message
        save_message(sid, "assistant", reply)

    def clear(self, sid: str) -> bool:
        from memory import clear_session
        return clear_session(sid) > 0


_store = None


def get_store() -> ConversationStore:
    global _store
    if _store is None:
        _store = ConversationStore()
    return _store


def extract_memory_async(user_text: str, assistant_text: str) -> None:
    def run():
        try:
            from memory import extract_and_store
            extract_and_store(user_text, assistant_text)
        except Exception as exc:
            log.debug("Memory extraction failed: %s", exc)
    Thread(target=run, daemon=True).start()
