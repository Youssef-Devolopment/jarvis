"""Autonomous app-learning engine — scan, launch, and TEACH itself.

When the user says "open <something>" and neither the resolver nor the
app index knows it, this module:

  1. deep-scans system paths on demand (cached1h, warmed in the
     background at boot):
       - %ProgramFiles% / %ProgramFiles(x86)%
       - %LocalAppData%\\Programs
       - Start Menu (user + all users) — .exe and .lnk (resolved)
       - every directory on %PATH%
  2. launches the found executable through the same safety gate as the
     launcher (instant apps open directly; others ask first);
  3. autonomously writes a brand-new ``@register`` skill into
     ``skills/auto_generated/app_<slug>.py`` following the repo's
     standard pattern, then **imports it immediately** — so the next
     "open <app>" is matched by the dedicated skill at the FRONT of
     the registry (instant, no restart). When the durable
     ``auto_approve_skills`` pref (memory prefs) is OFF, the generated
     code is staged in the shared approval pipeline instead and goes
     live only after "approve skill app_<slug>".

Stores:
  logs/app_scan.json      scan cache  (norm -> {name, path})
  logs/learned_apps.json  learned apps (norm -> {name, path, skill})

Nothing outside those stores and skills/auto_generated/ is written;
``forget()`` reverses everything.
"""
from __future__ import annotations

import importlib
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_SCAN_CACHE = _ROOT / "logs" / "app_scan.json"
_LEARNED = _ROOT / "logs" / "learned_apps.json"
_SKILL_DIR = _ROOT / "skills" / "auto_generated"
_TTL = 3600
_MAX_DEPTH = 5

_lock = threading.Lock()
_warm_thread: threading.Thread | None = None
_misses: set[str] = set()        # negative cache (per session)


# ---------------------------------------------------------------- helpers
def _norm(s: str) -> str:
    """'Visual Studio Code.exe' -> 'visualstudiocode'"""
    s = (s or "").strip().lower()
    for ext in (".exe", ".lnk", ".bat", ".cmd", ".com"):
        if s.endswith(ext):
            s = s[: -len(ext)]
    return re.sub(r"[^a-z0-9]", "", s)


def _slug(display: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (display or "app").lower()).strip("_")
    return s[:40] or "app"


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    except Exception as exc:
        log.warning("Could not write %s: %s", path.name, exc)


# ---------------------------------------------------------------- scanning
def _roots() -> list[Path]:
    out: list[Path] = []

    def add(p):
        try:
            if p and Path(p).is_dir():
                out.append(Path(p))
        except Exception:
            pass

    add(os.environ.get("ProgramFiles"))
    add(os.environ.get("ProgramFiles(x86)"))
    add(os.environ.get("ProgramW6432"))
    la = os.environ.get("LocalAppData")
    if la:
        add(Path(la) / "Programs")
    add(os.environ.get("AppData") and
        Path(os.environ["AppData"]) / "Microsoft" / "Windows" / "Start Menu")
    pd = os.environ.get("ProgramData")
    if pd:
        add(Path(pd) / "Microsoft" / "Windows" / "Start Menu")
    for entry in (os.environ.get("PATH") or "").split(os.pathsep):
        add(entry.strip())
    seen, uniq = set(), []
    for p in out:
        k = str(p).lower()
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return uniq


def _cache_fresh() -> bool:
    data = _load(_SCAN_CACHE)
    return bool(data.get("apps")) and \
        time.time() - data.get("ts", 0) < _TTL


def _scan_fresh() -> dict:
    """Bounded parallel walk of all roots. Returns norm -> {name, path}.

    Budgeted (dirs + files) so a cold scan can never hang the engine;
    roots run in parallel threads for speed.
    """
    import concurrent.futures as cf
    apps: dict[str, dict] = {}
    budget = {"left": 120_000}
    _skip = {"winsxs", "servicing", "assembly", "node_modules", ".git",
             "$recycle.bin", "windowsapps_cache", "common files",
             "reference assemblies", "dotnet", ".vs", "installer"}

    def walk_one(root: Path) -> dict[str, dict]:
        found: dict[str, dict] = {}
        base_depth = len(root.parts)
        try:
            for dirpath, dirnames, filenames in os.walk(
                    root, followlinks=False):
                if budget["left"] <= 0:
                    break
                depth = len(Path(dirpath).parts) - base_depth
                if depth >= _MAX_DEPTH:
                    dirnames[:] = []
                    continue
                dirnames[:] = [d for d in dirnames if d.lower() not in _skip]
                budget["left"] -= len(dirnames) + len(filenames)
                for fn in filenames:
                    low = fn.lower()
                    if not low.endswith((".exe", ".lnk")):
                        continue
                    if low.startswith(("unins", "uninstall", "setup_",
                                       "update")):
                        continue
                    full = Path(dirpath) / fn
                    path = str(full)
                    if low.endswith(".lnk"):
                        try:
                            from ai.app_index import _lnk_target
                            target = _lnk_target(full)
                            if target:
                                path = target
                        except Exception:
                            continue
                    display = Path(fn).stem
                    key = _norm(display)
                    if key and key not in found:
                        found[key] = {"name": display, "path": path}
        except Exception as exc:
            log.debug("scan walk failed for %s: %s", root, exc)
        return found

    roots = _roots()
    with cf.ThreadPoolExecutor(max_workers=min(8, max(1, len(roots)))) as ex:
        for part in ex.map(walk_one, roots):
            for k, v in part.items():
                if k not in apps:
                    apps[k] = v
    return apps


def scan(force: bool = False) -> dict:
    """Cached system scan (1h TTL). Thread-safe."""
    with _lock:
        if not force:
            data = _load(_SCAN_CACHE)
            if data.get("apps") and time.time() - data.get("ts", 0) < _TTL:
                return data["apps"]
        log.info("App learner: scanning system paths …")
        apps = _scan_fresh()
        _save(_SCAN_CACHE, {"ts": time.time(), "count": len(apps),
                            "apps": apps})
        log.info("App learner: indexed %d executables", len(apps))
        return apps


def warm() -> None:
    """Background warm-up (idempotent)."""
    global _warm_thread
    with _lock:
        if _warm_thread and _warm_thread.is_alive():
            return
        _warm_thread = threading.Thread(target=scan, name="app-learner",
                                        daemon=True)
        _warm_thread.start()


# ---------------------------------------------------------------- learned
def _learned_store() -> dict:
    return _load(_LEARNED).get("apps", {})


def learned_list() -> list[dict]:
    return sorted(_learned_store().values(), key=lambda d: d.get("name", ""))


def find(query: str) -> dict | None:
    """Learned apps first, then the scan cache (exact, then fuzzy).

    Fuzzy rules (kept strict on purpose): candidates must be at least
    4 chars, prefix matches win, containment needs >= 6 chars — so a
    tiny key like "app" can never hijack "totallyunknownappxyz".
    """
    q = _norm(query)
    if not q:
        return None
    learned = _learned_store().get(q)
    if learned:
        return dict(learned, source="learned")
    apps = scan()
    hit = apps.get(q)
    if hit:
        return dict(hit, source="scan")

    def unique(cands):
        return dict(cands[0], source="scan") if len(cands) == 1 else None

    if len(q) >= 4:
        got = unique([apps[k] for k in apps
                      if k.startswith(q) and len(k) >= 4])
        if got:
            return got
    # containment: the KEY must be substantial (>=6 chars) and a
    # substring of the query — tiny keys can never hijack a long query
    cont = [apps[k] for k in apps if len(k) >= 6 and k in q]
    return unique(cont)


# ---------------------------------------------------------------- skill gen
def _skill_path(display: str) -> Path:
    return _SKILL_DIR / f"app_{_slug(display)}.py"


def _skill_source(display: str, path: str) -> str:
    pattern = r"^(?:open|launch|start|run)\s+(?:the\s+)?(?:app\s+)?" \
              + re.escape(display.strip()) + r"[\?\.\!]?$"
    module = "app_" + _slug(display)
    return (
        "# Auto-learned by JARVIS (system/app_learner.py).\n"
        "# Safe: opens one known local application.\n"
        "from skills.registry import register\n"
        "\n"
        f"@register({module!r},\n"
        f"          [{pattern!r}],\n"
        f"          \"Open {display} (learned app)\", front=True)\n"
        f"def {module}(text, match):\n"
        "    from system.app_learner import launch_learned\n"
        f"    return launch_learned({path!r}, {display!r}) \\\n"
        "        or \"OK, not opening it.\"\n"
    )


def ensure_skill(display: str, path: str) -> tuple[str, bool]:
    """Stage or write the learned skill per the durable
    `auto_approve_skills` pref. Returns (module, created).

    Pref ON  -> write + hot-import immediately (instant skill).
    Pref OFF -> hand the generated code to the shared approval pipeline
                (skills/auto_generator.stage_candidate, trusted=True);
                the file only lands after "approve skill app_<slug>".
    The learned-app record is written either way, so launching keeps
    working while the skill waits for approval.
    """
    display = (display or "").strip()
    path = str(path)
    if not display or not path:
        raise ValueError("display and path are required")
    p = Path(path)
    if not p.exists():
        raise ValueError(f"target does not exist: {path}")
    if p.suffix.lower() not in (".exe", ".lnk", ".bat", ".cmd"):
        raise ValueError(f"refusing to learn non-executable: {p.suffix}")

    _SKILL_DIR.mkdir(parents=True, exist_ok=True)
    fp = _skill_path(display)
    want = _skill_source(display, path)
    created = not fp.exists()
    if not created and fp.read_text(encoding="utf-8", errors="replace") != want:
        created = True          # path moved: refresh the skill
    if created:
        from skills import auto_generator as ag
        if ag.auto_approve_enabled():
            fp.write_text(want, encoding="utf-8")
            ag.drop_pending(fp.stem)   # clear any stale approval entry
            log.info("App learner: wrote skill %s", fp.name)
        else:
            res = ag.stage_candidate(want, f"open {display}",
                                     trusted=True, execute=False)
            log.info("App learner: staged skill %s for approval "
                     "(test_ok=%s)", fp.name, res.get("test_ok"))

    if fp.exists():
        module = f"skills.auto_generated.{fp.stem}"
        try:
            if created and module in sys.modules:
                # content changed: swap the registration cleanly
                from skills.registry import unregister
                unregister(fp.stem)
                importlib.reload(sys.modules[module])
            else:
                __import__(module)  # instant registration, no restart
        except Exception as exc:
            log.warning("App learner: import %s failed: %s", module, exc)
    else:
        log.debug("App learner: %s awaiting approval", fp.stem)
    entry = {"name": display, "path": path, "skill": fp.stem,
             "learned_at": time.time()}
    with _lock:
        store = _load(_LEARNED)
        store.setdefault("apps", {})[_norm(display)] = entry
        _save(_LEARNED, store)
    return fp.stem, created


def forget(query: str) -> bool:
    """Reverse learning: drop the entry + skill file + registration."""
    key = _norm(query)
    with _lock:
        store = _load(_LEARNED)
        entry = store.get("apps", {}).pop(key, None)
        _save(_LEARNED, store)
    if not entry:
        # a fresh clone may ship the skill file without the store record
        fp = _skill_path(query)
        if not fp.exists():
            return False
        entry = {"skill": fp.stem}
    fp = _SKILL_DIR / f"{entry.get('skill', '')}.py"
    try:
        if fp.exists():
            fp.unlink()
    except Exception as exc:
        log.warning("App learner: could not remove %s: %s", fp.name, exc)
    try:
        from skills.registry import unregister
        unregister(entry.get("skill", ""))
    except Exception:
        pass
    try:
        from skills import auto_generator as ag
        ag.drop_pending(entry.get("skill", ""))   # staged copy, if any
    except Exception:
        pass
    log.info("App learner: forgot %s", query)
    return True


# ---------------------------------------------------------------- launching
def launch_learned(path: str, display: str, ask_fn=None) -> str | None:
    """Gate + launch a learned target. Returns output, or None if the
    user declined. Mirrors skills/app_launcher's safety flow."""
    from system import launch as L
    path, display = str(path), str(display)
    if not Path(path).exists():
        return f"{display} moved or was uninstalled — relearn it."
    if L.is_instant(path):
        out = L.launch_target(path)
    else:
        approved = False
        if ask_fn is not None:
            approved = bool(ask_fn(display))
        if not approved:
            return None
        out = L.launch_target(path)
    try:
        from memory import context as ctx
        ctx.log_event("app", f"launched {display} (learned)")
    except Exception:
        pass
    try:
        from skills.code_mode import _audit
        _audit("launch", path, True, display)
    except Exception:
        pass
    return out


def learn_and_launch(query: str, ask_fn=None) -> dict | None:
    """Main entry: find an UNLISTED app by deep scan, learn it, launch it.

    Returns None when nothing matches (caller keeps its error message).
    """
    hit = find(query)
    if not hit and _norm(query) not in _misses and not _cache_fresh():
        # miss + the cached scan is stale/absent -> one deep rescan
        apps = scan(force=True)
        hit = apps.get(_norm(query))
        if hit:
            hit = dict(hit, source="scan")
    if not hit:
        _misses.add(_norm(query))   # don't burn cycles on repeats
        return None
    display, path = hit["name"], hit["path"]
    created = False
    stem = None
    try:
        stem, created = ensure_skill(display, path)
    except Exception as exc:
        log.warning("App learner: could not learn %s: %s", display, exc)
    staged = False
    try:
        from skills.registry import get_skill
        staged = bool(created and stem and not get_skill(stem))
    except Exception:
        pass
    out = launch_learned(path, display, ask_fn=ask_fn)
    if out is None:
        return {"declined": True, "name": display, "path": path,
                "created": created, "staged": staged}
    return {"output": out, "name": display, "path": path,
            "created": created, "staged": staged,
            "source": hit.get("source", "scan")}
