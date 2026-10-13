# MANUS — JARVIS Agent OS Operator Manual

How JARVIS works as a disciplined agent: one loop, typed tools,
verified edits, consent gates, staged rollouts, and an audit trail.
Read this before adding tools, changing permissions, or enabling
autonomy. Companion docs: `DECISIONS.md` (why), `ARCHITECTURE.md`
(what exists), `TESTING.md` (how we know).

## 1. Overview

JARVIS is a local Flask server (port 5001) with a voice HUD, a web
dashboard, and one authoritative agent loop:

```
user text → skill router → (miss) → model → tool → observe → model …
```

Deterministic Python skills answer first (offline, instant, free).
Anything they miss falls through to the LLM with 31 built-in tools
plus live MCP servers, up to 15 rounds per request. The model acts
through tools; the loop verifies, gates, truncates, and audits every
step. Every behavior below is tested — `python -m unittest discover
-s tests` is the proof.

## 2. Operating principles

1. **One loop.** Skills, MCP tools, workspace tools and subagents
   plug into the same model → tool → observe cycle. No ad-hoc flows
   bypass it.
2. **Small typed surface.** Strict schemas over vague catalogs;
   every tool declares input/output, capabilities, timeout.
3. **Verify before completion.** Checks after each meaningful
   action; self-correct and retry; never silent success.
4. **Permission boundaries.** Reads run free; writes, shell, MCP
   and destructive actions gate on allow / confirm / deny.
5. **Structured results.** Compact outputs, truncation with notice,
   no raw dumps into model context.
6. **No fake breadth.** Fewer real behaviors beat many stubs;
   everything shipped is tested and real.
7. **Backward compatibility.** Additive changes only: frozen
   `stream()` signature, stable SSE keys, stable endpoints/prefs.
8. **Flags and staged rollout.** New behavior behind a flag; one
   safe demo flow first; expand on log evidence.
9. **Traceable actions.** Every call, verdict and result auditable.
10. **Agent-like, not chatty.** Act through tools and verify.

## 3. Architecture — the loop

`POST /api/command` (`routes/api.py:command`) is the single entry:

1. Rejection/confirmation markers, conversational bypass.
2. Consent verdicts (`allow 3` / `deny 3`) resolve parked tools.
3. Skill dispatch → auto-skill approve/propose.
4. Sub-agent fan-out (flagged, multi-part questions only).
5. `AIClient.stream(messages, tools, max_rounds=15)` (`ai/client.py`):
   streams deltas, accumulates `tool_calls`, executes via
   `execute_tool`, appends results, re-opens — until an answer,
   a budget-exhausted final no-tools pass, or 15 rounds.
6. Reply recorded, spoken, memory-extracted; `[DONE]` terminates.

Event kinds are additive and stable: `content`, `reasoning`,
`tool_call` (+`step`/`steps`), `tool_result`, `status`, `route`,
`error`. Consumers must ignore unknown keys, never unknown kinds.

## 4. Tool registry and schema format

Schemas live in `ai/tool_schemas.py:TOOL_SCHEMAS` (OpenAI function
shape: `{type, function: {name, description, parameters}}`).
Metadata lives in `ai/permissions.py:_CATALOG` (capabilities, tier,
timeout) — the two are cross-validated by test, so neither drifts:

- Tool id: `fs_read`, `term_run`, `mcp__server__tool`…
- Version: tools are versioned with the product (`config.VERSION`);
  no per-tool versions — renames never happen (see mapping below).
- Capabilities: `fs:read fs:write fs:delete shell:exec
  shell:exec:destructive mcp:invoke network:fetch network:post`.
- Timeout: seconds where enforceable (`term_*` 30, MCP 60,
  `computer_run` 120); `None` means local and bounded — an honest
  null, not a fake number.
- Allowed roots: `ai/tools_fs.py:_ALLOWED_ROOTS` (repo, Desktop,
  Documents, Downloads). Outside → `[blocked]`, always.
- Result envelope: backends return text; the choke point caps it
  (300 display, 6000 model-bound, both with notice) and redacts
  secrets before anything model-bound.

Name mapping (kept stable for the model — never rename tools):

| Operator name | Built-in |
|---|---|
| `workspace.read_file` | `fs_read` |
| `workspace.list_files` | `fs_list` |
| `workspace.edit_file` | `fs_replace` (+`fs_write`) |
| `workspace.run_checks` | verify-after-edit (§7) |
| `shell.exec` | `term_run` / `term_python` |
| `web.fetch` | `silent_browse`, `deep_search` |
| `mcp.call` | `mcp__server__tool` |

## 5. Permission model

One table (`ai/permissions.py`), one decision function:

```
decide(name, args, mode) → "run" | "park"
```

- Destructive shell text parks **even in auto mode** — auto never
  bypasses confirmation. Destructiveness is matched per command
  segment (`rm -rf /`, `format X:`, `deltree`, `mkfs`, `dd … of=`,
  `del/rmdir …windows…`, `shutdown /s|r`, `reg delete HKLM`,
  `diskpart`, `bcdedit`); mere mentions don't match.
- Confirm-tier parks only in `ask` mode; auto mode runs it.
- Unknown names run free: the dispatcher is closed, so they return
  `"Unknown tool"` and the model self-corrects.
- Enforcement differs by context, tiers don't: chat parks for
  numbered consent; OS missions (gated by `autonomy_enabled`) ask
  by voice/toast. The single mission-context exception is `mcp__`
  tools running free inside supervised missions.

Consent flow: gated call → parked as `#N` → model asks in plain
words → `allow N` runs it now and its result is the reply,
`deny N` refuses. Requests expire after 10 minutes, queue caps at
20. Pref `tool_approval`: `ask` (default) or `auto`.

## 6. Subagents

Off by default (`subagents_enabled: false`; Settings → GENERAL →
Sub-agents). When on and a question misses every skill and trips
the multi-part gate (`compare`, `research`, `pros and cons`…):

- plan → ≤5 sub-tasks → max **2 workers**, 45 s each, 1 retry →
  merge (evidence capped at 4000 chars) → one answer.
- Stragglers are cancelled into timeout dicts; the pool never
  raises; a failed pool degrades to the single loop silently.
- `subagent_spawned` / `subagent_completed` audit events bracket
  every run. Workers make no tool calls (2 LLM calls max each).

## 7. Verification workflow

`workspace.run_checks` is the verify-after-edit phase, built into
`fs_write` / `fs_append` / `fs_replace` (`ai/tools_fs.py`):

| Suffix | Check |
|---|---|
| `.py` | compiled in-process (parses, never runs) |
| `.json` | parsed |
| `.js` | `node --check` (10 s; missing node → "skipped") |
| other | quiet — no fake verdicts |

The verdict rides the tool result (`verify: ok` / `VERIFY FAILED:
…line N`), so the model sees its own breakage next round and fixes
it. A failed check changes the flow; success is never announced
without the check line. The reference demo (read → edit → verify →
report) runs in `tests/test_audit_trail.py:DemoFlowTests`.

## 8. Audit trail and observability

One file: `logs/code_mode_audit.log` (`[time] OK/FAIL action
target extra`). Writers: `execute_tool` (every call),
consent park/run/deny, subagent spawn/complete, mission
propose/deny. Served newest-first via `GET /api/audit?limit=N`
(capped at 200, never raises). Secrets are redacted before
model-bound text; the local trail keeps full evidence. When
something surprises you, read the tail first.

## 9. Feature flags

| Flag (pref) | Default | Gates |
|---|---|---|
| `subagents_enabled` | `false` | parallel pool fan-out |
| `tool_approval` | `ask` | `auto` runs confirm-tier free (destructive still parks) |
| `autonomy_enabled` | `false` | OS missions entirely (kill switch) |
| `code_mode_enabled` | `false` | workspace code edits by missions |
| `auto_approve_skills` | `true` | auto-drafted skill activation |

Rule: new behavior ships behind a flag, one safe flow first,
expansion only on audit evidence. Flags live in Settings →
GENERAL; all are read live (no restart).

## 10. Extension guide — adding a tool safely

1. Schema in `ai/tool_schemas.py` (name, description, parameters
   with types + required). No renames, ever.
2. Branch in `ai/tool_dispatch.py:_execute_tool` (bounded output,
   `[blocked]/[error]` conventions, never raise).
3. Row in `ai/permissions.py:_CATALOG` (capabilities, tier,
   timeout or honest `None`). Reads → auto; state change →
   confirm.
4. Tests: dispatch result, tier membership, validation
   accept/reject, audit line. The catalog/toggle coverage tests
   fail if you skip (1).
5. Docs: CHANGELOG entry, MANUS mapping row if operator-named.
6. Never: network/exec without a tier, unbounded results,
   secrets in results, silent success.

## 11. Troubleshooting

- **"Unknown tool" in replies** — the model hallucinated a name;
  it self-corrects next round. If persistent, the schema wasn't
  offered (check `filtered_schemas` + toggle list).
- **Parked tool never runs** — consent request expired (10 min) or
  queue full; ask again and answer promptly.
- **Subagents never fire** — flag off (default), or the question
  matched a skill first, or the gate words are absent.
- **Destructive command parked in auto mode** — by design (§5);
  say `allow N`.
- **Empty audit tail** — actions predate the trail, or `/api/audit`
  with a bad limit (defaults to 50).
- **Dead-model delays** — failed models cool for 10 minutes
  automatically; change Settings → GENERAL model if persistent.

## 12. Security notes

- Filesystem allowlist enforced on every fs call; writes back up
  first (`logs/tool_backups`); oversized deletes refused.
- `term_python` is NOT sandboxed — that is why it is confirm-tier.
  Treat every shell-capable tool as remote code execution with a
  human in the loop.
- Secrets: redacted before model context and logs; the local audit
  trail is full evidence — protect the machine, not just the repo.
- `.env`, DBs, backups, pending files are gitignored; the updater
  refuses non-fast-forward pulls.
- MCP servers are third-party processes: their tools are
  confirm-tier in chat, and their schemas are validated but their
  semantics are not — review what you enable.
