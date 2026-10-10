"""Preflight check — verify JARVIS is ready to run.
Usage: python check.py

Exit codes (what setup scripts and humans branch on):
  0  ready — core passed (optional gaps and/or skills-only mode are
     reported as capabilities, not failures)
  1  core broken — JARVIS will not start until these are fixed
  2  core OK, key missing/invalid — JARVIS starts in skills-only mode;
     AI chat unlocks after Setup -> GENERAL (or .env) gets a key
"""
from __future__ import annotations
import importlib
import os
import subprocess
import sys
from pathlib import Path

OK = "\033[92m✓\033[0m"
BAD = "\033[91m✗\033[0m"
WARN = "\033[93m!\033[0m"

results = []   # (ok, label, detail, bucket)

# Buckets: core = must pass to run, key = AI chat readiness,
# optional = features that degrade gracefully.
OPTIONAL_LABELS = {"Optional imports", "Chromium (Playwright)"}
KEY_LABELS = {"API key works"}


def bucket(label: str) -> str:
    if label in OPTIONAL_LABELS:
        return "optional"
    if label in KEY_LABELS:
        return "key"
    return "core"


def check(label, fn):
    try:
        detail = fn()
        results.append((True, label, detail or "", bucket(label)))
        print(f"{OK} {label}" + (f" — {detail}" if detail else ""))
    except Exception as exc:
        results.append((False, label, str(exc)[:120], bucket(label)))
        print(f"{BAD} {label} — {exc}")


def _python_version():
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 10):
        raise RuntimeError(f"Python {v.major}.{v.minor} too old (need 3.10+)")
    return f"{v.major}.{v.minor}.{v.micro}"


def _venv():
    if not hasattr(sys, "real_prefix") and not hasattr(sys, "base_prefix"):
        return "not in venv"
    if sys.prefix == sys.base_prefix:
        raise RuntimeError("venv not activated")
    return "active"


def _imports():
    missing = []
    for mod in ["flask", "dotenv", "openai", "edge_tts", "pygame"]:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        raise RuntimeError(f"missing: {', '.join(missing)}")
    return "flask, openai, edge-tts, pygame"


def _optional():
    found = []
    for mod in ["faster_whisper", "sounddevice", "playwright", "numpy"]:
        try:
            importlib.import_module(mod)
            found.append(mod)
        except ImportError:
            pass
    return ", ".join(found) if found else "none installed"


def _env_file():
    p = Path(".env")
    if not p.exists():
        raise RuntimeError(".env not found (copy .env.example to .env)")
    content = p.read_text(encoding="utf-8")
    if "sk-paste" in content:
        return ".env found (API key still the template placeholder)"
    return ".env OK"


def _config():
    # Lenient on purpose: a missing key is the KEY check's job, and a
    # fresh install must be able to say "config loads, key pending".
    from config import Settings, try_settings
    s = try_settings()
    if s is None:
        s = Settings.load(require_key=False)
        return f"model={s.model}, voice={s.voice_name} (skills-only)"
    return f"model={s.model}, voice={s.voice_name}"


def _chromium():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("playwright not installed")
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            b.close()
        return "chromium OK"
    except Exception as exc:
        msg = str(exc)
        if "Executable doesn't exist" in msg:
            raise RuntimeError("Run: playwright install chromium")
        raise RuntimeError(msg[:100])


def _api_key():
    from config import get_settings
    from openai import OpenAI
    s = get_settings()
    c = OpenAI(api_key=s.api_key, base_url=s.base_url)
    r = c.models.list()
    return f"key valid — {len(r.data)} models available"


def _dirs():
    needed = ["logs", "voice", "ai", "skills", "moods", "memory", "routes",
              "templates", "static"]
    missing = [d for d in needed if not Path(d).exists()]
    if missing:
        raise RuntimeError(f"missing: {', '.join(missing)}")
    return f"{len(needed)} directories present"


def _memory_store():
    from memory import count_facts
    n = count_facts()                      # opens/creates the SQLite DB
    return f"sqlite OK - {n} facts"


def _approval_gate():
    from skills import auto_generator as ag
    state = "ON" if ag.auto_approve_enabled() else "OFF"
    return f"auto-approve {state}, {len(ag.list_pending())} pending"


CHECKS = [
    ("Python version", _python_version),
    ("Virtual env", _venv),
    ("Required imports", _imports),
    ("Optional imports", _optional),
    ("Project directories", _dirs),
    (".env file", _env_file),
    ("Config loads", _config),
    ("Memory store", _memory_store),
    ("Skill approval gate", _approval_gate),
    ("Chromium (Playwright)", _chromium),
    ("API key works", _api_key),
]

# One actionable next step per check — printed only when that check
# failed, so nobody has to guess what "✗ Config loads" means.
HINTS = {
    "Python version": "Install Python 3.10+ from python.org "
                      "(check 'Add python.exe to PATH') and re-run setup.",
    "Virtual env": "Run from inside the repo with .venv active "
                   "(or re-run setup.ps1).",
    "Required imports": ".venv\\Scripts\\python.exe -m pip install "
                        "-r requirements.txt",
    "Optional imports": "Voice/mic extras: pip install -r "
                        "requirements-voice.txt",
    "Project directories": "The checkout is incomplete — re-clone the repo.",
    ".env file": "Copy .env.example to .env (or re-run setup.ps1).",
    "Config loads": "Fix the reported line in .env "
                    "(see comments in .env.example).",
    "Memory store": "Check disk permissions; if the DB is corrupt, "
                    "restore the newest backup from memory/backups\\.",
    "Skill approval gate": "Check logs/auto_skills/pending.json "
                           "(it must be valid JSON).",
    "Chromium (Playwright)": ".venv\\Scripts\\python.exe -m playwright "
                             "install chromium",
    "API key works": "Settings -> GENERAL -> paste DEEPSEEK_API_KEY -> "
                     "SAVE+TEST (or fix DEEPSEEK_BASE_URL in .env).",
}


def verdict(res):
    """Classify results -> {code, core, key, optional} (see module doc)."""
    core = [r for r in res if not r[0] and r[3] == "core"]
    key = [r for r in res if not r[0] and r[3] == "key"]
    optional = [r for r in res if not r[0] and r[3] == "optional"]
    if core:
        code = 1
    elif key:
        code = 2
    else:
        code = 0
    return {"code": code, "core": core, "key": key, "optional": optional}


def capability_lines(res):
    """What actually works right now — the product-facing summary."""
    ok = {label: bool(o) for o, label, _d, _b in res}
    det = {label: (d or "") for _o, label, d, _b in res}
    llm = ok.get("API key works", False)
    mic = "sounddevice" in det.get("Optional imports", "")
    browser = ok.get("Chromium (Playwright)", False)
    rows = [
        ("AI chat", "on" if llm else
         "off — skills-only mode (add DEEPSEEK_API_KEY)"),
        ("Voice input", "on" if mic else
         "off — needs requirements-voice.txt"),
        ("Browser skills", "on" if browser else
         "off — run: python -m playwright install chromium"),
        ("Memory", det.get("Memory store") or "unavailable"),
    ]
    out = ["  Capabilities:"]
    for name, val in rows:
        out.append(f"    {name:<16}: {val}")
    return out


def main():
    print("\nJARVIS preflight check")
    print("=" * 50)
    for label, fn in CHECKS:
        check(label, fn)
    print("=" * 50)

    v = verdict(results)
    for line in capability_lines(results):
        print(line)
    print()

    if v["code"] == 1:
        print(f"{BAD} Core checks failed — JARVIS will not start until "
              "these are fixed:")
        for _ok, label, detail, _b in v["core"]:
            print(f"    {label}: {detail}")
            if label in HINTS:
                print(f"      fix: {HINTS[label]}")
        return 1
    if v["code"] == 2:
        print(f"{WARN} Core checks passed — but there is no working API key.")
        print("    JARVIS starts in SKILLS-ONLY mode: local skills, memory,")
        print("    reminders and the HUD all work; AI chat stays off.")
        for _ok, label, detail, _b in v["key"]:
            print(f"    {label}: {detail}")
        if "API key works" in HINTS:
            print(f"    fix: {HINTS['API key works']}")
        return 2
    if v["optional"]:
        print(f"{WARN} Ready — optional features unavailable:")
        for _ok, label, detail, _b in v["optional"]:
            print(f"    {label}: {detail}")
            if label in HINTS:
                print(f"      fix: {HINTS[label]}")
    else:
        total = len(results)
        print(f"\033[92mAll {total} checks passed. JARVIS is ready.\033[0m")
    print("\nStart: python run.py   (or desktop.bat for tray mode)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
