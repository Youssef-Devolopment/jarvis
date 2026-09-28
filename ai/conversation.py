from __future__ import annotations
from threading import Thread
from logger import get_logger

log = get_logger(__name__)
MAX_TURNS = 20


class ConversationStore:
    def messages_for(self, sid: str, user_text: str) -> list[dict]:
        from memory import save_message, load_recent_messages, ensure_session
        ensure_session(sid)
        save_message(sid, "user", user_text)
        history = load_recent_messages(sid, limit=MAX_TURNS)
        clean = [m for m in history if m.get("role") in ("user", "assistant")]
        if len(clean) > MAX_TURNS:
            clean = clean[-MAX_TURNS:]
        return [{"role": "system", "content": ""}, *clean]

    def record_reply(self, sid: str, reply: str) -> None:
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
