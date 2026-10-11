# Modules — the JARVIS extensibility ecosystem

A **module** is a folder with a `module.json` manifest. Modules are how
JARVIS grows: skills, MCP server integrations and (by extension) any
validated drop-in, installed without editing core code. Everything in
this system is real and inspectable — every module declares what it
does and what it may touch **before** it is allowed to run, and
anything that fails validation is shown as `failed` with the reason,
never silently ignored.

The MODULES tab (Settings → MODULES) shows the whole picture: installed
/ active / inactive / failed states, declared permissions and
capabilities, docs, examples, and update status.

## The starter library

JARVIS ships 9 real modules under `modules/` — five pure-computation
skills and four governed MCP integrations:

| Module | Kind | What it does |
| --- | --- | --- |
| `unit_convert` | skill | Length, weight and temperature conversions |
| `color_convert` | skill | Hex ⇄ RGB ⇄ HSL color math |
| `number_base` | skill | Decimal ⇄ binary ⇄ octal ⇄ hex |
| `secure_token` | skill | Cryptographically strong tokens (`secrets`) |
| `url_codec` | skill | Percent-encode / decode text for URLs |
| `mcp_fetch` | mcp | Official `mcp-server-fetch` — web pages as clean text |
| `mcp_filesystem` | mcp | Official server-filesystem — scoped Documents access |
| `mcp_git` | mcp | Official `mcp-server-git` — read/search repos |
| `mcp_memory` | mcp | Official server-memory — knowledge-graph memory |

Every one of them is validated by the same test suite as community
modules (`tests/test_modules.py`) — there is no privileged path.

## Authoring a skill module in 5 steps

1. **Copy the template**

   ```
   xcopy modules\_template_skill modules\my_module /E /I
   ```

2. **Edit `module.json`** — `id` must equal the folder name
   (`my_module`). Describe it in one sentence, list 1–8
   `capabilities`, pick `permissions`, add at least one `example`.

3. **Edit `skill.py`** — write your `@register(name, patterns)` skill.
   Handler signature: `def handler(text, match) -> str | None`.

4. **Write the README** — what it does, examples, and what the
   permissions are for. Users see this in the DOCS panel before they
   activate anything.

5. **Check, then activate** — in the MODULES tab, point the install
   box at your folder and press **CHECK** (dry run: reports
   permissions and every problem, installs nothing), then
   **INSTALL**. Or from the API:

   ```
   POST /api/modules/validate   {"path": "C:\\dev\\my_module"}
   POST /api/modules/install    {"path": "C:\\dev\\my_module"}
   ```

If anything is wrong you get a plain-English rejection; if the code
crashes at load, the module is installed but shows **FAILED** with the
error, and none of its skills stay registered.

## Authoring an MCP module

An MCP module wraps a real MCP server with declared permissions and
docs. Copy `modules\_template_mcp` → `modules/my_mcp` and set the
`mcp` block:

```json
"mcp": {
  "name": "my-server",
  "command": "npx",
  "args": ["-y", "@scope/some-mcp-server"],
  "env": {"SOME_API_KEY": ""},
  "auto_start": true
}
```

On activation JARVIS writes the server into your MCP config
(`mcp_servers.json`) and starts it; deactivation stops and removes it.
`{HOME}`, `{DOCUMENTS}` and `{DESKTOP}` in args are expanded at
activation. Empty env values mark the module **needs key** — it waits
for you instead of failing in a loop.

## Manifest schema (`module.json`)

| Field | Required | Rules |
| --- | --- | --- |
| `schema` | no | Manifest schema version; current build understands `1` |
| `id` | yes | `^[a-z][a-z0-9_]{0,29}$`, **must equal the folder name** |
| `name` | yes | 1–60 chars, shown in the UI |
| `version` | yes | `MAJOR.MINOR.PATCH` |
| `author` | no | Shown on the card |
| `license` | no | e.g. `MIT` |
| `description` | yes | 1–300 chars, one honest sentence |
| `kind` | no | `skill` or `mcp` — derived from `entry`/`mcp` if absent |
| `entry` | skill | Python file (plain name, inside the folder) with `@register` |
| `skills` | no | Skill names the entry must register (checked at activation) |
| `mcp` | mcp | Server block: `name`, `command`, `args`, `env`, `auto_start` |
| `capabilities` | yes | 1–8 short strings: what it can do |
| `permissions` | yes | Non-empty list from the vocabulary below |
| `docs` | no | Docs file name (default `README.md`) |
| `examples` | yes* | Up to 5 `{phrase, reply}` objects (*at least one expected) |
| `homepage` | no | Link for more info |

## Permission vocabulary

Every module must declare what it touches. Anything outside this list
is **rejected** — the vocabulary is deliberately small and reviewable:

| Permission | Meaning |
| --- | --- |
| `none` | Pure computation — only sees the words you type |
| `read:text` | Reads text you provide in the command |
| `read:file` | Reads files on disk |
| `write:file` | Writes files on disk |
| `network` | Makes outbound network requests |
| `process` | Launches other programs |
| `memory` | Reads or writes JARVIS memory and notes |
| `clipboard` | Touches the clipboard |
| `registry` | Touches Windows registry or app config |

`none` cannot be combined with other permissions. The MODULES tab
colors every permission chip, so a module asking for `process` is
never hiding in fine print.

## Safety model

Validation runs **before** anything loads:

- **Manifest** — schema, id/version formats, permission vocabulary,
  entry file shape, MCP command checked against shell metacharacters
  (`; | & \` < >` and friends are rejected).
- **Skill code** — the entry file passes the same AST validator as
  community plugins (`skills.auto_generator._validate`): an import
  whitelist (no `os`, no `subprocess`), blocked calls (`eval`,
  `exec`, `open`, `popen`…), hijack-proof regex patterns (no
  catch-alls, no swallowing "hello"/"help"/timers).
- **Archives** — zip installs refuse traversal (`../`), absolute
  paths, >200 files, >10 MB uncompressed, and unexpected file types.
- **Activation** — declared `skills` must actually register; a crash
  at import rolls back every skill it managed to register and records
  the error. A failed module is degraded, visible, and retryable —
  it can never take the boot down.
- **Uninstall** — deactivates (unregisters skills, stops + removes
  MCP servers) then deletes the folder.

## Lifecycle & states

```
validate (dry run) ──> install (folder or .zip) ──> activate ⇄ deactivate ──> uninstall
```

- `active` — enabled and loaded (skills registered / MCP configured)
- `inactive` — installed, disabled, nothing loaded
- `failed` — validation or activation failed; the error is shown on
  the card and in `GET /api/modules`

State persists in `modules/state.json` (gitignored). Boot re-activates
exactly what you enabled via the `modules` boot service.

## Update status

`modules/catalog.json` maps each module id to its latest known
version — a bundled snapshot of the same `{id: version}` shape a remote
registry will publish later. When the catalog version is higher than
the installed one, the card shows an **UPDATE** chip. Modules not in
any catalog show no update source (honestly "unknown", not "current").

## API

| Route | Body | Does |
| --- | --- | --- |
| `GET /api/modules` | — | All modules + counts + permission vocabulary |
| `GET /api/modules/<id>` | — | One module in full, including docs text |
| `POST /api/modules/validate` | `{path}` | Dry-run check of a folder or `.zip` |
| `POST /api/modules/install` | `{path, activate=true}` | Install (validated first) |
| `POST /api/modules/toggle` | `{id, enabled}` | Activate / deactivate |
| `POST /api/modules/uninstall` | `{id}` | Deactivate + delete |

## Roadmap

This framework is the base the registry work builds on: the catalog
format above is already what a remote registry will serve, and
`install from .zip` is the transport it will use. Publishing, signing
and one-click community installs land on top of this — not instead of
it.
