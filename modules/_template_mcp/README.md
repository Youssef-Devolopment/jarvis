# My MCP Module (template)

Wraps an MCP server as a governed JARVIS module: declared
permissions, docs, and one-click activation.

1. Copy this folder: `modules/_template_mcp` → `modules/my_mcp`.
2. Edit `module.json`:
   - `id` must match the folder name (`my_mcp`),
   - `mcp.name` — the server name in your MCP config (lowercase),
   - `mcp.command` / `mcp.args` — how to launch the server
     (`{HOME}`, `{DOCUMENTS}`, `{DESKTOP}` are expanded at activation),
   - `mcp.env` — API keys the server needs (empty value = the module
     shows **needs key** and waits for you),
   - `permissions` — from the fixed vocabulary (see MODULES.md):
     `none`, `read:text`, `read:file`, `write:file`, `network`,
     `process`, `memory`, `clipboard`, `registry`.
3. Write this README: what the server does, what the permissions are
   for, and requirements (`npx`/`uvx`/keys).
4. In the MODULES tab, press **ACTIVATE** — or check it first with
   **CHECK**.

Rules enforced by the validator: command must be a plain program name
(no shell metacharacters), args ≤ 20 strings, env maps strings to
strings. Anything else is rejected with the reason shown.

Full author guide: `MODULES.md` in the repo root.
