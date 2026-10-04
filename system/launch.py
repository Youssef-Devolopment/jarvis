"""Universal open — ANY app, ANY url. Single source of truth.

Apps resolve through layers: curated aliases -> Start Menu (.lnk names)
-> PATH (where.exe) -> Registry App Paths. Fuzzy matching with
"did you mean" instead of guessing. Safe-listed apps launch instantly;
everything else is confirmed first by the caller. URLs are normalized,
scheme-checked (http/https only), and opened as REAL tabs.
"""
from __future__ import annotations
import difflib
import os
import platform
import shutil
import subprocess
import webbrowser
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)
IS_WIN = platform.system() == "Windows"

# Instant-launch, no confirmation (harmless viewers/managers).
SAFE_INSTANT = {
    "notepad.exe", "calc.exe", "mspaint.exe", "explorer.exe",
    "taskmgr.exe", "control.exe", "msedge.exe", "chrome.exe",
    "brave.exe", "firefox.exe",
}

ALIASES = {
    "notepad": "notepad.exe", "calculator": "calc.exe", "calc": "calc.exe",
    "paint": "mspaint.exe", "explorer": "explorer.exe",
    "file explorer": "explorer.exe", "files": "explorer.exe",
    "task manager": "taskmgr.exe", "control panel": "control.exe",
    "settings": "ms-settings:", "vs code": "code", "vscode": "code",
    "code": "code", "spotify": "spotify.exe", "discord": "discord.exe",
    "chrome": "chrome.exe", "edge": "msedge.exe", "brave": "brave.exe",
    "firefox": "firefox.exe", "whatsapp": "WhatsApp.exe",
    "telegram": "Telegram.exe", "steam": "steam.exe", "obs": "obs64.exe",
    "vlc": "vlc.exe", "cmd": "cmd.exe", "terminal": "wt.exe",
    "powershell": "powershell.exe", "notepad++": "notepad++.exe",
    "notion": "Notion.exe", "slack": "slack.exe", "zoom": "Zoom.exe",
    "obsidian": "obsidian.exe", "everything": "Everything.exe",
    "snipping tool": "snippingtool.exe", "snip": "snippingtool.exe",
}


def _obsidian_target() -> str:
    """Vault-aware deep link when a vault is configured, else exe."""
    try:
        from config import try_settings
        s = try_settings()
        vault = (s.obsidian_vault if s else "") or ""
        vault = vault.strip().rstrip("/\\")
        if vault:
            import urllib.parse
            name = vault.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
            if name:
                return ("obsidian://open?vault="
                        + urllib.parse.quote(name))
    except Exception:
        pass
    return ""

SHORTCUTS = {
    "youtube": "https://www.youtube.com", "google": "https://www.google.com",
    "github": "https://github.com", "gmail": "https://mail.google.com",
    "maps": "https://maps.google.com", "spotify": "https://open.spotify.com",
    "reddit": "https://www.reddit.com", "wikipedia": "https://en.wikipedia.org",
    "chatgpt": "https://chat.openai.com",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
    "twitter": "https://twitter.com", "x": "https://x.com",
    "amazon": "https://www.amazon.com", "netflix": "https://www.netflix.com",
    "duckduckgo": "https://duckduckgo.com", "twitch": "https://www.twitch.tv",
    "discord": "https://discord.com/app",
}

_BLOCKED_SCHEMES = ("file:", "javascript:", "data:", "vbscript:",
                    "jar:", "expect:")


def _start_menu_index() -> dict:
    """Map lowercase shortcut-stem -> .lnk path."""
    idx = {}
    if not IS_WIN:
        return idx
    roots = []
    try:
        prog = os.environ.get("ProgramData", "")
        if prog:
            roots.append(Path(prog) / "Microsoft/Windows/Start Menu/Programs")
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            roots.append(Path(appdata) / "Microsoft/Windows/Start Menu/Programs")
    except Exception:
        pass
    for root in roots:
        try:
            if not root.is_dir():
                continue
            for lnk in root.rglob("*.lnk"):
                stem = lnk.stem.strip().lower()
                if stem and stem not in idx:
                    idx[stem] = str(lnk)
        except Exception:
            continue
    return idx


def _app_paths(exe: str) -> str:
    """Registry App Paths lookup (e.g. 'blender.exe' -> full path)."""
    if not IS_WIN or not exe.lower().endswith(".exe"):
        return ""
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for view in (0, winreg.KEY_WOW64_64KEY):
                try:
                    with winreg.OpenKey(
                            hive,
                            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\\"
                            + exe, 0, winreg.KEY_READ | view) as k:
                        val, _ = winreg.QueryValueEx(k, "")
                        if val and Path(val).exists():
                            return str(val)
                except OSError:
                    continue
    except Exception:
        pass
    return ""


def resolve_app(name: str) -> dict:
    """Resolve ANY app name. Never launches — pure lookup."""
    key = (name or "").strip().lower()
    if not key:
        return {"status": "unknown", "candidates": []}
    if key == "obsidian":
        uri = _obsidian_target()
        if uri:
            return {"status": "found", "target": uri, "display": name}
    if key in ALIASES:
        return {"status": "found", "target": ALIASES[key], "display": name}
    idx = _start_menu_index()
    if key in idx:
        return {"status": "found", "target": idx[key], "display": name}
    for stem, lnk in idx.items():
        if key in stem or stem in key:
            return {"status": "found", "target": lnk, "display": name}
    exe = key if key.endswith(".exe") else key + ".exe"
    hit = shutil.which(exe) or shutil.which(key)
    if hit:
        return {"status": "found", "target": hit, "display": name}
    reg = _app_paths(exe)
    if reg:
        return {"status": "found", "target": reg, "display": name}
    close = difflib.get_close_matches(
        key, list(ALIASES) + list(idx), n=3, cutoff=0.6)
    return {"status": "unknown" if not close else "candidates",
            "candidates": close}


def _exe_stem(target: str) -> str:
    try:
        return Path(target).name.lower()
    except Exception:
        return str(target).lower()


def is_instant(target: str) -> bool:
    return _exe_stem(target) in SAFE_INSTANT


def launch_target(target: str) -> str:
    """Launch an already-resolved target. No questions asked."""
    try:
        if IS_WIN and str(target).startswith("ms-"):
            os.startfile(target)
            return f"Opened {target}."
        if IS_WIN:
            try:
                os.startfile(target)
                return f"Opened {target}."
            except Exception:
                pass
        subprocess.Popen([target], shell=False)
        return f"Launched {target}."
    except Exception as exc:
        log.warning("Launch failed for %s: %s", target, exc)
        return f"Could not launch {target}: {exc}"


def is_blocked_scheme(text: str) -> bool:
    """True for non-http(s) schemes (file:, javascript:, ...)."""
    low = (text or "").strip().lower()
    if "://" in low and not low.startswith(("http://", "https://")):
        return True
    return low.split(":", 1)[0] in ("javascript", "data", "vbscript", "file")


def normalize_url(text: str) -> str:
    t = (text or "").strip().strip(" ?.!")
    if is_blocked_scheme(t):
        return ""
    low = t.lower()
    for pinned, purl in custom_sites().items():
        if low == pinned:
            return purl
    for name, url in SHORTCUTS.items():
        import re
        if re.search(rf"\b{re.escape(name)}\b", low):
            return url
    if low.startswith(("http://", "https://")):
        return t
    import re as _re
    if _re.match(r"^[\w\-]+(\.[\w\-]+)+([/?#].*)?$", t, re.IGNORECASE):
        return "https://" + t
    return ""


def open_url(text: str) -> str:
    """Open ANY url as a REAL tab. http/https only, else refused."""
    url = normalize_url(text)
    if not url:
        return ""
    if url.lower().startswith(_BLOCKED_SCHEMES):
        log.warning("Blocked dangerous scheme: %s", url[:60])
        return "Refused: that link type is blocked for safety."
    try:
        webbrowser.open_new_tab(url)
        log.info("Opened tab: %s", url)
        return f"Opened {url} in your browser."
    except Exception as exc:
        return f"Could not open that: {exc}"


_CUSTOM_SITES = Path(__file__).resolve().parent.parent / "logs" / "custom_sites.json"


def custom_sites(path: Path | None = None) -> dict:
    """User-pinned {name: url} shortcuts. Missing/corrupt -> {}."""
    import json
    p = Path(path) if path else _CUSTOM_SITES
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {str(k).strip().lower(): str(v)
                for k, v in data.items() if v}
    except Exception:
        return {}


def pin_site(name: str, url: str, path: Path | None = None) -> str:
    """Pin a shortcut. http(s) only. Returns human reply."""
    import json
    import re as _re2
    name = (name or "").strip().lower()
    url = (url or "").strip().rstrip("?.!")
    if not name:
        return "Pin what? Give it a name."
    if is_blocked_scheme(url):
        return "Refused: only http(s) links can be pinned."
    low = url.lower()
    if not (low.startswith(("http://", "https://"))
            and "." in low.split("://", 1)[1].split("/")[0]):
        if _re2.match(r"^[\w\-]+(\.[\w\-]+)+([/?#].*)?$", url,
                      _re2.IGNORECASE):
            url = "https://" + url
        else:
            return f"'{url}' doesn't look like a web address."
    p = Path(path) if path else _CUSTOM_SITES
    try:
        sites = custom_sites(p)
        sites[name] = url
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(sites, indent=2), encoding="utf-8")
    except Exception as exc:
        log.warning("pin site failed: %s", exc)
        return "Could not save that shortcut."
    return f"Pinned '{name}' — 'open {name}' works from now on."


def unpin_site(name: str, path: Path | None = None) -> str:
    """Remove a pinned shortcut. Returns human reply."""
    import json
    name = (name or "").strip().lower()
    if not name:
        return "Unpin what? Give me the shortcut name."
    p = Path(path) if path else _CUSTOM_SITES
    sites = custom_sites(p)
    if name not in sites:
        return f"No pinned shortcut called '{name}'."
    try:
        del sites[name]
        p.write_text(json.dumps(sites, indent=2), encoding="utf-8")
    except Exception as exc:
        log.warning("unpin site failed: %s", exc)
        return "Could not remove that shortcut."
    return f"Removed '{name}'."
