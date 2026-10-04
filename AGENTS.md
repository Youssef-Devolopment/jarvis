# AGENTS.md — AI developer guide for JARVIS

> You are continuing work on JARVIS, a Windows voice assistant
> (Flask + DeepSeek/OpenAI-compatible). Read this file first, then
> `ARCHITECTURE.md`. Finish one unit at a time: investigate →
> implement → verify by execution → commit → push → confirm CI.

## Layout (full build)

```
run.py / server.py / desktop.py   entry (console / Flask app / tray app)
config.py      Settings + .env helpers; VERSION is the source of truth
routes/api.py  ~126 endpoints (chat, skills, apps, prefs, settings...)
skills/        125 @register skills; registry.py dispatches first-match
system/        launcher, overlay (Tk HUD), app_learner, app_close, tray…
ai/            client (stream()), tools, agents, council, screen context
voice/         mic/speech — DO NOT EDIT output.py or voices.py
memory/        SQLite facts/prefs (whitelisted _DEFAULTS)/outcomes
moods/         personalities + model router
mcp/           local package (shadows real SDK — use _sdk())
plugins/       community skills (validated, isolated loading)
static/js/app.js + templates/index.html   dashboard (single IIFE!)
tests/         unittest suite (must stay green + hermetic, see below)
check.py       11 preflight checks (run after install-level changes)
```

Lite build (`../lite jarvis/`, own repo): 26 skills, port 5002,
minimal chat page. No skills-only mode by design (yet).

## The dev loop (do this every unit)

1. `py_compile` touched files.
2. Full suite: `$env:PYTHONIOENCODING='utf-8'; .\.venv\Scripts\python.exe -m unittest discover -s tests > $null 2>&1; echo "X=$LASTEXITCODE"` → must be 0.
3. JS: `node --check static/js/app.js`. PS1: `[PSParser]::Tokenize`.
4. Live-verify the actual behavior (boot server / curl endpoint /
   browser `console`+`evaluate` via the `execute` tool — never
   `screenshot`). Restart desktop server after server-code changes
   (kill pythonw, drop `logs/jarvis.lock`, start `desktop.py`).
5. Two commits: code, then docs (`CHANGELOG.md` Unreleased +
   `README.md` if user-visible). Descriptive sentences, no prefixes.
6. `git push origin main` + confirm the Actions run goes green.

## PowerShell 5.1 rules

No `&&`, no `grep/tail/head` — use `;`, `Select-String`,
`Select-Object`. unittest writes stderr (see loop above for the exit
code trick). Quote exe paths containing spaces.

## Non-negotiable constraints

- Never edit `voice/output.py`, `voice/voices.py`; never change
  `stream()` in `ai/client.py`.
- Keys/secrets (`.env`, `.env.bak`, `*.db`, logs) are gitignored —
  never print or commit them. `git credential fill` gives the
  GitHub token; never echo it.
- `Settings.load()` is strict; lenient paths use
  `Settings.load(require_key=False)` / `try_settings()` and must
  never poison the `_settings` cache.
- Refusals always win: system processes, JARVIS's own interpreter,
  destructive terminal commands — regardless of auto mode.
- Tests must be hermetic: CI has no `.env`, no key, no voice/gpu
  deps. Fake the env (`DEEPSEEK_API_KEY`), stub `voice` via
  `sys.modules`, clear `ai.client._clients`, pin `auto_mode`,
  stub the auto-skill drafter (it writes real files + runs slow
  isolation tests).
- Frontend is one IIFE: nothing is global — drive the page via DOM
  in browser checks. Flask has no reloader: restart to see changes.
- Tk overlay flashes on the user's real screen: verify state,
  keep it to seconds, always hide afterwards.

## Key behaviors to preserve

- Chat is skills-first, LLM fallback (`POST /command`, SSE).
- Open/close gates: curated+learned = instant; else voice+toast
  confirm (default NO); auto mode (`auto_approve_skills` pref) is a
  standing yes. Generated open-skills share `ask_user`.
- Close resolves learned store → aliases → running processes;
  graceful terminate → force leftovers → verify.
- Skills-only boot (no key): local skills answer, LLM paths return
  a `no_key` setup hint, dashboard banner + HUD show the state.
- Skill modules load isolated; broken patterns/handlers fall
  through instead of failing requests.
