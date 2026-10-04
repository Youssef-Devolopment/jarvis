"""Preflight check — verify JARVIS is ready to run.
Usage: python check.py
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

results = []


def check(label, fn):
    try:
        detail = fn()
        results.append((True, label, detail or ""))
        print(f"{OK} {label}" + (f" — {detail}" if detail else ""))
    except Exception as exc:
        results.append((False, label, str(exc)[:120]))
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
        raise RuntimeError(".env not found")
    content = p.read_text(encoding="utf-8")
    if "sk-paste" in content:
        raise RuntimeError("API key still placeholder")
    return ".env OK"


def _config():
    from config import get_settings
    s = get_settings()
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


def main():
    print("\nJARVIS preflight check")
    print("=" * 50)

    check("Python version", _python_version)
    check("Virtual env", _venv)
    check("Required imports", _imports)
    check("Optional imports", _optional)
    check("Project directories", _dirs)
    check(".env file", _env_file)
    check("Config loads", _config)
    check("Memory store", _memory_store)
    check("Skill approval gate", _approval_gate)
    check("Chromium (Playwright)", _chromium)
    check("API key works", _api_key)

    print("=" * 50)
    passed = sum(1 for ok, _, _ in results if ok)
    total = len(results)
    if passed == total:
        print(f"\033[92mAll {total} checks passed. JARVIS is ready.\033[0m")
        print("\nRun: python run.py")
        return 0
    else:
        print(f"\033[93m{passed}/{total} passed. Fix the ✗ items above.\033[0m")
        print("\nDetails in logs/jarvis.log if you run anyway.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
