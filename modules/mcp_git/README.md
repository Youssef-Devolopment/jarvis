# Git Repositories (MCP module)

Wraps the **official** `mcp-server-git` (Python, run via `uvx`) as a
governed JARVIS module: the assistant can read and search your git
history from chat.

## What it does once active

- `git status`, log, diff, blame and history search — surfaced as MCP
  tools the assistant calls when you ask ("what changed in my last
  commit", "who touched this file in June").
- The repository root defaults to `{HOME}`, so nested repos under your
  profile resolve correctly.
- The server runs `git` commands locally; nothing is pushed or
  published unless you explicitly ask JARVIS to run a push.

## Declared permissions

| Permission | Why |
| --- | --- |
| `read:file` | Reading repository files and history. |
| `process` | The server shells out to `git`. |

## Requirements

- `git` on PATH.
- [`uv`](https://docs.astral.sh/uv/) so `uvx` is available.
- On activation JARVIS writes the server into your MCP config
  (standard name `git`) and starts it; deactivation stops and
  removes it.

## Manifest reference

```json
"mcp": {
  "name": "git",
  "command": "uvx",
  "args": ["mcp-server-git", "--repository", "{HOME}"],
  "auto_start": true
}
```

To point it at one repo instead of your whole profile, replace
`{HOME}` with an absolute path after install.
