"""Todoist API integration."""
from __future__ import annotations
import json
import os
import urllib.parse
import urllib.request
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)

BASE = "https://api.todoist.com/rest/v2"


def _key():
    return os.getenv("TODOIST_API_TOKEN", "").strip()


def _req(method: str, path: str, body: dict = None):
    key = _key()
    if not key:
        return None
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method,
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as exc:
        log.warning("Todoist failed: %s", exc)
        return None


@register("todoist_add", [
    r"^(?:add|create)\s+(?:a\s+)?todoist\s+task\s+(?P<task>.+?)[\?\.\!]?$",
    r"^add\s+to\s+todoist[:]\s+(?P<task2>.+?)[\?\.\!]?$",
], "Add Todoist task")
def s_add(text, m):
    gd = m.groupdict()
    task = (gd.get("task") or gd.get("task2") or "").strip()
    if not task:
        return None
    if not _key():
        return "Todoist token not set. Add TODOIST_API_TOKEN to .env."
    result = _req("POST", "/tasks", {"content": task})
    if result:
        return f"Added to Todoist: {task[:80]}"
    return "Todoist add failed."


@register("todoist_list", [
    r"^(?:what(?:'s| is)\s+on\s+)?(?:my\s+)?todoist\s+(?:tasks?|list)[\?\.\!]?$",
    r"^read\s+(?:my\s+)?todoist[\?\.\!]?$",
], "List Todoist tasks")
def s_list(text, m):
    if not _key():
        return "Todoist token not set."
    tasks = _req("GET", "/tasks")
    if not tasks:
        return "Todoist has no tasks."
    lines = [f"You have {len(tasks)} Todoist tasks:"]
    for t in tasks[:5]:
        lines.append(f"- {t.get('content', '')[:80]}")
    return " ".join(lines)
