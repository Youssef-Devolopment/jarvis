# JARVIS Architecture (extension map)

```
user text → skills.dispatch() → skill reply
              │ miss (+not conversational)
              ├→ auto_generator.propose → approval → skills/auto_generated/
              └→ AIClient.stream() + TOOL_SCHEMAS → execute_tool()
/command (SSE) · /chat-style JSON · 120 REST endpoints (one /api
blueprint split across routes/api_*.py, shared routes/_common.py)
```

## Stable seams (safe to build on)

- **Skills**: `skills/registry.py` — `Skill(name, patterns, handler,
  description)`, `register()`, `dispatch()`, `toggle_skill()`.
  Community entry point: `plugins/` (validated, hot-addable).
- **LLM tools**: `ai/tool_schemas.py` (JSON schemas) +
  `ai/tool_dispatch.py:execute_tool(name, args)`.
- **Escalation**: `moods/levels.py` (8 specs) → `classifier.classify`
  → `council.run_council` → `moderator.synthesize`.
- **Memory**: `memory/store.py` (SQLite: facts, messages, prefs,
  outcomes, contacts, reminders, snippets, layouts, time_entries,
  `integrity()`); `memory/schema.py` versions the DB and snapshots it
  to `memory/backups/` before any migration.
- **Voice**: `voice/output.py:speak_async(text)`,
  `voice/input.py:listen_until_silence()`. Swap TTS/STT behind these;
  the end-to-end flow is in *The voice command path* below.
- **Config**: `config.py` + `.env` (all models OpenAI-compatible).
- **Desktop**: `system/launcher.py` (tray, hotkey, autostart, notify).
- **Service lifecycle**: `system/services.py` — one registry boots
  every background subsystem in BOTH entry points (console +
  desktop): declarative ServiceSpecs, optional pref gates, isolated
  failure capture, per-service start timing. `boot(mode)` never
  raises; its results merge with legacy `health.mark()` calls into
  `/api/health` and the SYSTEM tab. Specs that can be cycled carry a
  `stop` handler and expose stop/restart at runtime
  (`POST /api/services/<name>` with `{"action": "stop"|"restart"}`);
  boot-only listeners (hotkeys, tray) set `restartable=False`. New
  background service = add a ServiceSpec here, not another
  try/except block.
- **Boot voice**: `system/startup.py` — pure, tested messaging helpers
  shared by both entry points: the guarded console status block, the
  post-boot verdict derived from the `/api/health` snapshot (ok /
  still-starting / warn / SAFE MODE with next step), the busy-port
  probe (`ensure_port()` → friendly exit 3 before subsystems boot),
  and desktop toast text. New boot message = helper here, not a
  print in `run.py`.
- **Overlay**: `system/overlay.py` — Alt+Space HUD; thread-safe action
  queue → Tk thread; talks to `/api/command` + `/api/listen` only.
- **MCP server**: `mcp/server.py` — stdio JSON-RPC (newline frames,
  stdout = protocol, stderr = logs). Add a tool in `TOOLS` +
  `call_tool()`, a resource in `RESOURCES` + `read_resource()`.
- **Port sentinel**: `ai/ports.py:list_listeners/kill_listener`
  (refuses self + system PIDs).
- **Single instance**: `system/singleton.py:acquire()` called by
  `run.py` and `system/launcher.py`.
- **Screen context**: `ai/screen_context.py` (RAM-only loop) →
  `ai/screen_text.ask_image()` shared with on-demand OCR.
- **Turn trail**: `system/turns.py` — what each turn actually did
  (skill or model, which one, how long, ok/fail). Add a field there,
  not another log line; see *The voice command path* below.
- **Packaging**: `installer/` (Inno Setup 6).
  `installer/jarvis.iss` is the installer definition and
  `installer/install-deps.ps1` is the dependency bootstrap it runs. It
  is a packaging seam, not a third entry point: it runs the same steps
  as `install.bat` and then launches the same `desktop.py` / `run.py`.
  What it ships is generated from `git ls-files` at build time, so the
  package contains exactly the repository's tracked files — a
  hand-written file list here would be a way to leak `.env`. See
  `DECISIONS.md` #16.

## The voice command path (end to end)

There is **no wake word** — capture is push-to-talk, and there are
**two different microphones** feeding the *same* `/api/command` turn
that typed text uses. Voice has no separate brain.

**A. Overlay HUD (Alt+Space) — the server machine's mic.**
`system/overlay.py:_mic()` → `POST /api/listen` →
`voice/input.py:listen_until_silence()`: a 16 kHz mono stream in 0.1 s
blocks, RMS voice-activity detection — records until `silence_duration`
of quiet, gives up after 2 s of nothing, trims to the loud region.
The WAV goes to **Groq Whisper** (`groq_stt_model`; the prompt tells
it Arabic and English may be mixed). The transcript comes back as a
`"heard"` action → fills the entry field → **auto-submits**.

**B. Web UI mic (or Ctrl+M) — the browser's mic.**
`static/js/app.js:startRecording()` (`getUserMedia` + `MediaRecorder`,
webm/opus) → `POST /api/transcribe` →
`voice/input.py:transcribe_audio_bytes()` → the same Groq call →
`sendCommand(text)` → **auto-sends**. The VOICE button is *mute for
JARVIS's speech*, not the mic.

**The turn — `routes/api_chat.py:/command`:**

1. cheap intents, in order, *before* skills or the LLM: rejection /
   confirmation of the previous answer, `is_conversational` chitchat
   (this gate *skips the skills below* — so it must never match a
   phrasing a local skill answers),
   tool-consent verdicts ("allow 3"/"deny 3"), auto-skill approve plus
   draft-on-miss;
2. `dispatch_skill()` → `skills/registry.py:dispatch()` — skills run in
   registration order save for auto-learned app skills (front); the
   first `pattern` match whose handler returns truthy wins
   (`source:"skill"`);
3. on a miss, the LLM: route `reasoning`/`fast` (`needs_reasoning`),
   session history, `filtered_schemas(TOOL_SCHEMAS) + mcp_schemas()`,
   optional sub-agent fan-out (`subagents_enabled`), else
   `client.stream(messages, tools=…)`;
4. on finish: `store.record_reply`, **`_speak_quiet(full)`**,
   `extract_memory_async`, `outcomes.record`.

**Seeing what a turn did.** `system/turns.py` keeps a bounded
in-memory ring of the last 50 turns — `source` (skill / llm / consent
/ auto_skill / no_key), the skill or model that answered, `ms`, `ok`,
and the accept/reject `verdict` when there was one. `routes/api_chat.py`
records one entry per turn on every branch (including the failure
paths), `ai/client.py` exposes `last_model` so a fallback is nameable,
and `GET /api/turns` serves the newest first. The sidebar's **RECENT**
strip polls it (`12:04:11 · SKILL · time · 3ms`), which is how
"which skill or model answered that?" stopped being a line scrolling
past in the SYSTEM LOG. Note the distinction from `system/audit.py`:
audit is *what an agent action did* (tool calls, consents, missions),
turns is *how a command was routed*.

**Answering out loud.** `voice/output.py:speak_async()` splits the
reply into sentences, synthesizes them in parallel (Piper local,
edge-tts fallback), and plays them through pygame on the host;
`system/audio_duck` lowers other audio while the mic is open or the
voice is playing. The web UI additionally has a browser
`speechSynthesis` path (`speakText`) for payloads carrying `speak`.

**Things that bite**

- STT is a **second provider**: voice needs `GROQ_API_KEY`; a healthy
  chat model says nothing about whether the mic works.
- Dispatch is **first-match-wins and regex-based**, so a broad skill
  (e.g. `math`, which matches nearly any sentence) can swallow a
  spoken command before the model ever sees it.
- `/api/listen` blocks for the pause the user leaves
  (`silence_duration`, capped by `max_record_sec`; the overlay calls
  it with a 60 s timeout), so latency = that pause + the Groq round
  trip.
- `/api/listen` returns an empty transcript the same way for a missing
  `GROQ_API_KEY` and for a silent/muted mic, so `_listen_hint()`
  (`routes/api_voice.py`) names which one it most likely is.

## Replaceable without touching core

Moods (`moods/presets.py`), personalities, HTTP layer (per-domain
modules in `routes/`), frontend (`static/`, `templates/` — note
`static/js/app.js` is one IIFE, by decision #13), schedulers
(`system/scheduler.py`, `dream_scheduler.py`), STT/TTS engines.
