# Filesystem Access (MCP module)

Wraps the **official** `@modelcontextprotocol/server-filesystem`
(npm, run via `npx`) as a governed JARVIS module with declared
permissions and a scoped root.

## What it does once active

- Gives the assistant explicit, tool-mediated file access — list,
  read, write and edit files **inside your Documents folder only**.
- The server is directory-scoped by design: it cannot read or write
  outside the root JARVIS passes it (`{DOCUMENTS}` by default).
- Useful for: "read my meeting notes", "summarize the PDF text file in
  Documents", "draft the letter and save it to Documents".

## Declared permissions

| Permission | Why |
| --- | --- |
| `read:file` | Reading the files you point it at. |
| `write:file` | Saving or editing files on request. |

## Requirements

- Node.js (`npx` available on PATH).
- On activation JARVIS writes the server into your MCP config
  (standard name `filesystem`) and starts it; deactivation stops and
  removes it.

## Manifest reference

```json
"mcp": {
  "name": "filesystem",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "{DOCUMENTS}"],
  "auto_start": true
}
```

To widen or narrow the scope, edit the last arg after install — for
example `{DESKTOP}` or a dedicated folder.
