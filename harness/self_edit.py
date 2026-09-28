"""Self-edit proposals. Writes require user approval."""
from __future__ import annotations
import difflib, shutil, uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from logger import get_logger
from harness.self_read import _safe_path, read_file

log = get_logger(__name__)
_ROOT = Path(__file__).resolve().parent.parent
_BACKUPS = _ROOT / "logs" / "backups"
_BACKUPS.mkdir(parents=True, exist_ok=True)
_PROTECTED = {".env", "run.py", "config.py"}
_PROPOSALS: dict[str, dict] = {}


def propose(file: str, old_text: str, new_text: str, reason: str = "") -> dict:
    if file in _PROTECTED:
        return {"error": f"{file} is protected and cannot be edited."}
    current = read_file(file)
    if current.startswith("[harness] Not allowed"):
        return {"error": current}
    if old_text not in current:
        return {"error": "old_text not found in file."}
    updated = current.replace(old_text, new_text, 1)
    diff_lines = list(difflib.unified_diff(
        current.splitlines(), updated.splitlines(),
        fromfile=f"a/{file}", tofile=f"b/{file}", lineterm=""))
    pid = uuid.uuid4().hex[:10]
    _PROPOSALS[pid] = {
        "id": pid, "file": file, "reason": reason,
        "diff": "\n".join(diff_lines),
        "old_text": old_text, "new_text": new_text,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": "pending",
    }
    log.info("Edit proposed: %s (%s)", file, pid)
    return {k: v for k, v in _PROPOSALS[pid].items() if k not in ("old_text", "new_text")}


def apply(proposal_id: str) -> dict:
    p = _PROPOSALS.get(proposal_id)
    if not p:
        return {"error": "Unknown proposal."}
    if p["status"] != "pending":
        return {"error": f"Proposal is {p['status']}."}
    path = _safe_path(p["file"])
    if path is None:
        return {"error": "File not allowed."}
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = _BACKUPS / f"{p['file'].replace('/', '__')}.{ts}.bak"
    shutil.copy2(path, backup)
    current = path.read_text(encoding="utf-8")
    updated = current.replace(p["old_text"], p["new_text"], 1)
    path.write_text(updated, encoding="utf-8")
    p["status"] = "applied"
    log.info("Applied: %s", p["file"])
    return {"ok": True, "file": p["file"], "backup": str(backup)}


def reject(proposal_id: str) -> dict:
    p = _PROPOSALS.get(proposal_id)
    if not p:
        return {"error": "Unknown proposal."}
    p["status"] = "rejected"
    return {"ok": True}


def pending() -> list[dict]:
    return [{k: v for k, v in p.items() if k not in ("old_text", "new_text")}
            for p in _PROPOSALS.values() if p["status"] == "pending"]


def get(proposal_id: str):
    return _PROPOSALS.get(proposal_id)
