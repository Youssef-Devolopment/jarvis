# JARVIS — Architecture Decisions

Why the code looks the way it does. Each entry is a decision we made
on purpose, with what it buys us and what it costs — so future
contributors can reason with us instead of archaeology-digging through
commits. Related: `ARCHITECTURE.md` (structure), `TESTING.md`
(verification), `ROADMAP.md` (direction).

---

## 1. Skills-first execution

**Decision.** User text hits the local skill dispatcher *before* any
LLM call. Only a dispatch miss (or purely conversational input) goes
to the model.

**Why.** A registered skill is deterministic, offline, instant and
free. The model is probabilistic, networked, slow and metered — for
"what time is it", "stop listening", "clear my clipboard" there is
nothing to gain from a round trip. Skills-first also means core
functionality survives a dead provider, a missing key, or an empty
wallet: skills-only mode is a *mode*, not a failure.

**What it costs.** Routing bugs are possible — a skill that matches
too greedily steals a conversational turn. That is why dispatch
routing is hermetically tested (`test_dispatch.py`), skill replies
carry `source: "skill"` in the SSE stream, and purely-conversational
input bypasses skills by classifier rather than by keyword.

---

## 2. Local memory in SQLite

**Decision.** All persistent state — facts, messages, prefs, outcomes,
contacts — lives in local SQLite files under `memory/`, accessed
through `memory/store.py` + `memory/schema.py`. No cloud DB, no
ORM-heavy layer, no server.

**Why.** JARVIS is a *personal* assistant: its memory is the user's
data and should stay on the user's disk. SQLite gives transactions,
single-file backups, `PRAGMA integrity_check`, and zero operational
surface. Schema versioning (`user_version` + ordered migrations) and
**backup-before-migration** mean the DB can evolve without gambling
the facts a user spent weeks accumulating.

**What it costs.** No sync story, no multi-writer access, and we own
the migration discipline ourselves. Accepted: single-process,
single-machine is the product. The tests prove the discipline
(`test_memory_schema.py`: migrations, backups, integrity).

---

## 3. Graceful degradation instead of hard fails

**Decision.** When a subsystem breaks, the system *degrades with a
structured, honest error* — it never lets one broken piece crash the
boot or the request, and it never pretends nothing happened.

**Why.** A personal assistant runs on a machine the user half-owns:
networks flap, keys expire, `npx` servers don't start. Hard fails
make the whole product dead for an unrelated reason; silent fails
make it untrustworthy. So: services boot in isolated threads with
their own health marks, `/api/health` reports each row separately,
LLM failures return a structured `502` with a setup hint (not an
HTML traceback), and skills-only mode keeps answering local commands
when the key is missing.

**What it costs.** Degraded states are *states we have to design* —
every failure mode deserves a test. Hence `test_failure_paths.py`,
`test_no_key_mode.py`, and the "what to do when degraded" section in
`TESTING.md`. Complexity lives in the error paths so the happy path
stays simple.

---

## 4. Service-based lifecycle management

**Decision.** Every background subsystem (voice, browser, scheduler,
sentinels, MCP, tray/hotkeys, …) is declared once in
`system/services.py` as a `ServiceSpec` and booted by one registry
shared by **both** entry points (`desktop.py` and `run.py`). Each
service starts independently, fails independently, logs its own
health, is optional if broken, and (where meaningful) is
stop/restart-able from the API and the SYSTEM tab.

**Why.** Boot used to be one big procedural flow — a single failure
could cascade, and desktop and console drifted apart (the desktop
parity bug shipped precisely because two code paths duplicated
startup). One registry means: one place to see what runs, one place
to fix a start order, per-service timing in the log, and UI lifecycle
controls that can't point at services the server doesn't actually
run.

**What it costs.** The registry is a framework — specs need honest
`stop`/`restartable` flags (hotkeys and tray are boot-only and say
so), and threaded starts record their results *after* boot (tests
poll to settle). The endpoint `POST /api/services/<name>` refuses
structured 400s rather than pretending it restarted something it
can't.

---

## 5. Health warnings surfaced, not hidden

**Decision.** Problems are visible in as many honest places as
possible: the boot log line (`Health after boot: …`), the
`GET /api/health` snapshot, the SYSTEM dashboard, a page-wide banner
that **cannot be dismissed while the system is degraded**, and a
config-audit WARNING line at startup. Config warnings are *counted
and surfaced*, not buried in a debug log.

**Why.** Trust comes from observability. If JARVIS has a degraded
MCP server, the user should see it without opening a dashboard — and
should also see it if they don't look for twenty minutes. A dismissible
banner trains people to ignore it; an auto-hiding one only when
healthy trains them to trust it. The banner is amber for `warn`
(config drift) and red for `degraded` (something failed), and it
names the failure.

**What it costs.** Visible warnings are pressure to *fix* things —
and some states are legitimately noisy (a user's MCP config failing
on their machine). We accept that pressure; the alternative is a
product that lies by omission. Tests assert the banner's three states
and the boot line's wording.

---

## 6. Config auditing matters

**Decision.** `config.audit_settings()` runs static, never-raising
checks at boot — model/base-URL pairing, port/temperature/token
ranges, engine and log-level validity, vault path existence,
debug-on-non-loopback, external key formats (`gsk_`, `tvly-`) — and
its warnings feed `/api/health` and the boot log.

**Why.** A flexible env file is a machine for silent mistakes: a
`deepseek-*` model pointed at a foreign base URL, `PORT=70000`,
`LOG_LEVEL=INF0`, a key with a typo'd prefix. Each one is invisible
until runtime, then confusing. Auditing converts future 3 a.m.
debugging into a boot-time sentence.

**What it costs.** Audits can nag. We deliberately *don't* warn on
sane-but-unusual combos (e.g. a deepseek model on a proxy base URL —
proxies are a legitimate use), because a warning nobody can act on
teaches people to ignore warnings. Every check has a test asserting
both that it fires *and* that the clean config stays silent.

---

## 7. Windows-native, and what that means

**Decision.** JARVIS targets Windows first: tray icon, global
hotkeys (`Ctrl+Alt+J`, `Alt+Space`), window management, scheduled
tasks for autostart, PowerShell installers, and a CI runner on
`windows-latest`.

**Why.** The voice-first, hands-on-desktop experience is the product.
Cross-platform abstractions would have us maintaining lowest-common-
denominator shells while the actual differentiators (overlay HUD,
hotkeys, tray lifecycle) would still be Windows-specific. We'd rather
do one OS properly than three superficially.

**What it costs.** PowerShell 5.1 constraints (no `&&`, no `??`, no
ternaries in scripts), `pythonw` vs `python` entry-point subtleties,
and Windows-only CI mean contributors on other OSes can write logic
but can't fully verify. Documented in `TESTING.md` and `AGENTS.md`
so the constraints are known, not discovered.

---

## 8. Secrets and local data handled as if audited

**Decision.** `.env` is the single secret store and is gitignored;
key saves go through `write_env_key` which snapshots `.env.bak` first;
logs pass through `logger.redact()` so tokens can't leak into
`logs/jarvis.log`; memory backups and the DB itself are gitignored;
`check.py` verifies secret hygiene as one of its 11 preflight checks.

**Why.** A personal assistant sees API keys, contacts, clipboard
content and browser history. "It's local" is only a privacy story if
the hygiene backs it: nothing secret is ever committed, logged, or
written outside the machine. Reviewers and users should be able to
assume this without reading the code each time.

**What it costs.** Redaction and backups are code we must maintain
(`test_logging.py`, `test_settings_key.py`, `test_backup.py`), and
debug output must stay boring — no dumping full settings objects into
logs "just for this one bug".

---

## 9. Agent operating system, not a chat app with features

**Decision.** All agent work obeys ten principles: (1) **one loop** —
a single model → tool → observe → model cycle that skills, MCP
tools, workspace tools and subagents all plug into, no ad-hoc flows
bypassing it; (2) **small typed tool surface** — strict
schema-driven tools with explicit input/output, permissions,
timeouts and validation; (3) **verification before completion** —
checks after each meaningful action, self-correct and retry, never
silent success; (4) **permission boundaries** — reads run free,
writes/shell/MCP/destructive actions gate on allow / confirm /
deny, allowlists and sandboxing by default; (5) **structured
results** — compact tool outputs, truncation with a visible warning,
never raw log/stack dumps into model context; (6) **no fake
breadth** — fewer real behaviors beat many half-working stubs,
everything shipped is tested and real; (7) **backward
compatibility** — additive, non-breaking changes, stable public
contracts (SSE keys, `stream()` signature, endpoints, prefs);
(8) **feature flags and staged rollout** — new behavior behind a
flag, one safe demo flow first (read → edit → verify → report),
expand only on evidence; (9) **traceable actions** — every tool
call, permission decision and result visible and auditable;
(10) **agent-like, not chatty** — act through tools and verify,
don't narrate.

**Why.** Feature count is not the product; a *reliable operator*
is. Each principle exists because the opposite already bit us:
bypass flows hid the z-order bug from tests, an uncapped tool
result can blow a context window, an ungated write is one
hallucination from data loss, and an untested breadth claim (an
auto-drafted skill announcing read-only mode while write tools
exist) degrades trust faster than any missing feature.

**What it costs.** Consolidation work instead of new features:
parallel permission models must merge, bypass loops must converge,
every rollout needs a flag and a demo, and "it works" claims need
log evidence. Slower cadence, higher trust. Known gaps live in
`.agent-state.md`, not in marketing copy.

---

## 10. Disciplined Agent OS (v1.26.0 consolidation)

**Decision.** The agent organs built across v1.21–v1.25 (loop,
verify-after-edit, consent, MCP hardening, subagents, audit) are
consolidated under one operating model instead of extended: a single
permission table (`ai/permissions.py`) with a capability vocabulary
drives both chat consent and mission gating; `execute_tool` is the
single audited choke point; subagents ship **off by default** behind
`subagents_enabled`; tool names are frozen (operator names like
`workspace.edit_file` are documented aliases, never renames);
phantom tools (`web_search`, `read_current_page` toggles for tools
that never existed) are deleted, not implemented; unknown tool names
run free because the closed dispatcher cannot execute them. The
operator manual is `MANUS.md`.

**Why.** Each consolidation exists because the alternative already
bit us: overlapping CONFIRM/AUTO sets answered the same question
two ways; per-caller audit lines meant some paths were trailed and
some weren't; an unflagged pool burned LLM calls unconditionally;
toggle entries for nonexistent tools were fake breadth served to
the UI. One table, one trail, one flag each.

**What it costs.** Two deliberate behavior changes: subagents no
longer fire unless enabled in Settings → GENERAL, and destructive
shell text parks even in `auto` mode. Both are the spec, not bugs.
The mission-context `mcp__` carve-out remains the single documented
exception (supervised context + kill switch).

---

## 11. Lint as a gate, not a rewrite

**Decision.** The tree is gated by `ruff` (`ruff.toml`) in CI. The
rule set is curated: real-bug families on (pyflakes, bugbear, import
order, typing modernization), pure formatting off (`E501` line
length, `E701`/`E702` one-line statements, `E402` deferred imports,
`UP031`/`UP032`). The frozen voice modules and user/generated code
(`plugins/`, `skills/auto_generated/`) are excluded by policy.

**Why.** A lint gate that demands a cosmetic rewrite of a working
codebase gets disabled. Catching unused names, shadowed globals and
modern typing is worth it; re-wrapping 130 long lines is not. The
gate also *found real bugs* — an undeclared global in the clipboard
loop meant captured suggestions were silently dropped.

**What it costs.** A curated ignore list is a maintenance promise —
each ignored rule needs a reason here, and widening the set later is
its own batch. Coverage is reported, not yet enforced by threshold.

## 12. One blueprint, many route modules

**Decision.** The `/api` surface is a single Flask blueprint (`bp` in
`routes/_common.py`) whose handlers live in per-domain
`routes/api_*.py` modules; `routes/api.py` is a thin aggregator that
just imports them.

**Why.** A 58 KB single file is where contributors stop reading. The
split keeps every URL and endpoint name identical — proven by diffing
`app.url_map` before and after — while letting a change touch one
domain. Shared imports and helpers stay in exactly one place.

**What it costs.** Handlers now resolve shared names from their own
module, so a test that used to patch `routes.api.get_client` must
patch `routes.api_chat.get_client`. Keep the aggregator import-only.

## 13. The frontend stays one file (for now)

**Decision.** `static/js/app.js` stays a single ~127 KB script wrapped
in one IIFE. We are *not* splitting it into multiple files or ES
modules yet; the API split (decision 12) was the one worth doing now.

**Why.** Unlike `routes/api.py`, the frontend can't be split
mechanically: the whole file lives inside one top-level IIFE
(`(function(){ … })();`), so no two parts share scope and every
cross-reference would break. The only real paths are a full ES-module
conversion (`<script type="module">` + `export`/`import` for ~100
shared symbols) or a global-namespace rewrite — both are large,
delicate rewrites of a stable UI whose only automated guard is the DOM
smoke. The payoff (readability) doesn't yet outweigh the regression
risk on a personal tool.

**What it costs.** The UI monolith stays large. Revisit when a build
step or a second contributor exists — then the conversion is its own
batch, with the smoke suite expanded first. Until then, every *big*
change gets a written update here.

---

## 14. Boot-settle retry for MCP servers, not a transient verdict

**Decision.** `mcp/runtime.py:start_all()` makes two passes: it starts
every enabled server, and if any failed it waits for the boot burst to
settle (20s) and tries those failures again. The `services` health row
is a boot snapshot, so a server that died in the burst and would have
recovered on its own must not read as `degraded` for the whole session.

**Why.** MCP stdio servers are child processes launched by `npx`/`uvx`.
Under a cold cache, on a machine already loading modules, prewarming
Chromium and starting the tray, one can exit mid-handshake
("Connection closed") and then start perfectly a minute later — start
it on demand (`POST /api/mcp/start`) and it comes up. The older code
retried once *inside* the burst and then froze the failure:
`GET /api/health` would show `mcp: ok` beside `services: degraded`,
which is worse than useless to someone reading the verdict.

**What it costs.** A genuinely broken server adds one 20s wait before
the verdict lands (in a daemon thread — boot stays non-blocking and
the check labels the gap "still starting"). The retry is bounded: one
extra pass, no polling, no loop.

---

## How to use this document

- **Proposing a change?** If it contradicts a decision here, either
  update this file in the same batch or argue why the decision has
  expired. Silent contradictions are how architecture rots.
- **Reviewing a change?** Ask which decision it touches. "No
  decision" is a valid answer for small things; "I didn't think
  about it" is not.
- **New contributors?** Read `ARCHITECTURE.md` for *what exists*,
  this file for *why*, `TESTING.md` for *how we know it works*.
