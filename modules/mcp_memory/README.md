# Knowledge Graph Memory (MCP module)

Wraps the **official** `@modelcontextprotocol/server-memory` (npm, run
via `npx`) as a governed JARVIS module: persistent, structured memory
that survives restarts.

## What it does once active

- Stores facts as a knowledge graph: **entities** (people, projects,
  tools), **relations** between them, and **observations** (details).
- The assistant creates and queries the graph through MCP tools —
  "remember that my editor is VS Code", "what do you know about the
  jarvis project".
- The graph is persisted server-side on disk, so memories outlive a
  session. This complements JARVIS's own memory DB with a
  relationship-aware store.

## Declared permissions

| Permission | Why |
| --- | --- |
| `memory` | Reading and writing the knowledge graph. |

## Requirements

- Node.js (`npx` available on PATH).
- On activation JARVIS writes the server into your MCP config
  (standard name `memory`) and starts it; deactivation stops and
  removes it.

## Manifest reference

```json
"mcp": {
  "name": "memory",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-memory"],
  "auto_start": true
}
```
