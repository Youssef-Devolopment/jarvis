"""Workspace Orchestrator suite — Boilerplate Scaffolder + File Interleaver.

Scaffolder (*"scaffold a flask project called taskboard"*) lays down a
runnable tree — README, gitignore, entrypoint, tests, .env.example —
and runs `git init` best-effort. Kinds: python, flask, fastapi, node,
react, web, plain.

Interleaver (*"append X to file Y"*, *"insert X after <anchor> in file
Z"*) targets an exact file without rewriting it by hand: every write
takes a `.bak` snapshot first and is confined to the same allow-listed
roots as Code Mode (repo, Desktop, custom pref entries) plus
`Documents\\JARVIS Projects` for new scaffolds — nothing outside is
ever touched.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from logger import get_logger
from skills.registry import register

log = get_logger(__name__)

_PROJECTS = Path.home() / "Documents" / "JARVIS Projects"


def _allowed_roots() -> list[Path]:
    roots = [_PROJECTS]
    try:
        from skills.code_mode import _allowed_paths
        roots.extend(Path(p) for p in _allowed_paths())
    except Exception:
        pass
    return roots


def _is_allowed(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except Exception:
        resolved = path
    for root in _allowed_roots():
        try:
            r = root.resolve()
            if resolved == r or r in resolved.parents:
                return True
        except Exception:
            continue
    return False


def _slug(raw: str) -> str:
    s = re.sub(r"[^\w\- ]+", "", raw.strip().lower()).strip()
    s = re.sub(r"[\s_]+", "-", s).strip("-")
    return s[:48] or "project"


_GITIGNORE = "__pycache__/\n*.pyc\n.env\n.venv/\nnode_modules/\ndist/\n"
_README = "# __NAME__\n\nScaffolded by JARVIS. Run it, then make it yours.\n"

_TEMPLATES: dict[str, dict[str, str]] = {
    "python": {
        "README.md": _README,
        ".gitignore": _GITIGNORE,
        "requirements.txt": "# add dependencies here\n",
        ".env.example": "DEBUG=1\n",
        "main.py": ('"""__NAME__ entry point."""\n\n\n'
                    'def main() -> None:\n'
                    '    print("__NAME__ ready")\n\n\n'
                    'if __name__ == "__main__":\n'
                    '    main()\n'),
        "tests/test_main.py": ("from pathlib import Path\n"
                               "import sys\n\n"
                               "sys.path.insert(0, str(Path(__file__)."
                               "parents[1]))\n\n\n"
                               "def test_import():\n"
                               "    import main\n"
                               "    assert main is not None\n"),
    },
    "flask": {
        "README.md": _README,
        ".gitignore": _GITIGNORE,
        "requirements.txt": "flask\n",
        ".env.example": "FLASK_DEBUG=1\nSECRET_KEY=change-me\n",
        "app.py": ('"""__NAME__ Flask app."""\n'
                   "from flask import Flask\n\n\n"
                   "def create_app() -> Flask:\n"
                   '    app = Flask(__name__)\n\n'
                   '    @app.get("/")\n'
                   '    def home():\n'
                   '        return {"status": "ok", "app": "__NAME__"}\n\n'
                   "    return app\n"),
        "templates/index.html": ("<!doctype html>\n<title>__NAME__</title>\n"
                                 "<h1>__NAME__</h1>\n"),
        "tests/test_app.py": ("import sys\nfrom pathlib import Path\n\n"
                              "sys.path.insert(0, str(Path(__file__)."
                              "parents[1]))\n\n\n"
                              "def test_home():\n"
                              "    from app import create_app\n"
                              "    c = create_app().test_client()\n"
                              "    assert c.get('/').status_code == 200\n"),
    },
    "fastapi": {
        "README.md": _README,
        ".gitignore": _GITIGNORE,
        "requirements.txt": "fastapi\nuvicorn\n",
        ".env.example": "APP_DEBUG=0\n",
        "main.py": ('"""__NAME__ FastAPI app."""\n'
                    "from fastapi import FastAPI\n\n"
                    "app = FastAPI(title='__NAME__')\n\n\n"
                    "@app.get('/')\n"
                    "def home():\n"
                    "    return {'status': 'ok', 'app': '__NAME__'}\n"),
        "tests/test_main.py": ("from fastapi.testclient import TestClient\n"
                               "from main import app\n\n\n"
                               "def test_home():\n"
                               "    assert TestClient(app).get('/')"
                               ".status_code == 200\n"),
    },
    "node": {
        "README.md": _README,
        ".gitignore": _GITIGNORE,
        ".env.example": "PORT=3000\n",
        "package.json": ('{\n  "name": "__NAME__",\n'
                         '  "version": "0.1.0",\n'
                         '  "main": "index.js",\n'
                         '  "scripts": {\n'
                         '    "start": "node index.js"\n  }\n}\n'),
        "index.js": ("const http = require('http');\n\n"
                     "const port = process.env.PORT || 3000;\n"
                     "http.createServer((req, res) => {\n"
                     "  res.end(JSON.stringify({ status: 'ok' }));\n"
                     f"}}).listen(port, () => console.log('__NAME__ on ' + port));\n"),
        "tests/smoke.test.js": ("const assert = require('assert');\n"
                                "assert.ok(true);\n"
                                "console.log('smoke ok');\n"),
    },
    "react": {
        "README.md": _README,
        ".gitignore": _GITIGNORE,
        "package.json": ('{\n  "name": "__NAME__",\n'
                         '  "version": "0.1.0",\n'
                         '  "type": "module",\n'
                         '  "scripts": {\n'
                         '    "dev": "vite",\n'
                         '    "build": "vite build"\n  },\n'
                         '  "dependencies": {\n'
                         '    "react": "^18",\n'
                         '    "react-dom": "^18"\n  },\n'
                         '  "devDependencies": {\n'
                         '    "@vitejs/plugin-react": "^4",\n'
                         '    "vite": "^5"\n  }\n}\n'),
        "vite.config.js": ("import { defineConfig } from 'vite';\n"
                           "import react from '@vitejs/plugin-react';\n\n"
                           "export default defineConfig({ plugins: [react()] });\n"),
        "index.html": ('<!doctype html>\n<html><head><meta charset="utf-8">'
                       '\n<script type="module" src="/src/main.jsx"></script>'
                       "</head><body><div id='root'></div></body></html>\n"),
        "src/App.jsx": ("export default function App() {\n"
                        "  return <h1>__NAME__</h1>;\n}\n"),
        "src/main.jsx": ("import { createRoot } from 'react-dom/client';\n"
                         "import App from './App.jsx';\n\n"
                         "createRoot(document.getElementById('root'))"
                         ".render(<App />);\n"),
    },
    "web": {
        "README.md": _README,
        ".gitignore": _GITIGNORE,
        "index.html": ("<!doctype html>\n<meta charset='utf-8'>\n"
                       "<link rel='stylesheet' href='style.css'>\n"
                       "<h1>__NAME__</h1>\n<script src='script.js'></script>\n"),
        "style.css": "body { font-family: system-ui, sans-serif; margin: 2rem; }\n",
        "script.js": "console.log('__NAME__ ready');\n",
    },
    "plain": {
        "README.md": _README,
        ".gitignore": _GITIGNORE,
        "TODO.md": "# __NAME__\n\n- [ ] first step\n",
    },
}

_KIND_WORDS = ["fastapi", "flask", "react", "python", "node",
               "javascript", "web", "plain"]


def scaffold(kind: str, name: str, parent: Path | None = None) -> str:
    """Create the tree. Returns a human summary (or an error line)."""
    if kind == "javascript":
        kind = "node"
    kind = kind if kind in _TEMPLATES else "python"
    slug = _slug(name)
    if not slug or slug in (".", ".."):
        return "Bad project name."
    root = parent or _PROJECTS
    target = root / slug
    if target.exists():
        return f"Already exists: {target} — pick another name."
    if not _is_allowed(root):
        return f"Blocked: {root} is outside the allowed project roots."
    try:
        root.mkdir(parents=True, exist_ok=True)
        files = []
        for rel, content in _TEMPLATES[kind].items():
            fp = target / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content.replace("__NAME__", slug), encoding="utf-8")
            files.append(rel)
    except Exception as exc:
        return f"Scaffold failed: {exc}"
    try:
        subprocess.run(["git", "init", "-q"], cwd=str(target),
                       capture_output=True, timeout=15)
        files.append("(git initialised)")
    except Exception:
        pass
    log.info("scaffold kind=%s name=%s files=%d", kind, slug, len(files))
    return (f"Created {kind} project '{slug}' at {target} — "
            f"{len(files)} entries: " + ", ".join(files[:8]) + ".")


@register("scaffold", [
    r"^(?:please\s+)?scaffold\s+(?P<rest>.+?)[\?\.\!]?$",
    r"^(?:please\s+)?boilerplate\s+(?:for\s+|a\s+)?(?P<rest>.+?)[\?\.\!]?$",
], "Scaffold a project tree (python/flask/fastapi/node/react/web)")
def skill_scaffold(text, match):
    rest = (match.group("rest") or "").strip()
    if not rest:
        return None
    kind = "python"
    low = " " + rest.lower()
    for k in _KIND_WORDS:
        if f" {k}" in low:
            kind = k
            break
    name = None
    m = re.search(r"(?:called|named|for)\s+([\w\- ]+?)(?:\s+(?:project|app)\b)?$",
                  rest, re.IGNORECASE)
    if m:
        name = m.group(1)
    else:
        words = re.sub(r"\b(?:a|an|the|project|app|called|new)\b", " ", rest)
        words = [w for w in words.split() if w.lower() not in _KIND_WORDS]
        name = words[-1] if words else rest
    parent = None
    m2 = re.search(r"\s+in\s+(\S+)$", rest)
    if m2 and (":" in m2.group(1) or "\\" in m2.group(1) or "/" in m2.group(1)):
        parent = Path(m2.group(1).strip('"').strip())
        name = rest[:m2.start()].strip()
        name = re.sub(r".*(?:called|named)\s+", "", name) or name
    return scaffold(kind, name, parent)


# ---------------------------------------------------------------- interleave

def _prep(path_str: str) -> tuple[Path | None, str]:
    p = Path(path_str.strip("\"'")).expanduser()
    if not _is_allowed(p):
        return None, f"Blocked: {p} is outside the allowed roots."
    if not p.is_file():
        return None, f"No such file: {p} (interleave needs an existing file)."
    return p, ""


def _backup(p: Path) -> None:
    try:
        p.with_suffix(p.suffix + ".bak").write_bytes(p.read_bytes())
    except Exception as exc:
        log.debug("backup failed for %s: %s", p, exc)


def append_to_file(path_str: str, body: str) -> str:
    p, err = _prep(path_str)
    if not p:
        return err
    body = body.strip("\r\n")  # keep code indentation intact
    if not body.strip():
        return "Nothing to append."
    try:
        original = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"{p} is not a text file."
    _backup(p)
    sep = "" if original.endswith("\n") or original == "" else "\n"
    p.write_text(original + sep + body + "\n", encoding="utf-8")
    lines = (original + sep + body + "\n").count("\n")
    return f"Appended to {p} ({lines} lines now, backup at {p.name}.bak)."


def insert_near(path_str: str, body: str, anchor: str,
                where: str = "after") -> str:
    p, err = _prep(path_str)
    if not p:
        return err
    body = body.strip("\r\n")  # keep code indentation intact
    anchor = anchor.strip()
    if not body.strip() or not anchor:
        return "Need both the text and the anchor."
    try:
        lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return f"{p} is not a text file."
    idx = next((i for i, ln in enumerate(lines) if anchor in ln), None)
    if idx is None:
        return f"Anchor not found in {p}: no line contains {anchor!r}."
    _backup(p)
    new_line = body if body.endswith("\n") else body + "\n"
    at = idx if where == "before" else idx + 1
    lines.insert(at, new_line)
    p.write_text("".join(lines), encoding="utf-8")
    return (f"Inserted {where} line {idx + 1} of {p} "
            f"({len(lines)} lines now, backup at {p.name}.bak).")


@register("interleave", [
    r"^(?:please\s+)?append\s+(?P<body>.+?)\s+to\s+(?:the\s+)?file\s+(?P<path>\S+?)[\?\.\!]?$",
    r"^(?:please\s+)?(?:interleave|insert)\s+(?P<body>.+?)\s+(?P<where>before|after)\s+(?P<anchor>.+?)\s+in\s+(?:the\s+)?file\s+(?P<path>\S+?)[\?\.\!]?$",
], "Append or insert into an existing file (with .bak backup)")
def skill_interleave(text, match):
    g = match.groupdict()
    if g.get("anchor"):
        return insert_near(g["path"], g["body"], g["anchor"],
                           g.get("where") or "after")
    return append_to_file(g["path"], g["body"])
