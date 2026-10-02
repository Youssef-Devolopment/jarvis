# JARVIS Architecture (extension map)

```
user text → skills.dispatch() → skill reply
              │ miss (+not conversational)
              ├→ auto_generator.propose → approval → skills/auto_generated/
              └→ AIClient.stream() + TOOL_SCHEMAS → execute_tool()
/command (SSE) · /chat-style JSON · 117 REST endpoints (routes/api.py)
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
  outcomes, contacts, reminders, snippets, layouts, time_entries).
- **Voice**: `voice/output.py:speak_async(text)`,
  `voice/input.py:listen_until_silence()`. Swap TTS/STT behind these.
- **Config**: `config.py` + `.env` (all models OpenAI-compatible).
- **Desktop**: `system/launcher.py` (tray, hotkey, autostart, notify).
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

## Replaceable without touching core

Moods (`moods/presets.py`), personalities, HTTP layer (add blueprints
in `routes/`), frontend (`static/`, `templates/`), schedulers
(`system/scheduler.py`, `dream_scheduler.py`), STT/TTS engines.
