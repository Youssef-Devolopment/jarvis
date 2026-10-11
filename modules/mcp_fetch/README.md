# Web Fetch (MCP module)

Wraps the **official** `mcp-server-fetch` (Python, run via `uvx`) as a
governed JARVIS module: declared permissions, docs, and one-click
activation in the MODULES tab.

## What it does once active

- Fetches a URL and returns clean, readable text (HTML noise stripped).
- The assistant uses it for research: "summarize this page", "what does
  the docs site say about X".
- Runs entirely locally — the server process is started by JARVIS and
  only fetches the URLs you ask for.

## Declared permissions

| Permission | Why |
| --- | --- |
| `network` | Fetching web pages is the whole point. |

No filesystem or process access is requested beyond the server binary
itself (`uvx` downloads and runs `mcp-server-fetch`).

## Requirements

- [`uv`](https://docs.astral.sh/uv/) installed so `uvx` is available.
- On activation JARVIS writes the server into your MCP config
  (standard name `fetch`) and starts it; deactivation stops and
  removes it.

## Manifest reference

```json
"mcp": {
  "name": "fetch",
  "command": "uvx",
  "args": ["mcp-server-fetch"],
  "auto_start": true
}
```

Placeholders `{HOME}`, `{DOCUMENTS}` and `{DESKTOP}` in args are
expanded at activation.
