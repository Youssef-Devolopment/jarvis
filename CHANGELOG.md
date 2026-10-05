# Changelog

All notable changes to JARVIS. Versioning: **vMAJOR.MINOR.PATCH** —
bump MINOR for big feature batches, PATCH for fixes
(`config.VERSION` is the single source of truth).

## [1.7.0] — 2026-10-06

Overlay rebuilt from zero as HUD 4.0, a one-click Library for skill
packs and MCP servers, plus cross-cutting polish.

### Added
- **LIBRARY tab — one-click installs**: a curated catalog
  (`library/catalog.json`) of **13 bundled skill packs** (word
  counter, percent / tip / BMI calculators, date distance, age,
  ROT13, password generator, coin flip, random picker, JSON
  formatter, Roman numerals, palindrome check) and **12 MCP
  servers** (memory, filesystem, everything, time, fetch, git,
  sqlite, github, brave-search, puppeteer, playwright, postgres).
  `GET /api/library`, `POST /api/library/skill`,
  `POST /api/library/mcp` — packs hot-load through the same
  validator as community plugins (no restart), MCP entries expand
  `{HOME}`/`{DOCUMENTS}` placeholders, auto-start when they can and
  clearly defer when an API key is required. The tab has
  client-side search and per-entry ADDED state.
- **HUD 4.0 "Glass Command Deck"** — `system/overlay.py` rebuilt
  from zero: 20px rounded transparent corners with a double bezel
  and top accent line, a wider 760px deck whose compact input mode
  expands into a scrollable reply well, live JARVIS header (title,
  mood · model, version, status dot that pulses amber while
  thinking and turns red on errors), hover-lit chips, a key-hint
  footer with COPY, typewriter replies that cancel when superseded,
  100-entry history, dictation auto-send and header drag. Esc / ✕ /
  Alt+Space still hide outright while focus-away only dismisses an
  idle, empty deck.
- **`secrets` allowed in generated skills** — the validator accepts
  the crypto-RNG module so password packs can be truly random.

### Fixed
- **MCP `add_server` accepts list args** — arguments were split on
  whitespace, breaking any path containing spaces; one-click
  library entries now pass real argument lists.
- Plugin template and generator prompt now document the complete
  allowed-import list (including `time`, `random`, `secrets`).

### Changed
- 18 new tests (302 total) covering catalog shape, pack validation,
  install/add flows, placeholder expansion and the library API.

## [1.6.0] — 2026-10-05

Backup story completed, HUD refresh made dynamic, dev mode visible,
agent loop hardened, and the app catalog widened.

### Added
- **Backup restore** — the missing half of the backup story:
  `restore_backup` engine (`POST /api/backup/restore`), voice skill
  ("restore backup" → preview, "restore confirm" → apply), and a
  BACKUPS section in the Marketplace (BACK UP + RESTORE per zip).
  Restore is a two-step confirm; it snapshots current state first,
  refuses zip-slip and invalid names, closes the live SQLite handle,
  swaps files atomically, and reopens lazily. Live roundtrip proven.
- **Dynamic HUD refresh**: header now refreshes ~10s (was ~30s) and
  immediately after every command, so mood/model changes show at once.
- **Dev-mode badge**: `/api/info` exposes `dev`; the dashboard brand
  reads `v1.6.0 · DEV` under `FLASK_DEBUG=1`, and `run.py` prints
  the mode at boot.
- **~40 new native app aliases** (Office, 7-Zip, WinRAR, Blender,
  GIMP, JetBrains, GitHub Desktop, Signal, regedit, mstsc, charmap,
  magnifier, resmon…) plus 5 more instant-launch safe tools.

### Fixed
- **Aliases no longer dead-end**: `resolve_app` used to trust an
  alias unconditionally, so uninstalling the app broke "open X"
  even when the Start Menu had it. Aliases now verify (URI / PATH /
  App Paths) and fall through to Start Menu / fuzzy search.
- **Agent loop**: each sub-task retries once on transient failure
  (or an empty answer), merge is told how many sub-tasks failed so
  it answers with what survived, and `run()` never raises.

### Changed
- 19 new tests (284 total) covering restore roundtrip, zip-slip,
  alias fall-through, retry, dev flag, refresh cadence.

## [1.5.1] — 2026-10-05

Full error-and-logic sweep: a systematic audit of every subsystem
for crashes, silent failures, unbounded growth and unguarded input.

### Fixed
- **MCP tool calls timing out**: the client runtime used
  `run_coroutine_threadsafe` only when the server's event loop was
  NOT running (inverted check), so idle loops went down a fallback
  path that never worked. Idle loops are now driven directly with a
  timeout, running loops use `run_coroutine_threadsafe` — proven by
  a test that fails on the old code (60s timeout) and passes now.
- **Directory deletes lost data**: `fs_delete` and `code delete`
  only backed up files, so deleting a folder rmtree'd it with no
  recovery. Both now copy the whole tree first (50MB cap) and
  REFUSE the delete if the backup fails or the tree is too large.
- **Garbage numerics crashed endpoints**: unguarded `int()` on
  `minutes`/`hours`/personality sliders turned `"lots"` into a 500.
  New `_to_int` helper parses defensively and clamps to safe ranges.
- **Unbounded growth**: `jarvis.log` now rotates at 5MB × 3
  backups; research jobs pruned to 20 finished; overlay command
  history capped at 100; dashboard log honors the `log_max` pref;
  `tidy clean` LRU-trims the TTS voice cache (was 561 files / 20MB).
- **Cosmetic**: inline `__import__('os')` in the MCP stdio banner.

### Added
- 19 new tests (265 total): MCP loop-state dispatch, directory
  backup/refusal paths, input-clamp endpoints, log rotation, voice
  cache LRU, research job pruning.

## [1.5.0] — 2026-10-05

Autonomy + storefront batch: the box keeps working when models
misbehave, and everything installable lives in one Marketplace tab.

### Added
- **Admin terminal** (`code run-admin` / `run X as admin`):
  Code-Mode gate + forbidden list + structural checks, elevation
  ALWAYS asks (auto mode ignored by design), Windows UAC is the
  final guard, everything audited. Launcher yields `as admin`
  inputs to it instead of mis-opening apps.
- **Marketplace tab** (Settings → MARKET, `GET /api/market`): one
  catalog for everything installable — 133 skills with ON/OFF
  toggles, pending drafts with approve/reject, community plugins
  (file-upload install + reload), 8 MCP presets with one-click
  install, MCP servers with start/stop, pinned sites with remove.
  Every action reuses the existing validated endpoints; verified
  live with zero console errors.

### Fixed
- **Default-mood chat 400s**: the `fast` preset passed a stray
  string as `temperature`, so every default chat was rejected by
  the provider. Removed it (0.1/60 back in their fields) plus a
  regression test pinning numeric provider params on all presets.
- **Temperature-sensitive models**: new `create_with_temp_fallback`
  helper retries once without `temperature` on 400/invalid-request
  rejections; wired into chat streaming, agents, dream summary,
  reality check, vision and research synthesis. Other errors still
  fail loudly.

## [1.4.0] — 2026-10-04

Autonomy + resilience batch: research agent, HUD rebuild, loops
that survive dead models, native apps, backups.

### Added
- **Deep Research Agent** (`system/research_agent.py`): multi-step
  technical research — `search_all` finds candidates, top URLs are
  fetched (same-host one level, capped), BeautifulSoup strips
  layout noise and keeps code blocks, then LLM synthesis (or an
  extractive digest when keyless). Reports land timestamped in
  `docs/research/*.md` (gitignored vault) with TL;DR, key points,
  code fences and links; a one-line summary is remembered for later
  recall. Served as async `POST /api/research` + poll
  `GET /api/research/<job>`, and as the `deep_research` skill
  (`research <topic>` returns the report path). Verified live
  end-to-end (3 sources → report → recall).

- **DEV terminal upgrades**: output appends per run (no more
  overwrite), elapsed time on every command, Up/Down history,
  one-click CLEAR.
- **Logon task with working directory**: the scheduled task is now
  created from XML (`InteractiveToken`, 15s delay) with
  `WorkingDirectory` set to the project root — the old form started
  in System32 so `.env` never loaded. Legacy command kept as
  fallback. Still needs one elevated run to apply.
- **Overlay HUD 3.0 — command-deck rebuild**: the fixed panel is
  now a floating command bar (emblem + entry + mic/send + status
  dot) that expands into reply + chips + footer on submit.
  DPI-aware native rendering (the actual blur cure on scaled
  displays), bigger readable type, data-driven chips, live header
  refresh while visible, idle-only click-away still intact.

- **Agent loop that survives dead models**: split/merge/vision/
  dream/reality-check all use the configured default model instead
  of hardcoded IDs, plan/merge calls have timeouts, and expired /
  retired / sunset offers now trigger the fallback chain instead
  of failing chat (the exact Qwen-expiry 404 seen live is covered
  by test).
- **More native apps**: Zoom, Notion, Slack, Obsidian, Notepad++,
  Everything and Snipping Tool resolve instantly; Obsidian opens
  straight into your vault via deep link when one is configured.
- **One-click backup** (`backup` / `POST /api/backup`): memory DB
  + `.env` zipped to `logs/backups` (last 5 kept), list via
  `GET /api/backups`. Verified live (209 KB).

## [1.3.0] — 2026-10-04

Add-anything + fast-web batch: one verb installs everything, search
grows a keyed AI tier with a keyless reader fallback, sessions go
stable.

### Added
- **Universal add** (`add ...` / `POST /api/add`): sites
  (`remember <url> as <name>`, pinned to `logs/custom_sites.json`,
  `open <name>` resolves them, `forget site <name>` removes),
  MCP presets (`install mcp fetch`) and servers, apps
  (learn-without-launch), forced skill drafts — one router over the
  existing validated backends, unknown shapes fall through.
- **Tavily AI search tier** (fast depth, `TAVILY_API_KEY` optional):
  verified against the live API docs; silent skip when keyless.
- **Jina reader fallback**: pages raw HTML can't see resolve to
  readable markdown (verified live, no key).
- **Stable session secret**: first boot generates `FLASK_SECRET_KEY`
  into `.env` (never logged, never committed) and reuses it —
  sessions no longer reset on every restart. Falls back to
  ephemeral only if `.env` is unwritable.
- `mcp_servers.json` is now gitignored (it can hold server env
  secrets) — found by audit before it ever landed with any.

## [1.2.0] — 2026-10-04

Autonomy + self-care batch: the assistant opens, closes, cleans
and tours on its own; skills can't break it; agents get a memory.

### Added
- **Self-cleaning tidy**: `tidy` reports stale temp files, `tidy
  confirm` removes them (in-use skipped, MB reclaimed reported);
  Dream runs tidy nightly while idle (`dream_tidy_temp` pref).
- **Self-removing guided tour**: brand-new installs get a 4-step
  spotlight tour (command bar → log → settings → HUD) that deletes
  its own DOM on finish/skip and records `onboarded`; the
  GETTING STARTED card offers re-tours.
- **Windows theme control** (`win_theme` skill): dark/light mode
  and transparency effects via HKCU + instant broadcast, verified
  against the live registry both directions.
- **Faster memory**: `count_facts()` replaces full-table pulls,
  `idx_facts_status_id` covers the hot query (measured ms-range at
  50k rows, so no migration was justified — numbers first).
- **Voice pre-warmed**: TTS engine primes in a background thread
  at boot (console + desktop paths); first reply skips the cold
  model/network hit.
- **Skill-maker hijack guards**: catch-all, empty-matching, broad
  (2+ everyday utterances) and clone-of-another-skill patterns are
  rejected at validation; same-name refreshes and trusted system
  templates still pass.
- **Agent continuity files**: `.agent-state.md` (gitignored live
  session memory, updated every unit) and `AGENTS.md` (the full
  developer loop for any AI continuing this repo, linked from
  README).

## [1.1.0] — 2026-10-04

Big update: keyless-first onboarding, app open/close autonomy,
unbreakable skill loading, and a rewritten README.

### Added
- **Unbreakable skill loading**: core skill modules import
  isolated — one broken file logs a warning and boot continues
  with the rest (proven live with a syntax-broken probe module);
  broken regex patterns are skipped per-skill instead of failing
  the request. Community plugins already had this; now everything
  does.
- **Installer health report**: `setup.ps1` runs the 11-point
  `check.py` at the end and, on a fresh keyless install, points at
  Settings → GENERAL instead of failing the install.
- **First-run onboarding card**: fresh installs (no key, or zero
  memory facts) get a GETTING STARTED card atop the log — add key,
  try a local skill, open an app — each one click, dismiss persists
  in the new durable `onboarded` pref.
- **Overlay HUD usefulness pass**: `＋ OPEN` / `✕ CLOSE` chips
  prefill `open `/`close ` (one tap + app name runs it), a `⧉ COPY`
  button copies the last answer, the header shows a `NO KEY`
  suffix in skills-only mode, click-away only dismisses an idle
  empty HUD (never mid-answer or mid-typing — Esc/✕/Alt+Space
  still hide outright), and the HUD now resolves the server URL
  without requiring an API key.
- **Auto mode for apps**: the durable `auto_approve_skills` pref
  ("enable auto approve skills") is now a standing yes for app
  open/close gates — open and close run with zero prompts while
  system-critical and self-process refusals still apply. Also fixes
  repeat-`open` of learned non-safe apps, which previously dead-ended
  at "OK, not opening it." (generated skills had no asker); they now
  share one `ask_user` helper, paths are canonicalized on learn, and
  `POST /api/apps/close` honors auto mode too.
- **Close any app by voice** (`close`/`kill <app>`): companion to
  the universal opener. Resolves through the learner store, curated
  aliases and running processes; refuses Windows-critical processes
  and JARVIS's own interpreters; asks before closing anything that
  wasn't explicitly learned or aliased; closes gracefully first
  (apps may prompt to save), forces only leftovers, verifies gone,
  and audits like launches. Served also as `POST /api/apps/close`
  (`{query, confirm}`). Tab/window phrases stay with the
  browser/desktop hotkey skills (pattern-level guard plus dispatch
  order).
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
