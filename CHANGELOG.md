# Changelog

All notable changes to JARVIS. Versioning: **vMAJOR.MINOR.PATCH** —
bump MINOR for big feature batches, PATCH for fixes
(`config.VERSION` is the single source of truth).

## [Unreleased]

### Added
- **In-app API key setup** (Settings → GENERAL): paste
  `DEEPSEEK_API_KEY`, SAVE+TEST verifies it live against the
  provider (model count shown) and persists it to `.env` (with a
  `.env.bak` backup, now gitignored) preserving every other line;
  chat works immediately, the banner clears, and only voice features
  still ask for a restart. `GET /api/settings/key` reports a masked
  key (`thk•••d_hv` style — the secret is never sent to the page),
  and `config` gains `masked_key()`, `validate_key_format()` and
  `write_env_key()`.
- **Skills-only mode**: JARVIS now boots without `DEEPSEEK_API_KEY`.
  Local skills (time, math, notes, timers, opening apps, 100+ more)
  answer normally; only LLM chat degrades, returning a setup hint
  (`no_key` flag) instead of refusing to start. The dashboard shows
  an amber "Skills-only mode" banner (dismissible, links to
  Settings), `/api/info` reports `key` / `no_key_mode`, and
  `config` gains `Settings.load(require_key=False)`, `has_key`,
  `try_settings()` and `key_status()`. A dead speaker can no longer
  turn a good text reply into a failed request (chat TTS is
  best-effort).
- Known limitation: mic/speaker features stay unavailable until a
  key is set (`voice/output.py` reads settings at import and is
  intentionally untouched) — voice endpoints fail with a clear
  error while text chat and skills are unaffected.

## [1.0.0] — 2026-10-02

First GitHub-ready release.

### Added
- **Overlay 2.0** (`Alt+Space`): glass HUD with glow border, live
  mood/model header, typewriter replies, quick chips (screen / timer /
  time / note), command history, mic dictation, drag-by-header,
  pre-warmed at boot.
- **Native MCP stdio server** (`python -m mcp.server`): 7 tools,
  4 resources, JSON-RPC handshake; host configs via `GET /api/mcp/serve`.
- **Triple power-button autostart**: Startup shortcut + HKCU Run key +
  optional Task Scheduler logon task; single-instance guard
  (`logs/jarvis.lock` with PID verification).
- **LIFE / DEV mode switcher** with persisted state.
- **Developer terminal + port sentinel** (sandboxed commands,
  one-click kill with self/system PID refusal).
- **Omniscience screen-context loop**: RAM-only background capture,
  on-demand vision, skills `screen_context` / `screen_loop_control`.
- **Obsidian bridge REST API** + `/clip` and `/vault` chat commands.
- **Autonomous app learner** (`system/app_learner.py`): "open <unknown
  app>" deep-scans Program Files / LocalAppData / Start Menu / %PATH%
  (parallel, 1h cache, warmed at boot), launches the hit behind the
  usual confirm gate, then writes a permanent `@register` skill at the
  front of the dispatch order — next call is instant. Manage via
  `GET /api/apps/learned`, `POST /api/apps/learn` / `/api/apps/forget`.
- App finder, site finder, MCP presets/import, community plugin
  installer, DEV drawer (files / term / call / logs).
- **Persistent remember**: the `remember` skill writes facts
  (text + timestamp + source) into the core SQLite memory store —
  recalled via `memory.recall()` and injected into the system prompt
  (`facts_block()`); JSON sidecar fallback so a broken DB never loses a
  note.
- **Durable auto-approve gate** (`auto_approve_skills` preference):
  "enable/disable auto approve skills" or `POST
  /api/auto_skills/auto_approve` dynamically switches new-skill
  registration between explicit human approval and instant (only for
  code that passed validation + isolated test); app-learner skills
  stage through the same approval queue when the gate is off, and
  `forget()` / direct writes clean stale queue entries.
- Health surface: `GET /api/info` reports `facts` + `auto_approve`,
  `/api/auto_skills/pending` reports the gate state, `check.py` runs
  11 preflight checks (memory store + approval gate added).
- **One-line installer** (`setup.ps1`): a single copy/paste command
  (PowerShell or cmd) clones the repo to `%USERPROFILE%\jarvis`,
  builds `.venv`, installs every requirement group + Playwright
  Chromium and seeds `.env` from the template; run from inside an
  existing checkout it reuses the current `.venv` / `.env` untouched.
- GitHub packaging: CI, issue templates, PR template, MIT license,
  CONTRIBUTING, ARCHITECTURE.

### Changed
- **Full UI refresh — dashboard**: premium glass rebuild (gradient
  hairline panels, blurred topbar strip, pill dock), accent system now
  derived from `--theme-hue` so every glow follows the active mood,
  state-driven colors for the status pill / tagline / input ring
  (boot · idle · listening · thinking · speaking · tool · error),
  entrance choreography, hover micro-interactions, accent scrollbars,
  text selection and `prefers-reduced-motion` support.
- **Full UI refresh — overlay HUD**: bezel + accent edge with glowing
  hex emblem and halo status dot, letterspaced header with mood/model
  pill, readable Segoe UI reply well with accent bar, hover-reactive
  chips and buttons, focus-lit input border, slide+fade entrance and a
  proper fade-out dismissal.
- Layout pass: scroll-safe sidebar, richer log-entry styling (user
  messages get an accent stripe), sharper typography throughout.

### Fixed
- Fresh installs (`install.bat` / `pip install -r requirements.txt`)
  crashed on a dependency deadlock: `open-interpreter==0.4.3` pins
  `tiktoken<0.8` while every modern `litellm<2` needs `>=0.8`, sending
  pip through an unsatisfiable backtrack into a source-only build that
  needs Rust. Integrations now declare open-interpreter's real runtime
  dependencies with bounds that resolve (and match the shipped
  environment), the package itself installs with `--no-deps`, and a
  `setuptools<82` pin keeps the `pkg_resources` module open-interpreter
  still imports (removed in setuptools 82).
- Overlay "(no reply)": SSE `error` payloads now surfaced; bytes
  stream lines decoded; `/api` prefix restored on header fetch.
- Overlay queue pump could die silently after one failed action (HUD
  stopped responding while looking alive); actions now isolate errors,
  Tk callback exceptions are logged instead of lost under pythonw.
- App-learner fuzzy matching tightened: sub-4-char keys can no longer
  hijack long queries ("open totally-unknown-app" no longer matches).
- Skill approval pipeline: dead duplicate `test_in_isolation`
  definition removed; re-approving a changed candidate never
  double-registers, and approval after `forget()` re-registers even
  when Python has the module cached.
- The `auto_approve_skills` voice command now reports the persisted
  state instead of flipping an in-memory flag that died on restart.
- Duplicate `btn-dev` id in the dock: the visible DEV button had no
  listener (the id resolved to a hidden copy), so the drawer would not
  open — one button now works in both UI modes.

### Community
- README live overlay screenshot (`docs/overlay.png`), HUD demo callout
  with GIF placeholder, `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1),
  `SECURITY.md` (private reporting, scope, user hardening notes).
- Rogue venv launcher binaries replaced (single-process boots).
- MCP SDK shadowed by local `mcp/` package (`_sdk()` workaround).

### Security
- `.env` and runtime data gitignored; no keys in the repository;
  port sentinel refuses self/system PIDs; terminal command guards.
