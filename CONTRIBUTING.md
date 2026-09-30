# Contributing to JARVIS

## Plugins (no fork needed)
Put community skills in `plugins/` — see `plugins/README.md`.
They load on boot, are safety-validated, and never touch core.

## Core changes
1. One concern per change; keep skills to one file each.
2. Skills: `@register` + literal regexes; never invent facts in code.
3. Tools (`ai/tool_schemas.py` + `ai/tool_dispatch.py`): schema and
   handler ship together or not at all.
4. Every user-visible failure needs a spoken-safe fallback string.
5. Run before pushing:
   `python -m py_compile <files>` and the relevant `tests/test_*.py`.

## What stays stable
- `Skill` dataclass + `@register(name, patterns, description)` shape
- `TOOL_SCHEMAS` entries (`{type, function: {name, description,
  parameters}}`)
- `speak_async(text)`, `listen_until_silence()` signatures
- `/api/*` response envelope `{ok, ...}` + `ValidationError` → 400
