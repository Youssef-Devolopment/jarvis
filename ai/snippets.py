"""Snippet vault — save and retrieve code snippets."""

from __future__ import annotations
from logger import get_logger

log = get_logger(__name__)


def save(title, code, language="", tags=""):
    from memory import save_snippet
    sid = save_snippet(title, code, language, tags)
    return {"ok": bool(sid), "id": sid}


def list_all(query=""):
    from memory import list_snippets
    return list_snippets(query=query, limit=50)


def get(sid):
    from memory import get_snippet
    return get_snippet(sid)


def delete(sid):
    from memory import delete_snippet
    return delete_snippet(sid)
