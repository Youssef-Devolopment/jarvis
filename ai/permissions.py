"""Unified permission model — the single source of truth for what
any agent tool may do (principle 4, spec section 4).

One TABLE drives every enforcement context; contexts differ only in
HOW they ask, never in WHAT needs asking:
- chat loop  -> park for numbered consent ("allow N" / "deny N")
- OS missions -> voice/toast approval (autonomy_enabled context)

Capability vocabulary: fs:read, fs:write, fs:delete, shell:exec,
shell:exec:destructive, mcp:invoke, network:fetch, network:post.
Tiers: "auto" (runs free) or "confirm" (parks for consent).
Destructive shell text parks even in auto mode — auto never bypasses
explicit confirmation for destructive actions. Unknown names run
free: the closed dispatcher cannot execute them. Nothing here raises.
"""
from __future__ import annotations
import re
from logger import get_logger

log = get_logger(__name__)

AUTO = "auto"
CONFIRM = "confirm"

# tool -> {"caps": {...}, "tier": AUTO|CONFIRM, "timeout": seconds|None}.
# Timeout is metadata declaring the bound; enforcement lives where the
# call can actually overrun (term_* args, MCP runtime, computer_run).
# Local bounded tools carry None honestly instead of a fake number.
_CATALOG = {
    "remember_fact":      {"caps": set(),                "tier": AUTO,    "timeout": None},
    "switch_mood":        {"caps": set(),                "tier": AUTO,    "timeout": None},
    "read_own_code":      {"caps": {"fs:read"},          "tier": AUTO,    "timeout": None},
    "deep_search":        {"caps": {"network:fetch"},    "tier": AUTO,    "timeout": None},
    "silent_browse":      {"caps": {"network:fetch"},    "tier": AUTO,    "timeout": None},
    "silent_search":      {"caps": {"network:fetch"},    "tier": AUTO,    "timeout": None},
    "silent_read":        {"caps": {"network:fetch"},    "tier": AUTO,    "timeout": None},
    "silent_click":       {"caps": {"network:fetch"},    "tier": AUTO,    "timeout": None},
    "fs_read":            {"caps": {"fs:read"},          "tier": AUTO,    "timeout": None},
    "fs_list":            {"caps": {"fs:read"},          "tier": AUTO,    "timeout": None},
    "fs_search":          {"caps": {"fs:read"},          "tier": AUTO,    "timeout": None},
    "list_open_apps":     {"caps": set(),                "tier": AUTO,    "timeout": None},
    "read_screen":        {"caps": set(),                "tier": AUTO,    "timeout": None},
    "folder_watch":       {"caps": set(),                "tier": AUTO,    "timeout": None},
    "folder_unwatch":     {"caps": set(),                "tier": AUTO,    "timeout": None},
    "open_url":           {"caps": {"network:fetch"},    "tier": AUTO,    "timeout": None},
    "outcome_stats":      {"caps": set(),                "tier": AUTO,    "timeout": None},
    "reality_check_tool": {"caps": set(),                "tier": AUTO,    "timeout": None},
    "fs_write":           {"caps": {"fs:write"},         "tier": CONFIRM, "timeout": None},
    "fs_append":          {"caps": {"fs:write"},         "tier": CONFIRM, "timeout": None},
    "fs_replace":         {"caps": {"fs:write"},         "tier": CONFIRM, "timeout": None},
    "fs_mkdir":           {"caps": {"fs:write"},         "tier": CONFIRM, "timeout": None},
    "fs_delete":          {"caps": {"fs:delete"},        "tier": CONFIRM, "timeout": None},
    "term_run":           {"caps": {"shell:exec"},       "tier": CONFIRM, "timeout": 30},
    "term_python":        {"caps": {"shell:exec"},       "tier": CONFIRM, "timeout": 30},
    "focus_app":          {"caps": set(),                "tier": CONFIRM, "timeout": None},
    "launch_app":         {"caps": set(),                "tier": CONFIRM, "timeout": None},
    "win_click":          {"caps": set(),                "tier": CONFIRM, "timeout": None},
    "win_type":           {"caps": set(),                "tier": CONFIRM, "timeout": None},
    "bridge_transfer":    {"caps": {"network:post"},     "tier": CONFIRM, "timeout": None},
    "computer_run":       {"caps": {"shell:exec"},       "tier": CONFIRM, "timeout": 120},
}

# Dynamic third-party tools: unknown side effects => confirm.
_MCP_TIER = CONFIRM
_MCP_CAPS = {"mcp:invoke"}
_MCP_TIMEOUT = 60

# Destructive shell text parks even in auto mode — auto never
# silently bypasses confirmation.  Matching is per command segment
# (split on ; | & and newlines): the dangerous verb must BE the
# command, not a word inside a sentence ("echo diskpart is a tool"
# must not match).  "dd ... of=" is the exception — the target can
# sit anywhere in its segment.
_SEG_SPLIT = re.compile(r"[;|&\n]+")
_SUDO_PREFIX = r"(sudo\s+|runas\s+/user:\S+\s+)?"
_DESTRUCTIVE_FIRST = [
    re.compile(_SUDO_PREFIX + r"rm\s+.*-[a-z]*r[a-z]*\s+"
               r"((/|~|/\*)($|\s)|--no-preserve-root)"),
    re.compile(_SUDO_PREFIX + r"format\s+[a-zA-Z]:"),
    re.compile(_SUDO_PREFIX + r"(deltree|mkfs(\.\w+)?|diskpart|bcdedit)\b"),
    re.compile(_SUDO_PREFIX + r"shutdown\s+/[sr]\b"),
    re.compile(_SUDO_PREFIX + r"del\s+/[sfq]\S*\s+.*(windows|system32)"),
    re.compile(_SUDO_PREFIX + r"rmdir\s+/[sq]\S*\s+.*(windows|system32)"),
    re.compile(_SUDO_PREFIX + r"reg\s+delete\s+hklm\b"),
]
_DESTRUCTIVE_ANYWHERE = [
    re.compile(r"\bdd\s+[^;|&]*\bof="),
]


def tier_of(name: str) -> str:
    """AUTO or CONFIRM. Unknown and empty names are AUTO: the
    dispatcher is a closed if-chain plus the mcp__ prefix, so a name
    with no entry cannot execute anything — it returns an "Unknown
    tool" string that lets the model self-correct instead of
    pestering the user about a hallucination."""
    if not isinstance(name, str) or not name:
        return AUTO
    if name.startswith("mcp__"):
        return _MCP_TIER
    entry = _CATALOG.get(name)
    if entry is None:
        return AUTO
    return entry["tier"]


def capabilities_of(name: str) -> set:
    if not isinstance(name, str) or not name:
        return set()
    if name.startswith("mcp__"):
        return set(_MCP_CAPS)
    entry = _CATALOG.get(name)
    return set(entry["caps"]) if entry else set()


def timeout_of(name: str):
    if not isinstance(name, str) or not name:
        return None
    if name.startswith("mcp__"):
        return _MCP_TIMEOUT
    entry = _CATALOG.get(name)
    return entry["timeout"] if entry else None


def is_destructive(name: str, args: dict) -> bool:
    """True when a shell call's text IS a destructive command (not a
    mere mention of one)."""
    if name not in ("term_run", "term_python"):
        return False
    try:
        text = str((args or {}).get("command",
                                    (args or {}).get("code", "")))
    except Exception:
        return False
    low = text.lower()
    if any(rx.search(low) for rx in _DESTRUCTIVE_ANYWHERE):
        return True
    for seg in _SEG_SPLIT.split(low):
        seg = seg.strip()
        if seg and any(rx.match(seg) for rx in _DESTRUCTIVE_FIRST):
            return True
    return False


def decide(name: str, args: dict, mode: str) -> str:
    """Single decision for every context: "run" or "park".

    - destructive shell text parks even in auto mode;
    - confirm-tier parks only in ask mode;
    - everything else runs.
    """
    if is_destructive(name, args):
        return "park"
    if tier_of(name) == CONFIRM and mode != AUTO:
        return "park"
    return "run"


def auto_tools() -> frozenset:
    """Free-tier tool names (OS-mission AUTO set is this view)."""
    return frozenset(n for n, e in _CATALOG.items()
                     if e["tier"] == AUTO)


def confirm_tools() -> frozenset:
    """Confirm-tier tool names (chat consent set is this view)."""
    return frozenset(n for n, e in _CATALOG.items()
                     if e["tier"] == CONFIRM)
