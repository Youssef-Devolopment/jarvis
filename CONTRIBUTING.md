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
5. Run the **dev loop** below before pushing — it is the same gate CI
   runs, so a green local run and a green CI run mean the same thing.

## The dev loop (before you push)

```bat
.venv\Scripts\python.exe -m py_compile <the files you touched>
node --check static/js/app.js            :: if the UI changed
.venv\Scripts\ruff.exe check .           :: lint (curated ruff.toml)
.venv\Scripts\python.exe -m unittest discover -s tests
```

`Ran N tests ... OK` **and** `$LASTEXITCODE` = 0 is the pass line —
unittest writes to stderr, so check the exit code as well as the text.
`TESTING.md` is the full manual: the fresh-copy run that needs no
`.env`, the six health layers, the count of tests/routes/skills that
must be updated in the docs, and the manual smoke tests that only a
real Windows machine can do.

## The installer (`installer/`)

`installer/README.md` is the reference. The short version:

```bat
installer\build.ps1        :: -> dist\JARVIS-Setup-<version>.exe
```

Two things to know before you touch it:

- **The shipped file list is generated from `git ls-files`.** Only
  tracked files can be packaged, and `build.ps1` aborts the build if
  anything that looks like a secret (`.env*`, `*.db`, `*.onnx`, `*.bak`,
  `logs/`) shows up in that list. Do not replace it with hand-written
  `Excludes` patterns — a blacklist that is wrong leaks keys, and that
  is the one mistake here a later commit cannot undo.
- **Verify by installing, not by reading.** A silent install into a
  temp folder is part of `TESTING.md` §7 and runs in CI on every tag; it
  must leave no `.env`, no `logs\`, no `*.db` and no `*.onnx` behind,
  and the uninstaller must take everything else back out.

## What stays stable
- `Skill` dataclass + `@register(name, patterns, description)` shape
- `TOOL_SCHEMAS` entries (`{type, function: {name, description,
  parameters}}`)
- `speak_async(text)`, `listen_until_silence()` signatures
- `/api/*` response envelope `{ok, ...}` + `ValidationError` → 400
