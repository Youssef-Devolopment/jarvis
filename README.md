# JARVIS — Voice-first AI assistant for Windows

![version](https://img.shields.io/badge/version-v1.0.0-blue)
![license](https://img.shields.io/badge/license-MIT-green)
![tests](https://img.shields.io/badge/tests-66%20passing-brightgreen)
![platform](https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey)

JARVIS is a Flask + DeepSeek/OpenAI-compatible voice assistant with 119
regex-dispatched skills, 30 LLM tools, hotword-free mic input (Groq),
Edge/Piper speech output, multi-model councils, memory, and a desktop
mode with tray icon, global hotkeys (`Ctrl+Alt+J`, `Alt+Space` overlay),
native MCP server, and triple power-button autostart.

A slim **Lite** build (25 skills, port 5002) lives next to it in
`../lite jarvis/`.

## Repository status

- `main` builds green: syntax-check every file + **66 unit tests**
  on Windows runners (`.github/workflows/ci.yml`)
- No secrets in the repo — `.env`, runtime data and browser caches
  are gitignored; API keys live only in your local `.env`
- Community-friendly: MIT license, issue/PR templates,
  `CONTRIBUTING.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, hot-reloadable
  `plugins/` with a validated template

## Quickstart (Windows)

```bat
install.bat
copy .env.example .env   :: then fill in DEEPSEEK_API_KEY / GROQ_API_KEY
start.bat                :: console server on http://127.0.0.1:5000
```

Or silent desktop mode (tray + `Ctrl+Alt+J`, opens a fresh browser tab):

```bat
desktop.bat
```

## Login autostart (power button)

Settings → Autostart **on** (or `POST /autostart/enable`) arms up to
**three independent triggers** so pressing the PC power button always
brings JARVIS up:

1. Startup shortcut `pythonw desktop.py --open`
2. `HKCU\...\CurrentVersion\Run` registry key (no admin needed)
3. Task Scheduler logon task, +15s (created when elevated)

Every boot starts the server silently, opens JARVIS in a new browser
window, and greets you with system uptime. The single-instance guard
makes a double-fire harmless. `GET /autostart/status` reports which
mechanisms are armed; disable via Settings or `POST /autostart/disable`.

## What it does

- **Chat** (`POST /command`, SSE stream): skills first, LLM fallback
- **Skills** (`GET /api/skills`): notes (Obsidian vault or SQLite),
  todos, reminders, timers, contacts, weather, wiki, crypto, web
  search/fetch, file ops, desktop control, screenshots, bridges
  (OpenCode, OpenHands, Clawbot), and more
- **Council** (`POST /api/council/run`): 3–10 models debate in
  parallel, moderator synthesizes (levels 7–8 ask confirmation first)
- **Agents** (`POST /api/agents/run`): split → parallel → merge
- **Auto-generate skills** (`/api/auto_skills/*`): LLM drafts, isolated
  test, your approval registers it into `skills/auto_generated/`
- **Outcome memory** + **reality check**: rejections steer the system
  prompt; factual answers get second-source verification
- **Dream Mode**: nightly organize + backup + day summary (off by
  default, `dream_enabled` pref)
- **Morning briefing** (`GET /api/briefing`): greeting + pending
  reminders + things you told it to remember
- **MEGA utilities**: clipboard watcher, quick capture, contacts,
  snippets vault, window layouts, URL cleaner, auto-format, time
  tracking, focus lock, screen OCR, cross-app bridge

## Background nervous system (v1.0.0)

JARVIS runs as an invisible background OS layer, not just a chat tab:

- **Single-instance guard** — `logs/jarvis.lock` holds the live PID;
  a second boot refuses cleanly (exit 2, logged warning). No forks.
- **Alt+Space floating overlay** — a transparent, always-on-top HUD
  over any window (game, IDE, browser): glass panel with glow border,
  hexagon logo, live mood/model header, typewriter reply area,
  quick chips (SCREEN / TIMER / TIME / NOTE), command history
  (↑↓), mic dictation, drag-by-header, fade-in, status-dot pulse
  while thinking. Auto-hides on blur / Esc / second press; pre-warmed
  at boot so the first press is instant. (`system/overlay.py`,
  pref `overlay_enabled`)
- **LIFE / DEV mode switcher** — top-bar toggle, persisted in
  localStorage. LIFE shows briefing/vault/notes; DEV reveals the
  terminal drawer, port sentinel and file editor without reload.
- **Native MCP server** — `venv\python.exe -m mcp.server` speaks
  MCP stdio/JSON-RPC and exposes 7 tools (skills, command, terminal,
  memory, Obsidian, ports, screen OCR) + 4 resources to VS Code,
  Claude Desktop, Cursor, etc. Copy ready-made configs from
  `GET /api/mcp/serve`.
- **Port sentinel** — `GET /api/ports` lists listeners with process
  names, `POST /api/ports/kill` one-click kills (refuses self and
  system PIDs). Also a DEV-sidebar widget + `/ports`, `/kill`.
- **Developer terminal** — DEV drawer → TERM tab runs sandboxed
  commands (`POST /api/terminal/run`), same guards as Code Mode.
- **Screen-context loop** — RAM-only background capture every ~20s
  (never written to disk, zero API calls while looping); "what's on
  my screen" / "fix this error" answer from the freshest frame.
  Prefs: `screen_loop_enabled`, `screen_loop_interval`.
- **Obsidian bridge** — `POST /api/obsidian/save` clips ideas to the
  vault; `/clip <text>` and `/vault` from the chat bar.

## Layout

```
run.py / server.py / config.py      entry points + settings (.env)
ai/          LLM client, tools, agents, council backends, integrations
skills/      119 @register skills (+ skills/auto_generated/)
voice/       Groq mic input, Piper/edge-tts output (Ryan)
memory/      SQLite facts, messages, prefs, outcomes, contacts, …
moods/       personalities, router, escalation levels, classifier
mcp/         client runtime, presets, native stdio MCP server
plugins/     community plugins (hot-reload, MIT-replaceable)
system/      tray, hotkey, overlay, singleton, autostart, launcher
routes/      Flask blueprints (117 endpoints)
static/ + templates/   web UI (LIFE/DEV modes, 30+ slash commands)
```

## Config

Copy `.env.example` → `.env`. Minimum: `DEEPSEEK_API_KEY`
(Token Harbor–compatible base URL allowed). Optional: `GROQ_API_KEY`
(mic), `BRAVE_API_KEY` (search tier), `OBSIDIAN_VAULT` (notes go to
Obsidian Markdown instead of SQLite), `TODOIST_API_TOKEN`.

## Health

```bat
.venv\Scripts\python.exe check.py     :: 9 preflight checks
.venv\Scripts\python.exe -m unittest  :: test suite
```
