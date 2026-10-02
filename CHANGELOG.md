# Changelog

All notable changes to JARVIS. Versioning: **vMAJOR.MINOR.PATCH** —
bump MINOR for big feature batches, PATCH for fixes
(`config.VERSION` is the single source of truth).

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
- App finder, site finder, MCP presets/import, community plugin
  installer, DEV drawer (files / term / call / logs).
- GitHub packaging: CI, issue templates, PR template, MIT license,
  CONTRIBUTING, ARCHITECTURE.

### Fixed
- Overlay "(no reply)": SSE `error` payloads now surfaced; bytes
  stream lines decoded; `/api` prefix restored on header fetch.
- Rogue venv launcher binaries replaced (single-process boots).
- MCP SDK shadowed by local `mcp/` package (`_sdk()` workaround).

### Security
- `.env` and runtime data gitignored; no keys in the repository;
  port sentinel refuses self/system PIDs; terminal command guards.
