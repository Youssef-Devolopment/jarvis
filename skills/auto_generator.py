"""Auto-generate new JARVIS skills using the LLM.

Flow: user request matches no skill -> propose_skill() asks the LLM to
write one -> test_in_isolation() runs it without touching the live
registry -> proposal waits in _PENDING -> user approves via
approve_skill() (or "approve skill <name>") -> code lands in
skills/auto_generated/ and registers on import.

Safety:
- Generated code NEVER registers without explicit approval.
- Every candidate is saved under logs/auto_skills/ with a content hash.
- Every event is appended to logs/auto_skills.log.
- Approved skills live isolated in skills/auto_generated/.
"""

from __future__ import annotations
import ast
import hashlib
import importlib
import importlib.util
import json
import re
import sys
import tempfile
import time
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_AUTO_DIR = _ROOT / "skills" / "auto_generated"
_LOG_DIR = _ROOT / "logs" / "auto_skills"
_AUDIT = _ROOT / "logs" / "auto_skills.log"
_PENDING_FILE = _LOG_DIR / "pending.json"

_AUTO_DIR.mkdir(parents=True, exist_ok=True)
_LOG_DIR.mkdir(parents=True, exist_ok=True)

_GENERATION_PROMPT = """You are writing a new JARVIS skill in Python.

A skill is a Python function decorated with @register.

Template:
```python
from skills.registry import register

@register("SKILL_NAME", [
    r"REGEX_PATTERN_1",
    r"REGEX_PATTERN_2",
], "SHORT_DESCRIPTION")
def skill_func(text, match):
    # Optional: use match.group("name") for captured values
    return "Response text"
```

Rules:
- Reply with ONE fenced ```python block and nothing else.
- SKILL_NAME: lowercase letters, digits, underscores; max 30 chars.
- 1-3 regex patterns that match the user's request below.
  Use named groups (?P<name>...) for values the handler needs.
- Allowed imports ONLY: re, json, math, datetime, urllib.parse, html,
  plus `from skills.registry import register`.
  No file access, no subprocess, no eval, no network except reads
  via urllib (the runner validates this and rejects violations).
- Handler signature: def skill_func(text, match). Return a short
  spoken-friendly string, or None when the request does not apply.
- Keep it under 40 lines.
"""

# Import roots a generated skill may use (top-level package name).
_ALLOWED_IMPORT_ROOTS = {"skills", "logger", "re", "json", "math",
                         "datetime", "urllib", "html", "time", "random"}
# Callables / attributes that are never allowed in generated code.
_BLOCKED_CALLS = {"eval", "exec", "compile", "__import__", "open",
                  "input", "breakpoint", "exit", "quit", "system",
                  "popen", "call", "run", "check_output", "check_call",
                  "Popen", "remove", "unlink", "rmtree", "mkdir"}
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
_APPROVE_RE = re.compile(r"^(?:approve|enable)\s+(?:skill\s+)?"
                         r"(?P<name>[a-z0-9_]+)[\?\.\!]?$")
_REJECT_RE = re.compile(r"^(?:reject|discard|delete)\s+(?:skill\s+)?"
                        r"(?P<name>[a-z0-9_]+)[\?\.\!]?$")
_GREETING_RE = re.compile(r"^(?:hi|hey|hello|yo|thanks?|thank you|bye|"
                          r"good (?:morning|evening|night)|ok|okay)[\s\.\!]*$",
                          re.IGNORECASE)

_PENDING: dict = {}


def _audit(event: str, detail: str = "") -> None:
    try:
        with open(_AUDIT, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} "
                    f"{event} {detail[:300]}\n")
    except Exception as exc:
        log.warning("auto_skills audit write failed: %s", exc)


def _load_pending() -> None:
    try:
        if _PENDING_FILE.exists():
            _PENDING.update(json.loads(
                _PENDING_FILE.read_text(encoding="utf-8")))
    except Exception as exc:
        log.warning("auto_skills pending load failed: %s", exc)


def _save_pending() -> None:
    try:
        _PENDING_FILE.write_text(json.dumps(_PENDING, indent=2),
                                 encoding="utf-8")
    except Exception as exc:
        log.warning("auto_skills pending save failed: %s", exc)


_load_pending()


def auto_gen_enabled() -> bool:
    try:
        from memory import get_pref
        return bool(get_pref("auto_gen_enabled", True))
    except Exception:
        return True


def set_auto_gen_enabled(enabled: bool) -> bool:
    try:
        from memory import set_pref
        return bool(set_pref("auto_gen_enabled", bool(enabled)))
    except Exception as exc:
        log.warning("auto_gen toggle failed: %s", exc)
        return False


def _extract_code(text: str) -> str:
    m = re.search(r"```python(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    if "@register" in text:
        return text.strip()
    raise ValueError("LLM reply contained no Python skill block.")


def _validate(code: str) -> dict:
    """Parse + safety-check generated code. Returns {name, patterns,
    description}. Raises ValueError on any violation."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise ValueError(f"syntax error: {exc}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                root = a.name.split(".")[0]
                if root not in _ALLOWED_IMPORT_ROOTS:
                    raise ValueError(f"blocked import: {a.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root not in _ALLOWED_IMPORT_ROOTS:
                raise ValueError(f"blocked import: {node.module}")
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in _BLOCKED_CALLS:
                raise ValueError(f"blocked call: {f.id}()")
            if isinstance(f, ast.Attribute) and f.attr in _BLOCKED_CALLS:
                raise ValueError(f"blocked call: .{f.attr}()")
    name, patterns, desc = None, None, ""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            fn = dec.func
            if not ((isinstance(fn, ast.Name) and fn.id == "register")
                    or (isinstance(fn, ast.Attribute)
                        and fn.attr == "register")):
                continue
            if len(dec.args) < 2:
                raise ValueError("@register needs (name, patterns).")
            try:
                name = ast.literal_eval(dec.args[0])
                patterns = ast.literal_eval(dec.args[1])
                if len(dec.args) > 2:
                    desc = str(ast.literal_eval(dec.args[2]))
            except Exception:
                raise ValueError("@register args must be literals.")
    if not name or not patterns:
        raise ValueError("no @register(name, patterns) found.")
    if not _NAME_RE.fullmatch(name):
        raise ValueError(f"bad skill name: {name!r}")
    if not isinstance(patterns, (list, tuple)) or not (1 <= len(patterns) <= 5):
        raise ValueError("need 1-5 regex patterns.")
    for p in patterns:
        try:
            re.compile(p)
        except re.error as exc:
            raise ValueError(f"bad regex {p!r}: {exc}")
    return {"name": name, "patterns": list(patterns), "description": desc}


def _llm_draft(user_request: str) -> str:
    from ai.client import get_client
    c = get_client()
    model = getattr(c, "model", None) or c.default_model
    resp = c._client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _GENERATION_PROMPT},
            {"role": "user",
             "content": f"Write a skill for this request:\n{user_request}"},
        ],
        temperature=0.2, max_tokens=800)
    return (resp.choices[0].message.content or "").strip()


def test_in_isolation(code: str, sample_text: str = "") -> dict:
    """Import generated code from a temp dir, run its handler against a
    sample, then restore the registry. Never leaves traces behind."""
    meta = _validate(code)
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    import skills.registry as reg
    before = set(map(id, reg._SKILLS))
    mod_name = f"_auto_test_{meta['name']}_{int(time.time() * 1000) % 100000}"
    try:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / f"{mod_name}.py"
            p.write_text(code, encoding="utf-8")
            spec = importlib.util.spec_from_file_location(mod_name, str(p))
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            try:
                spec.loader.exec_module(mod)
            except Exception as exc:
                return {"ok": False, "skill": meta["name"],
                        "output": f"import failed: {exc}"}
            finally:
                sys.modules.pop(mod_name, None)
    except Exception as exc:
        return {"ok": False, "skill": meta["name"],
                "output": f"test harness failed: {exc}"}
def test_in_isolation(code: str, sample_text: str = "") -> dict:
    """Import generated code from a temp dir, run its handler against a
    sample, then restore the registry. Never leaves traces behind."""
    meta = _validate(code)
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    import skills.registry as reg
    before = set(map(id, reg._SKILLS))
    new = []
    mod_name = f"_auto_test_{meta['name']}_{int(time.time() * 1000) % 100000}"
    try:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / f"{mod_name}.py"
            p.write_text(code, encoding="utf-8")
            spec = importlib.util.spec_from_file_location(mod_name, str(p))
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            try:
                spec.loader.exec_module(mod)
            finally:
                sys.modules.pop(mod_name, None)
            new = [s for s in reg._SKILLS if id(s) not in before]
    except Exception as exc:
        return {"ok": False, "skill": meta["name"],
                "output": f"import failed: {exc}"}
    finally:
        # Isolation: drop anything the candidate registered.
        reg._SKILLS[:] = [s for s in reg._SKILLS if id(s) in before]
    if not new:
        return {"ok": False, "skill": meta["name"],
                "output": "module imported but no @register executed"}
    s = next((x for x in new if x.name == meta["name"]), new[0])
    sample = (sample_text or "").strip()
    try:
        if sample:
            m = s.match(sample)
            if not m:
                return {"ok": False, "skill": s.name,
                        "output": "pattern did not match the request"}
            out = s.run(sample, m)
        else:
            out = s.run("test", None)
    except Exception as exc:
        return {"ok": False, "skill": s.name,
                "output": f"handler raised: {exc}"}
    if out:
        return {"ok": True, "skill": s.name, "output": str(out)[:300]}
    return {"ok": False, "skill": s.name,
            "output": "handler returned nothing"}


def _code_hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()[:12]


def propose_skill(user_request: str) -> dict:
    """Draft + validate + test + stage a candidate. Raises on failure."""
    raw = _llm_draft(user_request)
    code = _extract_code(raw)
    meta = _validate(code)
    test = test_in_isolation(code, user_request)
    h = _code_hash(code)
    cand_path = _LOG_DIR / f"{meta['name']}_{h}.py"
    cand_path.write_text(code, encoding="utf-8")
    _PENDING[meta["name"]] = {
        "request": user_request[:200],
        "code_hash": h,
        "candidate": cand_path.name,
        "description": meta["description"],
        "patterns": meta["patterns"],
        "test_ok": test["ok"],
        "test_output": test["output"],
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_pending()
    _audit("propose", f"{meta['name']} hash={h} test_ok={test['ok']} "
                      f"req={user_request[:80]!r}")
    return {"name": meta["name"], "description": meta["description"],
            "test_ok": test["ok"], "test_output": test["output"]}


def propose_if_enabled(text: str) -> dict | None:
    """Safe entry for chat fallbacks. Never raises; None = carry on."""
    try:
        if not auto_gen_enabled():
            return None
        if _GREETING_RE.match((text or "").strip()):
            return None
        from skills.registry import get_skill
        if get_skill((text or "").strip()):
            return None
        return propose_skill(text)
    except Exception as exc:
        log.debug("auto-generate skipped: %s", exc)
        return None


def approval_prompt(proposal: dict) -> str:
    name = proposal["name"]
    desc = proposal.get("description") or "a new skill"
    if proposal.get("test_ok"):
        tested = f"I tested it: {proposal['test_output'][:120]}"
    else:
        tested = (f"My test did not pass "
                  f"({proposal['test_output'][:120]}), so review carefully")
    return (f"I drafted a new skill '{name}' ({desc}). {tested}. "
            f"Say 'approve skill {name}' to enable it, "
            f"or 'reject skill {name}' to discard it.")


def handle_approval_text(text: str) -> str | None:
    """Approve/reject voice commands. Returns reply or None."""
    t = (text or "").strip()
    m = _APPROVE_RE.match(t)
    if m:
        r = approve_skill(m.group("name"))
        if r["ok"]:
            return (f"Skill '{m.group('name')}' is now live. "
                    f"Try the request again.")
        return f"Could not approve: {r['error']}"
    m = _REJECT_RE.match(t)
    if m:
        r = reject_skill(m.group("name"))
        if r["ok"]:
            return f"Discarded the draft skill '{m.group('name')}'."
        return f"Could not reject: {r['error']}"
    return None


def list_pending() -> list:
    return [{"name": n, **p} for n, p in _PENDING.items()]


def approve_skill(name: str) -> dict:
    """Register a staged candidate. The ONLY path to live registration."""
    name = (name or "").strip().lower()
    if not _NAME_RE.fullmatch(name):
        return {"ok": False, "error": f"bad name: {name!r}"}
    pend = _PENDING.get(name)
    if not pend:
        return {"ok": False, "error": f"no pending draft '{name}'"}
    try:
        code = (_LOG_DIR / pend["candidate"]).read_text(encoding="utf-8")
        _validate(code)  # re-check: file may have changed since staging
    except Exception as exc:
        return {"ok": False, "error": f"candidate invalid: {exc}"}
    try:
        dest = _AUTO_DIR / f"{name}.py"
        dest.write_text(code, encoding="utf-8")
        mod = importlib.import_module(f"skills.auto_generated.{name}")
        importlib.reload(mod)
    except Exception as exc:
        try:
            (_AUTO_DIR / f"{name}.py").unlink(missing_ok=True)
        except Exception:
            pass
        return {"ok": False, "error": f"registration failed: {exc}"}
    from skills.registry import get_skill
    if not get_skill(name):
        return {"ok": False, "error": "module loaded but skill missing"}
    del _PENDING[name]
    _save_pending()
    _audit("approve", f"{name} hash={pend.get('code_hash')}")
    log.info("auto_generated skill live: %s", name)
    return {"ok": True, "name": name}


def reject_skill(name: str) -> dict:
    name = (name or "").strip().lower()
    if name not in _PENDING:
        return {"ok": False, "error": f"no pending draft '{name}'"}
    del _PENDING[name]
    _save_pending()
    _audit("reject", name)
    return {"ok": True, "name": name}
