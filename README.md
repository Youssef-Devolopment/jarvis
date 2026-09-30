# JARVIS — Voice-first AI assistant for Windows

JARVIS is a Flask + DeepSeek/OpenAI-compatible voice assistant with 112
regex-dispatched skills, 30 LLM tools, hotword-free mic input (Groq),
Edge/Piper speech output, multi-model councils, memory, and a desktop
mode with tray icon, global hotkey, and Windows login autostart.

A slim **Lite** build (25 skills, port 5002) lives next to it in
`../lite jarvis/`.

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

## Login autostart

Settings → Autostart **on** (or `POST /autostart/enable`) creates a
Startup shortcut: `pythonw desktop.py --open`. Every boot starts the
server silently, opens JARVIS in a new browser window, and greets you
with system uptime. Disable anytime via Settings or
`POST /autostart/disable`.

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

## Layout

```
run.py / server.py / config.py      entry points + settings (.env)
ai/          LLM client, tools, agents, council backends, integrations
skills/      112 @register skills (+ skills/auto_generated/)
voice/       Groq mic input, Piper/edge-tts output (Ryan)
memory/      SQLite facts, messages, prefs, outcomes, contacts, …
moods/       personalities, router, escalation levels, classifier
routes/      Flask blueprints (93 endpoints)
system/      tray, hotkey, notify, autostart, scheduler, launcher
static/ + templates/   web UI (16 settings tabs, 37 slash commands)
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
