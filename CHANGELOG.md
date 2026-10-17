# Changelog

All notable changes to JARVIS. Versioning: **vMAJOR.MINOR.PATCH** —
bump MINOR for big feature batches, PATCH for fixes
(`config.VERSION` is the single source of truth).

## [Unreleased]

- **Frontend split deferred.** `static/js/app.js` stays one IIFE for
  now; a real split needs an ES-module conversion (see `DECISIONS.md`
  #13). Recorded here so the decision is visible in the release log.

## [1.33.2] — 2026-10-17

Documentation. `ARCHITECTURE.md` gains **The voice command path (end to
end)**: the two push-to-talk capture routes (the overlay HUD's
`/api/listen` on the host mic, and the web mic's `/api/transcribe` in
the browser), how both funnel into the same `/api/command` turn, and
then skill dispatch → LLM stream → `speak_async` output. It also names
the traps: STT is a second provider (Groq, not the chat model),
`dispatch()` is first-match-wins so a broad skill can swallow a spoken
command, and `/api/listen` blocks for the pause the user leaves.

## [1.33.1] — 2026-10-17

Fix the MCP start path, which could leave the health row `degraded`
with orphaned `npx`/`node` children on a loaded machine:

- A failed handshake now closes the transport and session context
  managers it opened, so a dead server no longer leaks its child
  process (and pipes).
- A start slower than the 45s join is marked abandoned and closes its
  own handle when the thread finishes, instead of lingering as an
  unreachable server that nothing can call or stop.
- A failed start is retried once before the server is reported down.

Six new tests cover the teardown, the retry, and the abandon path.

## [1.33.0] — 2026-10-17

The 58 KB `routes/api.py` is now nine per-domain modules behind one
shared blueprint. `routes/_common.py` holds the imports, helpers and
the `bp` object; each `routes/api_*.py` registers its own slice
(chat, skills, market, reasoning, desktop, memory, mcp, voice, core).
No URL, method or behaviour changed — `app.url_map` is byte-identical
before and after and the suite still passes — but tests that patched
the old module namespace now target the module that holds the code.

## [1.32.0] — 2026-10-17

Hardening and provability. The LAN token check is now constant-time
(`hmac.compare_digest`). A curated `ruff` config and coverage
reporting now gate CI, and the whole tree is lint-clean — which also
uncovered a latent clipboard bug (captured suggestions never
accumulated because the loop reassigned a global without declaring
it). New match-only skill diagnostic: `GET /api/skills/match?text=…`
reports which patterns a phrase hits (flagging conflicts) and which
skill last actually answered — it never runs a handler.

## [1.31.0] — 2026-10-15

Module permission diff — reinstalling a module can no longer
silently gain access. CHECK now reports added and dropped
permissions versus the installed manifest, with an amber warning
when the candidate asks for more. Fresh installs and broken
manifests report honestly instead. WAL sidecar files ignored.

## [1.30.0] — 2026-10-15

Review-fix batch — an external review listed twenty weaknesses; four
survived verification against the code (the rest were already fixed,
already covered, or declined with reasons in the session notes).
WAL journal mode on the shared memory database (background writers
stop blocking readers), a global thread-crash hook (unhandled
background exceptions reach the log file instead of vanishing under
pythonw), token auth for off-machine API writers (`X-Jarvis-Token`
vs `JARVIS_TOKEN`; localhost and all reads untouched), and a pinned
`requirements-lock.txt`. No behavior change on localhost.

## [1.29.0] — 2026-10-14

Drafter quality bar (principle 6) — seen live: an auto-drafted skill
passed isolation and auto-approved while telling the user "no
file-writing tool exists". Now handler code and the registered
description are screened for capability lies; a hit parks the draft
for a human verdict (with the reason shown) instead of
auto-approving, and the generation prompt teaches honesty up front.
Explicit manual approval still works — the human read the warning.
No behavior change for honest drafts.

## [1.28.0] — 2026-10-14

Boot-race fix — the v1.27.0 restart wedged because Flask's first
import landed inside the MCP SDK's `sys.modules` surgery (which ran
on every server spawn: ~11 windows per boot) and died with "cannot
import name 'all_servers' from 'mcp'". The surgery now runs once per
process (cached, failures cached too), and both entry points
pre-warm it single-threaded before background threads spread — no
window left for a concurrent local import to fall into.

## [1.27.0] — 2026-10-14

Audit panel — the trail becomes user-visible where users look.
New AUDIT settings tab: newest-first trail rows with OK/FAIL status
chips parsed from the shared log, one REFRESH reload. No new
endpoints (reads the existing `/api/audit` tail), no new CSS (reuses
set-list/set-row/schip/dbtn), every row escaped. Shipped with eight
surface tests and a Playwright smoke that clicks the real tab.

## [1.26.1] — 2026-10-13

README gallery batch: the README now shows the product instead of
only describing it — a "See it in action" section with the live
dashboard and the HUD overlay side by side, and the promo-video
link becomes a clickable poster frame. All captures are real (no
mockups): the dashboard shot is the running v1.26.0 deck, the
poster is a frame of the committed video.

## [1.26.0] — 2026-10-13

Disciplined Agent OS consolidation — no new product surface. The
organs built across v1.21–v1.25 now obey one operating model
(`MANUS.md` added, `DECISIONS.md` entry 10).

### Added
- **MANUS.md** — the operator manual: loop architecture, tool
  schema format with the `workspace.*` name mapping (aliases,
  never renames), permission model, subagent bounds, verification
  workflow, audit trail, feature-flag table, safe extension
  guide, troubleshooting, security notes.
- **Unified permission table** (`ai/permissions.py`) — one tier +
  capability vocabulary (`fs:read/write/delete`, `shell:exec`,
  `shell:exec:destructive`, `mcp:invoke`, `network:fetch/post`)
  driving both chat consent and mission gating; the legacy
  AUTO/CONFIRM sets are frozen views. Destructive shell text parks
  even in `auto` mode.
- **Choke-point hardening** — `execute_tool` validates args against
  `TOOL_SCHEMAS` (required + types, integers/booleans coerced from
  strings) and redacts secrets before anything model-bound.
- **Settings toggles** — Sub-agents and Tool approval in GENERAL;
  consent replies render distinctly (amber, dashed rail).

### Changed
- **Subagents default off** (`subagents_enabled: false`) with max 2
  workers, truncated merge evidence, cancelled stragglers, and
  spawn/complete audit events.
- **Phantom tools deleted** — `web_search` and `read_current_page`
  were user-toggleable but had no schema and no implementation;
  the toggle list is now covered by a test that fails on the next
  phantom. Unknown tool names run free (the closed dispatcher
  cannot execute them; the model self-corrects).

### Fixed
- Three test-caught issues: stacked duplicate return in the new
  tier function, mention-matching in destructive patterns (now
  per-segment command matching), and a lazy-SSE lesson re-applied
  to the new smoke test.

## [1.25.0] — 2026-10-13

Trace + flags, zero new features — the first consolidation batch
under the agent-OS principles: every action auditable, every rollout
gated, one safe demo flow as evidence.

### Added
- **Shared agent audit trail** — new `system/audit.py`: chat-loop
  tool calls, consent approvals/denials and OS-mission steps land in
  one append-only file in one line format. `execute_tool` is the
  single choke point that writes the execution lines, so every
  caller (loop, missions, verdicts, demos) is trailed uniformly;
  the OS mission logger and the loop's old ad-hoc audit lines now
  delegate to it instead of each keeping their own.
- **GET /api/audit** (118th endpoint) — newest-first tail of the
  trail (capped at 200 lines), so the dashboard or any client can
  show what ran, what was denied, and why. Never raises — worst
  case an empty list.
- **`subagents_enabled` pref flag** (default on, preserving shipped
  behavior with an opt-out) — the parallel pool now rolls out
  staged instead of firing unconditionally.

### Changed
- **Demo flow as a test, not a feature** — the principles' single
  safe flow (read → edit → verify → report) runs end-to-end through
  the real tools in `test_audit_trail.py`, with the audit lines as
  its evidence. No new skill, no new surface.

## [1.24.0] — 2026-10-13

Sub-agents + consent — JARVIS now acts like a supervised agent.
Multi-part questions fan out to the parallel pool that sat dormant
and tested since the agent work began; state-changing tools stop
running blind and ask first.

### Added
- **Sub-agent fan-out in the live route** — a question that misses
  every skill and trips the multi-part gate (`compare`, `research`,
  `pros and cons`…) runs plan → parallel sub-tasks → merge, with
  status events while the pool works. A failed pool never surfaces:
  the normal single loop answers instead, so the worst case is a
  slower reply, never an error.
- **Allow/confirm/deny permission layer** — new `ai/approvals.py`:
  read-only tools run free; file writes, deletes, shell, window
  control and all third-party MCP side effects park as numbered
  requests (`[awaiting approval #3]`) and the model asks in plain
  words. `allow 3` runs the parked call immediately and its result
  comes back as the reply; `deny 3` refuses without running.
  Requests expire after 10 minutes, the queue caps at 20, long
  results trim for speech, and unknown numbers answer honestly.
- **`tool_approval` pref** (`ask` by default, `auto` runs
  everything) — flips the whole layer without a restart.

### Fixed
- **Two real bugs the new tests caught**: the agents branch
  returned early past the reply-recording `finally` (history,
  speech and memory extraction silently skipped — now the branch
  feeds the same `collected` path), and it skipped the `[DONE]`
  terminator the HUD waits for.

## [1.23.0] — 2026-10-13

MCP tools safe to offer — the wiring existed (the route appends live
MCP schemas, the loop calls `mcp__server__tool`), but it had never
been tested and three sharp edges could ruin a request: one
malformed server entry raised through the schema build and killed
the whole AI reply, a catalog built mid-spawn blocked behind the
runtime lock for up to 45 seconds per server, and tool order
followed server start order.

### Changed
- **Bounded MCP snapshot** — `mcp_schemas()` now builds from
  `runtime.tools_snapshot()` (1-second lock budget, mirroring the
  module scan's `_running_snapshot`): a hot lock serves the
  last-known-good list instead of blocking the user's reply, and the
  whole path never raises — worst case the round goes out with no
  MCP tools rather than no answer at all.
- **Per-entry schema validation** — entries missing names, non-dict
  payloads and non-dict input schemas are skipped or replaced
  individually; one sick server costs its tools, never the request.
- **Deterministic catalog** — schemas sort by name, so the model
  sees the same tool list no matter what order servers started in.

## [1.22.0] — 2026-10-13

Workspace tools + mandatory self-verification — JARVIS edits files
like a careful coding agent: surgically, and never claiming a write
it did not check. The loop's 30 tools become 31.

### Added
- **`fs_replace` tool** — exact-match surgical editing: replace one
  text block without rewriting the whole file. Backs up first like
  every other mutation tool; zero matches report `[not found]`; two
  or more matches refuse as `[ambiguous]` unless `replace_all` is
  set, so a sloppy match can never silently rewrite the wrong
  places. Approval-gated in OS mode like `fs_write` (never runs free
  in the autonomous loop).
- **Verify-after-every-edit** — `fs_write`, `fs_append` and
  `fs_replace` now append a verify verdict for code files: Python is
  compiled in-process (parses, never runs), JSON is parsed,
  JavaScript goes through `node --check`. A broken edit reports
  `VERIFY FAILED` with the location loudly — so the model sees its
  own breakage in the tool result and fixes it in the next loop
  round instead of announcing success. Plain-text files stay quiet;
  a missing or timed-out `node` degrades to "verify skipped", never
  a false failure.

## [1.21.0] — 2026-10-12

Agent-loop hardening — the bounded tool loop already existed
(skills first, then the model with its 30 tools and live MCP
servers, up to 15 rounds); this batch makes it behave like a
properly run agent: no dead-model taxes, bounded context, and
never silence.

### Added
- **Model cooldown rotation** — a provider saying "gone" (campaign
  ended, 404, retired) now cools that model for ten minutes instead
  of retrying it on every request; the entry expires on its own, so
  a revived model rejoins rotation without a restart. This removes
  the live ~32-second dead-model tax from every reply.
- **Step progress on tool events** — `tool_call` payloads now carry
  `step`/`steps`, so consumers can show how deep into the budget the
  model is.
- **Guaranteed final answer** — if every round asks for another tool
  until the 15-step budget runs out, JARVIS makes one last pass with
  the tools withdrawn and answers from what the tools already found
  (and a plain fallback sentence if even that yields nothing — the
  old loop fell off the end with no reply at all).

### Changed
- **Default fallback chain drops the dead model** — the
  campaign-ended `qwen3.8-flash:free` leaves the rotation; the chain
  now starts at Mimo.
- **Tool results capped at 6,000 characters** before they are fed
  back into model context — one runaway MCP or terminal result can
  no longer blow a small free-model window mid-loop. Built-in tools
  already cap below that (unchanged), and the dashboard keeps its
  300-character display cap.
- **Last-round stream reopen skipped** — the loop no longer opens a
  streaming response on the final budget round just to discard it.

### Fixed
- **Test isolation for the cooldown table** — `test_fallback_status`
  clears it in setUp, now that a failed model stays cooled across
  tests in the same process.

## [1.20.2] — 2026-10-12

Trust-and-polish batch — no new features, only product perception:
copy tightening, status-chip consistency, and stale-number cleanup
across the site, README and dashboard.

### Changed
- **Launch page copy rewrite** — the hero subhead drops from four
  sentences to two product statements; the honest box no longer
  repeats the no-key story; the library card tightens from 46 words
  to 26 (the 18/12 counts stay — specificity is the premium);
  "Tiered search with fallbacks" becomes plain English; and the
  closing CTA points at the install steps instead of GitHub, which
  the nav already carries.
- **Stale numbers fixed** — the site said 653 tests in two places
  and the README in two more; ROADMAP still counted 150 API
  endpoints (real: 117). Skill counts unify on the exact 142.
- **Dashboard status vocabulary** — the transient chip now reads
  THINKING (matching the HUD's "JARVIS is thinking…" well), and a
  DONE chip holds ~1.6s after a reply completes before the pill
  settles back to the live health verdict; errors skip it, and the
  muted-speech path routes through the same beat.
- **Module trust summary** — the installed / active / inactive /
  failed counts render as colored status chips (the same vocabulary
  as the rows below), and capability chips cap at three with a +N
  overflow chip.
- **First-run card reordered** — the two TRY IT steps come first;
  the optional API-key step moves to the end with a visible OPTIONAL
  chip (listing an optional step as "1" undercut the key-optional
  message).
- **Safe-mode wording** — the SYSTEM verdict line and the pill
  tooltip now pair "some features are off" with "core skills still
  work".
- **Library import row** — the raw JSON schema dump in the LIBRARY
  help line becomes one plain sentence.

### Fixed
- **README dead copy** — the no-key story is told once instead of
  four times, the eight-line HUD bullet shrinks to three, and the
  GIF-placeholder comment is replaced by the promo-video link that
  now exists.
- **`docs/overlay.png` recaptured** from the real running deck
  (PrintWindow — the window's own pixels only), replacing the
  v1.19.1 screenshot.

## [1.20.1] — 2026-10-11

Promo-video asset batch: the 30-second feature tour, built locally
with ffmpeg from real product captures — no AI generation, no cost.

### Added
- **`docs/media/jarvis-promo-16x9.mp4`** — the 16:9 cut (30.0s,
  1920×1080) committed to the repo and served by GitHub Pages at
  `/media/jarvis-promo-16x9.mp4`; the 9:16 vertical cut was delivered
  as a local download only, to keep the repository lean.

### Changed
- **README badges refreshed** (v1.20.1, 665 passing tests) and the
  promo video linked under the site line.

## [1.20.0] — 2026-10-11

UI and error-noise cleanup batch, driven by a live HUD screenshot:
the reply was prefixed with nine `[fallback to Mimo ●]` banners.

### Fixed
- **Fallback notices are status events now, never reply text.** The
  `[fallback to X]` banner used to stream as content: it polluted the
  reply body, got stored in conversation history, and the model then
  echoed it back verbatim — one old marker bred whole rows of copies.
  `client.stream()` yields `("status", …)` instead, the SSE layer
  forwards it as its own `status` key (never collected, stored or
  spoken), the HUD ignores it, and the web dashboard shows a single
  ⇄ line in the activity log. Guarded by ten new tests.
- **Existing polluted history is cleaned automatically** — the
  conversation store strips legacy bracket markers on read and on
  record, and drops replies that were nothing but markers, so old
  sessions stop teaching the model to repeat them.

### Removed
- **34 dead API routes** — zero callers anywhere (UI, skills, system,
  tests): `/models/featured`, `/models/test`, `/auto_skills/*`,
  `/clipboard/suggestions`, `/screen/*`, `/snippets/<id>` (get/delete),
  `/overlay/state|toggle`, `/apps/*`, `/research/<id>`,
  `/sites/refresh`, `/mcp/setup|import|remove|toggle|tools|serve`,
  `/obsidian/search`, `/memory/forget`, `/prefs/reset`,
  `/autostart/*`, `/harness/pending|reject`, `/history/delete`. The
  `/apps/*` family was doubly dead — it targeted a `system/apps.py`
  that no longer exists. Endpoint count: 150 → 117.
- **3 dead CSS rules** (`.btn-label`, `.crit`, `.ui-container`) and one
  orphaned import (`classifier`) left behind by those routes.

## [1.19.3] — 2026-10-11

HUD rendering fix batch, found by regenerating the docs screenshot
straight from the real overlay with PrintWindow (the window's own
pixels only — never the screen behind it).

### Fixed
- **The Alt+Space HUD no longer buries its own furniture.** Every mode
  switch recreates the deck surface (background plates + accent lines)
  via `cv.delete`/recreate, and a recreated canvas item lands on top of
  the stacking order — hiding the brand diamond, the JARVIS title, the
  status dot, the close button, all six quick chips, the key hints and
  the COPY pill. Canvas windows (header chip, version, reply well,
  input, MIC/SEND, status) kept rendering because on Windows they are
  real child HWNDs, so the deck simply looked oddly empty. The surface
  is now lowered back under the content (`cv.tag_lower("chrome")`),
  guarded by a UI-surface regression test.

### Changed
- **`docs/overlay.png` recaptured** from the real v1.19.3 deck
  (expanded state, live version chip, honest sample reply) — replacing
  the stale pre-HUD-5.0 screenshot.

## [1.19.2] — 2026-10-11

Docs micro-fix batch — website presence in the README plus one stale
badge caught while generating the GitHub social-preview/avatar PNGs.

### Changed
- **README now points at the website in three places** — an enriched
  site line under the badges (what the site actually contains), a
  "Just browsing?" callout after the install steps, and a new
  **Links** section at the end (website, repo, module guide, demo
  script, changelog).
- **Version badge fixed** — it still read v1.18.0; it now tracks
  `config.VERSION` (v1.19.2).
- (Companion assets, not committed: `assets/jarvis-avatar.png`
  1024×1024 and `assets/jarvis-social-preview.png` 1280×640 were
  rendered from the shipped SVGs for the GitHub repo avatar and
  social preview — GitHub rejects SVG uploads.)

## [1.19.1] — 2026-10-11

Live-verification micro-fix for the module ecosystem, found by hitting
the running v1.19.0 app: `GET /api/modules` could hang for tens of
seconds right after boot.

### Fixed
- **The MODULES API can no longer hang behind a slow MCP spawn** —
  `runtime.start_server` holds its runtime lock for the entire
  server spawn (up to 45s per server), and `scan()` was asking for
  per-module running status through that lock. It now takes ONE
  bounded snapshot (gives up after ~1s and honestly reports "not
  running" while a spawn is in flight), so the request always
  returns.
- **Boot no longer spawns module MCP servers itself** — at boot the
  `modules` service only writes the server configs; the `mcp`
  service starts them immediately after, as it always has. Same end
  state, without a multi-server spawn stall in a synchronous boot
  step.
- +1 regression test (653 total): holds the runtime lock in another
  thread and asserts `scan()` returns within bounds.

## [1.19.0] — 2026-10-11

The extensibility batch: a real module ecosystem so JARVIS can grow
like a product platform, not a fixed app. Skills, MCP integrations and
community drop-ins all flow through one governed framework — declared
permissions, validated installs, honest failure states — with a
shipped starter library and author templates to match.

### Added
- **Module framework** (`system/modules.py`) — modules are folders
  with a `module.json` manifest (schema v1): id, version, author,
  description, capabilities, a fixed permission vocabulary, docs and
  examples. Two kinds ship: `skill` (a `skill.py` entry registering
  @register skills, validated with the same AST rules + hijack guards
  as community plugins) and `mcp` (a server spec wired into
  `mcp.manager`/`mcp.runtime` on activation).
- **Install / lifecycle** — install from a local folder or `.zip`
  (validated BEFORE anything copies; zip-slip, absolute-path, size
  and file-type guards), activate ⇄ deactivate, uninstall.
  Active / inactive / failed states persist in `modules/state.json`;
  boot re-activates exactly what you enabled via a new `modules`
  boot service that runs before MCP, so module servers are already
  configured when `start_all()` fires.
- **Starter library — 9 real modules, no placeholders**: five
  computation skills (`unit_convert`, `color_convert`, `number_base`,
  `secure_token`, `url_codec`) and four governed MCP integrations
  wrapping official servers (`mcp_fetch`, `mcp_filesystem`,
  `mcp_git`, `mcp_memory`) with declared permissions and docs.
- **MODULES tab** — installed / active / inactive / failed counts;
  per-module cards with state, kind, author and update chips, colored
  permission chips (hover shows what each means), capabilities,
  examples, an inline DOCS panel with the full README, and
  ACTIVATE / DISABLE / UNINSTALL. An install box offers CHECK
  (dry-run validation report) and INSTALL for local folders or zips.
- **Author path** — `modules/_template_skill` and
  `modules/_template_mcp` templates plus `MODULES.md`: schema table,
  permission vocabulary, safety rules, lifecycle and API reference.
  `POST /api/modules/validate` checks a package without installing.
- **Update status** — `modules/catalog.json` is a bundled
  `{id: version}` snapshot (the same shape a future remote registry
  will publish); modules newer than the catalog show an UPDATE chip,
  and missing sources read as unknown — never a fake "current".
- **API** — six new endpoints: `GET /api/modules`,
  `GET /api/modules/<id>`, and `POST /api/modules/toggle|install|
  uninstall|validate`.

### Safety
- Unknown permissions, shell metacharacters in MCP commands, entry
  paths escaping the module folder, oversized zips, disallowed file
  types and blocked code (`eval`/`exec`/`open`, import whitelist) are
  rejected with plain-English reasons before anything loads.
- A module that crashes at import rolls back every skill it
  registered and shows FAILED with the error — visible, retryable,
  never silently ignored, never fatal to boot.
- +54 tests (652 total): manifest schema, starter-library integrity
  (every shipped module validated exactly like a community one),
  install/zip/zip-slip guards, activation rollback, MCP wiring with
  needs-key detection, failed states, update flags, boot wiring, and
  the new API routes.

## [1.18.0] — 2026-10-11

The final polish pass before launch — UI, clarity and trust only. No
features, no rewrites: the same product, tightened until every visible
surface agrees with every other one.

### Changed
- **SYSTEM tab reads like a dashboard** — status values render as
  tinted pill chips (`.schip`, one variant per status: ok / info /
  warn / degraded / unknown) instead of loose colored text, so the
  verdict of each row is scannable at a glance.
- **Warnings are no longer buried** — `warn` and `error` log entries
  get a colored rail and a tinted background, not just a text color;
  a failed step is findable in a wall of output.
- **The screen tells one story** — the center tagline now follows the
  health verdict (`SYSTEM ONLINE` / `NEEDS ATTENTION` / `SAFE MODE ·
  SOME FEATURES OFF`) and is owned entirely by the state machine, so
  it can no longer claim SYSTEM ONLINE while the status pill says SAFE
  MODE. The idle tagline also takes the verdict's color.
- **Health banner in plain English** — degraded mode now says "Some
  features are off — mcp (…) — details in SYSTEM" instead of the
  terse "System degraded"; config warnings read "Needs attention —
  N config warnings".
- **First-run card wears a SKILLS ACTIVE badge** — keyless mode is
  presented as a feature, not a gap: the green chip states outright
  that local skills are working right now, no key required.
- **Log timestamps slightly larger** for readability.

### Alt+Space HUD
- **A real listening state** — pressing MIC turns the status line and
  the pulsing status dot brand cyan (the app's listening color), the
  mic button disables until the answer arrives, and a second press can
  no longer open a second mic. Amber now means "thinking" only.
- **COPY is a pill, not bare text** — an outlined button that appears
  only when there is actually a reply worth copying, with a hover
  state that lights the border.
- **Readable key hints** — the footer separator is a middle dot
  (`↵ SEND · ESC CLOSE · ↑ HISTORY · ALT+SPACE`).
- **Input well lights on focus** — the caret position is obvious even
  over a busy window behind the deck.
- **Done is green** — a finished answer reports "Done · Alt+Space to
  recall" in brand green, errors stay red, nothing stays neutral.

### Tests
- **598 passing (+10)** — `test_ui_surface.py` guards the chip
  component and every variant, the log warning rails, the health-
  aware tagline (including "setState is the only tagline writer"),
  the plain-English banner copy, the SKILLS ACTIVE badge, the HUD
  cyan listening color, middle-dot hints and the COPY pill.

## [1.17.1] — 2026-10-11

Two live-verification findings from the 1.17.0 rollout, both about
"what the user actually sees":

### Fixed
- **Banner strip cleared the topbar hairline** — the pinned strip sat
  at 60px while the topbar's final animated height is 62px, so a
  warning banner covered the topbar's glowing hairline exactly when
  it showed. Pinned at 64px now (2px gap).
- **First-run guidance on narrow windows** — below 1200px the log
  panel is hidden, so the onboarding card rendered inside an
  invisible parent while simultaneously suppressing the starter
  chips, leaving a fresh user with no guidance at all. The chips now
  only yield to an onboarding card that is actually visible
  (`offsetParent` check).

### Tests
- **588 passing (+1)** — `test_ui_surface.py` gained the narrow-
  window guard for the starter-chip fallback.

## [1.17.0] — 2026-10-11

The "genuinely ready" pass — product-trust and surface polish across
the app UI, the Alt+Space HUD and the first-run flow. No new features;
the same functionality now reads as a product instead of a prototype.

### Fixed
- **Status banners were buried behind the topbar** — the key/health
  strips rendered at document top under the fixed topbar's gradient,
  so the honest "skills-only mode" and "system degraded" messages
  were effectively invisible. Both banners now live in a pinned
  strip just below the topbar (`class="banners"` wrapper), stacking
  when both show. Guarded by tests.
- Stale hardcoded version in the template fallback (`v1.16.0`) —
  now `v{{ version }}`, so it can never lie again.
- Stray brace in `style.css` (starter-chip block).

### Changed
- **Alt+Space HUD 5.0** (`system/overlay.py`) — brand-aligned
  refresh: diamond mark (matches the logo), brand-green accent with
  cyan tails, a friendly "Ask JARVIS anything — Enter to send" hint
  in the empty input (cleared by the first keystroke, restored when
  emptied), and a pulsing **"JARVIS is thinking…"** line in the
  reply well so the deck is never a dead empty panel while the first
  token is in flight. Errors render as a plain-English red ⚠ line
  (never raw `[error]` plumbing), "(no reply)" becomes an actionable
  sentence, and every status string is title-case plain English
  (Ready / Thinking… / Listening… / Done / Something went wrong).
  Thread model, SSE stitching and the public API are untouched.
- **First-run card** — a dedicated onboarding card (not a bare
  settings list) that leads with "Local skills already work — no
  key needed. Add one any time to unlock AI chat" and marks the key
  step **Optional**, so skills-only mode reads as a product state,
  not an error state.
- **SYSTEM tab** — opens with a verdict card (READY / ATTENTION /
  SAFE MODE + one plain-English line + version/uptime + REFRESH),
  every row carries a status-colored left border (green/amber/red),
  and config warnings sit in a titled "CONFIGURATION — WORTH FIXING"
  box instead of an anonymous amber block.
- README HUD description updated to match the shipped behavior.

### Tests
- **587 passing (+9)** — new `tests/test_ui_surface.py` guards the
  template landmarks, the banner wrapper, the cache-buster, the
  version fallback, the new CSS components, and the overlay's brand
  palette and input hint.

## [1.16.2] — 2026-10-10

The public site, rebuilt for prime time — and now verified live at
**https://youssef-devolopment.github.io/jarvis/** (GitHub Pages,
project site served from `/docs` on `main`).

### Changed
- **Landing page rebuilt** (`docs/index.html` + new `docs/styles.css`)
  — nine sections: hero (two-column with a live-session terminal and
  a SYSTEM status card), value proposition, six core features, the
  skills-first pipeline ("why JARVIS"), 3-step install with copy
  button, the verified demo flow with use cases, an eight-point
  trust/reliability grid, CTA band and footer. Styles split into a
  proper design-token stylesheet (responsive: 920px/640px
  breakpoints, sticky glass nav, mobile stat wrapping).
- **Project-pages safe** — every asset path is relative, so the site
  works under the `/jarvis/` base path; verified by simulating
  GitHub Pages serving locally (junction `/jarvis` → `docs`, all
  assets 200, 104 CSS rules applied, zero console errors).

## [1.16.1] — 2026-10-10

Brand identity — a real logo set, consistent from a 16px favicon to
the README header. The mark extends the product's existing language
(the diamond ◆, the green→cyan accent) into a **gradient diamond gem
with a negative-space J**: one geometric form that adapts to any
background and stays legible at favicon size.

### Added
- **Logo set (SVG, all editable vectors)** —
  `assets/jarvis-logo.svg` (self-contained dark banner for the
  README/GitHub, renders correctly in light and dark themes),
  `assets/jarvis-logo-mark.svg` (transparent icon-only mark),
  `assets/jarvis-favicon.svg` + `docs/favicon.svg` (bolder J cut
  for 16px legibility), `docs/logo-dark.svg` and
  `docs/logo-light.svg` (theme lockups: gradient/white and deep-ink
  variants with the JARVIS wordmark).
- **Landing page branding** — SVG favicon + the real mark in the
  nav (replaces the ◆ text glyph).
- **Brand-asset guard tests** (`tests/test_branding.py`, 4) —
  the six files must exist, parse as SVG with a viewBox, contain no
  external fetches, and lockups must carry wordmark + mark geometry.

## [1.16.0] — 2026-10-10

Phase 2 of productization — JARVIS now *reads* like a product. The
interface tells the truth at a glance (the topbar pill carries the
live health verdict), an empty console doubles as a one-click tour,
errors explain themselves in plain English, and the repo finally
leads with what JARVIS does for a person instead of what it is made
of: a rewritten README, a GitHub-Pages-ready landing page, and a
verified 90-second demo script. 574 tests, 144 API endpoints, 142
shipped skills.

### Added
- **Health verdict in the topbar** — the status pill now shows the
  product state from `/api/health` whenever idle: green **READY**,
  amber **ATTENTION** ("Minor issues"), red **SAFE MODE** ("Some
  features are off"), each with a plain-English tooltip; clicking
  the pill opens Settings → SYSTEM. Transient states (LISTENING,
  PROCESSING, TOOL CALL) keep their own colors on top.
- **Starter chips** — a fresh console offers one click per
  capability: *What time is it? / Open Notepad / Search the web /
  Remind me in 1 min*. They hide the moment a command runs and come
  back on a cleared console; the first-run onboarding card takes
  priority when present.
- **Plain-English SYSTEM tab** — check rows use human names
  (Configuration, API key, MCP servers, Skill drafts…) and the
  Overall row always explains its verdict in words, not just a
  colored chip.
- **Landing page (`docs/index.html`)** — a self-contained product
  page (hero, live-session terminal card, three value points,
  3-step install with copy button, footer links), complete without
  screenshots; serve it via GitHub Pages from `/docs` when ready.
- **Demo script (`DEMO.md`)** — the one flow to show people: a
  timed 90-second run-of-show (voice → app control → web → note →
  self-spoken reminder), per-step fallbacks so nothing is fragile,
  and a recording/capture plan. Every command in it was verified
  end-to-end on a live session.
- **Static-asset cache buster** — `app.js`/`style.css` are served
  as `?v=<version>`, so an upgrade always loads fresh CSS/JS with
  no manual hard-refresh (`routes/views.py` passes `VERSION`).

### Changed
- **README rewritten product-first** — 10-second value prop, daily
  use cases, who it's for, a core-vs-optional table, "how it works"
  in three lines, and a trust-and-safety section; the deep
  developer material moved below the product story. First-run
  banner and console placeholder reworded in plain English.
- **Errors surface their reason** — a failed command shows the
  server's message ("Command too long.") instead of a bare
  "Error: HTTP 400".

### Fixed
- **Pill stuck on SPEAKING** — skill replies stream text without
  audio; the UI flipped to SPEAKING on the first delta and the
  end-of-stream guard then never reset it. Text now stays
  PROCESSING while streaming, SPEAKING is set only when audio
  actually starts, and muted voice no longer enters the state at
  all.

## [1.15.0] — 2026-10-10

Phase 1 of productization — JARVIS now explains itself. The moments a
first-time user meets (install, first boot, first failure) got one
honest, actionable voice: the console boot block, the desktop toasts,
the preflight script and the post-boot health verdict all answer the
same three questions — which mode am I in, what works, what do I do
next — and all derive from the same `/api/health` snapshot the UI
banner uses. 572 tests, 144 API endpoints, 142 shipped skills.

### Added
- **`system/startup.py`** — pure, tested boot-messaging helpers (the
  product-facing voice of startup):
  - `status_lines()` — console boot block: URL, model, voice, mood,
    memory, mode, logs. Every subsystem read is guarded: a broken
    memory DB or mood store degrades to an "unavailable" line, never a
    crashed boot.
  - `health_block()` / `safe_mode_block()` — the post-boot verdict
    from the health snapshot: "OK" (or "still starting: X" while async
    services are in flight — never claim healthy early), "WARN — N
    config warning(s)" with the first warning and where to look, or an
    explicit SAFE MODE block naming what broke, what the user loses,
    what still works, and the exact next step.
  - `ensure_port()` — probe-bind before booting the world: a busy port
    now fails in seconds with plain words and exit code 3, instead of
    werkzeug's terse exit 1 after every subsystem already started.
  - toast helpers — the desktop boot toast states the mode (safe
    mode + failed services, or skills-only); a deferred toast fires
    only when async services actually failed.
- **Capability-aware preflight (`check.py`)** — same 11 checks, now
  with three exit codes anyone can branch on: `0` ready (optional
  gaps reported as capabilities, not failures), `1` core broken,
  `2` key missing/invalid → JARVIS starts skills-only. Adds a
  "Capabilities:" block (AI chat, voice input, browser skills,
  memory), one actionable hint per check printed only when that check
  failed, a lenient "Config loads" (a fresh placeholder install is
  key-pending, not broken), and explicit core/key/optional buckets.
- **Setup summary speaks first-run** (`setup.ps1`) — launch-first:
  JARVIS starts with no API key at all (skills-only), then add one in
  Settings → GENERAL; branches on the new check.py exit codes so a
  fresh install is never told to "fix the ✗ items" for a placeholder
  key.

### Changed
- **`run.py` console boot** — friendly first-run block (version, URL,
  model, voice, mood, memory, logs) with guarded reads; skills-only
  mode prints what works now, what doesn't, and both fix paths; busy
  port fails fast before services boot (exit 3, lock auto-released).
- **Post-boot health verdict** (`server.schedule_health_log`) — the
  reporter that writes the log line now takes an `on_summary` callback
  receiving the same snapshot, so console output and desktop toasts
  can never disagree with the log line or the UI banner. Console
  prints the verdict (ok / still-starting / warn / safe mode);
  desktop toasts only when degraded.
- **Config audit +2** (`config.audit_settings`) — template-placeholder
  GROQ/TAVILY keys ("paste/your/example/replace") are called out even
  when they pass the prefix checks; enabled npx-based MCP servers with
  no Node.js on PATH warn with an install hint instead of leaving
  those servers silently degraded at boot.
- **DB failure degrades with instructions** (`errors.register`) —
  `sqlite3.Error` now returns a structured 503 ("Memory store is
  unavailable", locked/corrupt diagnosis, restart or restore from
  `memory/backups/` next step) instead of an opaque 500 traceback.
- **Desktop boot toast** (`system/launcher.py`) — "JARVIS is running"
  now states the mode: safe mode with the failed services named, or
  skills-only, or the plain Ctrl+Alt+J hint when healthy.

### Verified
- 572 tests (+42) including the new `tests/test_first_run.py`
  (boot messaging, verdicts, toasts, port probe, preflight
  buckets/exit codes/capabilities); fresh-copy suite (no `.env`)
  572 OK; check.py live 11/11 exit 0; live console: friendly busy-port
  exit 3, boot block, "still starting"/verdict honesty; desktop
  restart healthy on 1.15.0.

## [1.14.1] — 2026-10-07

Documentation batch — the repo now carries its own operating manual.
No code behavior changes; counts unchanged (530 tests, 144 API
endpoints, 142 shipped skills).

### Added
- **`TESTING.md`** — how this repo is verified: dependency groups and
  the minimal test install, full/single test runs with the PowerShell
  5.1 quirks that actually bite here, all 45 test files grouped by the
  seam they protect, the fresh-copy/clean-env procedure (and what
  class of bug it catches), health verification across its five
  layers, an exact definition of "CI green", manual smoke tests for
  voice/browser/MCP/scheduler/hotkeys/tray/UI, a degraded-system
  playbook, hermetic test-writing conventions, and a per-change
  definition of done.
- **`DECISIONS.md`** — the architecture story as deliberate choices
  with costs: skills-first execution, SQLite local memory, graceful
  degradation, one service registry, health surfaced not hidden,
  config auditing (including deliberate silences), Windows-native,
  secrets/local data hygiene — plus how to use the document when
  proposing or reviewing changes.
- **`ROADMAP.md`** — Completed (v1.0→v1.14.1 table), open threads,
  Next 30 days (lite health parity, MCP preflight, backup restore,
  health history, single-shot auto-heal, docs polish), Next 90 days
  (network auth, packaging, plugin SDK freeze, metrics, E2E smoke),
  long-term vision (great personal assistant → trusted platform),
  and explicit non-goals.

### Changed
- README: version badge → v1.14.1; community-friendly bullet links
  the three new documents.

## [1.14.0] — 2026-10-06

Reliability batch: health problems are no longer something you have
to go looking for — a persistent page banner shows warn (amber) /
degraded (red) states everywhere, a "Health after boot" line lands in
the log shortly after startup, and the config audit learned two more
external-key format checks. A silent-fallback audit confirmed the
remaining fallbacks already log honestly. 530 tests, 144 API
endpoints, 142 shipped skills.

### Added
- **Persistent health banner** — polls `/api/health` on load and every
  60s (paused while the tab is hidden, refreshed on visibility):
  amber strip with the config-warning count for `warn`, red strip
  naming the degraded checks and failed boot services for
  `degraded`. Auto-hides when healthy; "Open SYSTEM" jumps straight
  to the dashboard; not dismissable while unhealthy — by design.
- **Post-boot health line** — both entry points (run.py console and
  the desktop launcher) schedule `server._log_health_summary()`:
  after `HEALTH_LOG_DELAY_S` (20s) one line lands in
  logs/jarvis.log — `Health after boot: ok` at INFO, or a WARNING
  naming degraded checks, the specific failed boot services,
  the config-warning count, and any service still starting (async
  MCP/voice warmups). Daemon thread: never blocks boot, never
  raises.
- **Key-format checks in the config audit** — `GROQ_API_KEY` must
  start with `gsk_` and `TAVILY_API_KEY` with `tvly-` when set
  (Tavily is read from the environment; the test pins it for
  hermeticity). Unset keys stay silent, and the deliberate
  deepseek-model-on-foreign-proxy silence rule is untouched.

### Changed
- **Silent-fallback audit (no code needed)** — the remaining
  fallbacks were verified to already be honest: browser
  goto failures log "trying webbrowser fallback", skill replies
  carry `source: "skill"`, skills-only answers carry
  `no_key: true` + a setup hint, MCP partial starts degrade their
  row, voice warmup failures degrade theirs. Out of scope by
  standing constraint: internals of `voice/output.py`.

Tests: +5 config-audit, +5 health-summary.

## [1.13.0] — 2026-10-06

Lifecycle + data-integrity batch: every background service can now be
stopped or restarted at runtime — from the SYSTEM tab or one POST —
migrations snapshot the memory DB before touching it, and the health
probe runs `PRAGMA integrity_check` so silent corruption is reported
instead of discovered mid-query. 520 tests, 144 API endpoints, 142
shipped skills.

### Added
- **Service stop/restart API** — `POST /api/services/<name>` with
  `{"action": "stop" | "restart"}`. ServiceSpecs gained an optional
  `stop` handler: 9 services are stoppable (reminders, dream,
  scheduler, guard, clipboard, time tracker, screen context, MCP
  servers, folder sentinel), everything except the boot-only
  hotkey/tray listeners is restartable. Unknown names, missing
  handlers and boot-only listeners refuse with a structured 400 that
  says exactly why — never a half-cycled service. A failed stop does
  not abort a restart; the start's own record wins so the row always
  reflects what is actually running.
- **SYSTEM tab lifecycle buttons** — RESTART on every restartable
  service row, STOP on the stoppable ones: click → POST → automatic
  health refresh, FAILED in place when the server refuses. The
  buttons come from `stoppable`/`restartable` flags in the health
  snapshot, so API and UI can never disagree; mark-only rows (the
  desktop Flask thread) get no buttons.
- **Pre-migration DB backup** — `memory/schema.ensure()` snapshots
  the database to `memory/backups/` with sqlite3's backup API
  (consistent even with WAL frames outstanding) before running any
  migration, keeps the newest 3 copies, and never blocks the
  migration if the copy fails (logged, `backup: null`). The backups
  directory is gitignored alongside the DB itself.
- **Integrity probe** — `memory/store.integrity()` runs
  `PRAGMA integrity_check` (cheap on this KB-sized DB) on the health
  path: a corrupt file degrades the memory row with
  `integrity: <error>` instead of failing later somewhere unrelated.

### Changed
- Registry results carry `stoppable` / `restartable` alongside
  `ok` / `detail` / `ms` / `group`, merged unchanged into
  `/api/health` and the SYSTEM tab.
- Hotkeys and tray are explicitly marked boot-only
  (`restartable=False`): a second listener start would race the
  first, and tray's stop/start cycle can drop the icon thread.

## [1.12.0] — 2026-10-06

Service lifecycle + failure-path batch: one service registry now
boots every subsystem in both modes — console and desktop used to
start DIFFERENT sets (desktop was silently missing reminders, the
briefing scheduler, dreams, clipboard, time tracker, folder sentinel
and MCP). Every start is isolated, timed and reported, health gained
model + dependency rows, and a new failure-path suite proves the
system degrades cleanly when its parts break. 487 tests, 143 API
endpoints, 142 shipped skills.

### Added
- **`system/services.py` — shared service registry** — declarative
  ServiceSpecs grouped `core` / `background` / `voice` / `browser` /
  `mcp` / `desktop` with optional pref gates; `boot(mode)` starts the
  set for that mode and never raises. Each service runs isolated (one
  crash degrades exactly that row), threaded services report
  asynchronously, and every result carries a start time in ms. Both
  `run.py` and the desktop launcher boot through it and log/print a
  one-line summary before serving.
- **Desktop boot parity (bug fix)** — desktop mode now starts the
  background set it never had: reminder loop, daily briefing
  scheduler, dream scheduler, clipboard watcher, time tracker,
  folder sentinel and MCP autostart. App-learner warm and overlay
  pre-warm were folded into the same registry, so console and desktop
  can no longer drift apart (regression-tested).
- **Dependency probe** — health reports missing optional packages
  (playwright, sounddevice, pystray, pynput, pygame, apscheduler,
  psutil) as an amber `deps` row instead of failing silently at
  first use.
- **Model/provider row** — health shows the active model, base-URL
  host, temperature and extra-provider count.
- **Failure-path test suite** — `tests/test_failure_paths.py` proves:
  provider down → structured 502 JSON (never an HTML page), missing
  key → skills-only hint, corrupt memory DB → JSON 500 with detail,
  browser engine missing / voice unavailable / scheduler failing /
  MCP partially failed → that one row degrades while boot continues,
  and slow requests get logged. `tests/test_services.py` covers the
  registry itself (pref gates, isolation, timing, mode filtering).
- **Slow-request logging** — requests slower than 2s log
  `Slow request: GET /path took 2.31s` (threshold:
  `server.SLOW_REQUEST_S`).

### Changed
- Health `services` items now include `group` and per-service `ms`,
  shown in the SYSTEM tab as `background · detail · 12ms`; registry
  results and legacy `health.mark()` entries merge into one view.
- `health.reset()` also clears registry results so test runs stay
  isolated from each other.
- The boot config audit prints a one-line count after the individual
  warnings ("Config audit: N warning(s) — full list in Settings >
  SYSTEM").

### Fixed
- Desktop mode never started reminders, the briefing scheduler,
  dream scheduler, clipboard watcher, time tracker, folder sentinel
  or MCP autostart — those lived only in `run.py`, so features added
  to console boot silently didn't exist in daily desktop use.
- `mcp/runtime.py:_sdk()` briefly REMOVED the project root from the
  process-global `sys.path` while importing the MCP SDK; now that
  desktop boot starts MCP alongside Flask, that window raced the
  server's first import (`ModuleNotFoundError: No module named
  'routes'` — found live on the very first v1.12.0 desktop boot).
  The SDK's site dir is now moved to the FRONT of `sys.path` with no
  entries ever removed, and two regression tests pin the invariant.

## [1.11.0] — 2026-10-06

Operational maturity batch: the system can now tell you how it is
doing. One health snapshot covers every subsystem, the config audits
itself for drift, the memory DB knows its own schema version, and
secrets are scrubbed from every log line. 454 tests, 143 API
endpoints, 142 shipped skills.

### Added
- **Health dashboard** — `GET /api/health` returns one snapshot of
  config, API key, memory (+schema), voice, guard, updater, MCP,
  pending skill verdicts and every boot service; boot paths mark each
  service as it starts (`run.py` and desktop mode both), so a failed
  subsystem shows up as *degraded* with the reason instead of
  disappearing silently. Settings → **SYSTEM** tab renders it with a
  REFRESH button and an amber config-warnings block.
- **Config audit** — `config.audit_settings()` statically checks for
  drift (model/base-URL mismatch, out-of-range port/temperature/
  max_tokens, empty voice, unknown browser engine, missing Obsidian
  vault, debug on a non-loopback host, bad log level). Logged once at
  boot, served live via `/api/health` — warnings only, never blocks.
- **Memory schema versioning** — `memory/schema.py` stamps
  `PRAGMA user_version` on `jarvis_memory.db`, runs forward-only
  migrations when the schema bumps, and refuses to touch a DB written
  by a NEWER JARVIS (reported instead, so a downgrade never corrupts).
- **Secret redaction in logs** — every log handler now runs a
  `RedactFilter`: OpenAI/Tavily/GitHub-style keys, `Bearer` tokens,
  `*_API_KEY=…`/`TOKEN=…` assignments and `?key=…` query params are
  masked before they can reach `logs/jarvis.log` or the console.

### Changed
- `updater.check()` remembers its last result for `last_check()`, so
  health can report update state without another network fetch.

## [1.10.0] — 2026-10-06

The agentic suites batch: four self-contained capability packs —
System Guard, Workspace Orchestrator, n8n Bridge, Deep Web
Intelligence — built on the existing skill router, search tiers and
alert pipeline. 408 tests, 142 API endpoints, 142 shipped skills.

### Added
- **System Guard** — a RAM watchdog samples once a minute and fires
  ONE desktop alert (naming the hungriest process) when usage
  crosses the threshold, hysteresis so it never spams
  (`system/guard.py`, on in both `run.py` and desktop mode;
  `guard_enabled` / `guard_ram_threshold` prefs + Settings →
  GENERAL toggle). Skills: *"ram guard status"*, *"set ram guard to
  85"*; *"mic test"* reads 0.4s of the default input device and
  reports peak level so a dead mic is caught before dictation.
- **Workspace Orchestrator** — *"scaffold a flask project called
  taskboard"* lays down README/gitignore/entrypoint/tests/env
  template for python, flask, fastapi, node, react, web or plain
  and runs `git init`; *"append X to file Y"* / *"insert X after
  anchor in file Z"* edit existing files with a `.bak` snapshot
  every time, confined to the Code-Mode allow-list plus
  `Documents\JARVIS Projects`. Also exposed as `POST
  /api/interleave` for scripts.
- **n8n Bridge** — `POST /api/webhook/in` receives automation
  payloads: stored ring buffer (`GET /api/webhook/recent`), optional
  speak (toast + HUD + voice) and optional `run` that dispatches the
  payload's text through the real skill router — so an n8n flow can
  trigger system actions. Disabled by default; token-gated via
  `X-Jarvis-Token` or localhost-only. Outbound: *"send to n8n: …"*,
  *"set n8n url …"*, *"test n8n"* (`webhook_enabled`,
  `webhook_token`, `webhook_out_url` prefs).
- **Deep Web Intelligence** — *"docs for flask"* pulls real
  documentation (PyPI metadata + docs link, or GitHub README for
  `owner/repo` slugs) and briefs it with the LLM (extractive
  fallback when keyless); *"explore <topic>"* fans 4 query variants
  across the search tiers CONCURRENTLY, dedupes by URL and
  synthesizes one answer with sources.

## [1.9.0] — 2026-10-06

Self-update: JARVIS now watches GitHub for new versions and pulls
them itself — carefully.

### Added
- **Auto-update** — at boot JARVIS fetches `origin/main`, compares
  it to `config.VERSION`, and (when the toggle is on) fast-forwards
  the checkout to the newest release, then toasts *updated — restart
  to finish*. The pull **never runs over local edits or unpushed
  commits** (tracked files only — your untracked `.env` and personal
  files never block it), and every refusal says exactly why
  (`system/updater.py`, wired into both `run.py` and desktop mode).
- **Update UI + API** — Settings → ABOUT shows the live version
  status with CHECK / UPDATE buttons (auto-checks when the tab
  opens), Settings → GENERAL gains an Auto-update toggle (default
  on), and `GET /api/update/check` + `POST /api/update/apply` expose
  the same to scripts.

### Changed
- README version badge finally tracks `config.VERSION` (was stuck
  at v1.7.0) and all counts refreshed (352 tests, 139 endpoints,
  Lite at 28 skills).

## [1.8.0] — 2026-10-06

Library v2 (uninstall + import + live status), real token streaming
into the HUD, and background-job alerts that reach you on the desktop
and on the deck.

### Added
- **Library v2** — every installed pack and MCP server now has a
  REMOVE button (unregisters the skills and deletes the pack file;
  stops the server and drops its config), installed servers show
  running/stopped state with inline START/STOP, and you can
  **import your own packs as JSON** (`POST /api/library/import`):
  id + code, passed through the community-plugin validator before it
  enters the Library, catalogued in gitignored
  `library/user_catalog.json`. **5 new packs** — Caesar cipher,
  anagram check, weekday finder, prime check, leetspeak (18 total).
- **HUD live streaming** — replies flow token-by-token into the deck
  as the model answers instead of being stitched and typed out
  afterwards; a mid-stream error turns the reply red in place and
  the fast path still applies when nothing streamed.
- **Background-job alerts** — `notify.alert()` fires a desktop toast
  AND flashes the open HUD's status dot green when timers,
  reminders, research jobs or computer tasks finish (the deck is
  never force-shown — the toast is the reach when it is closed).
- **Per-server stop** — `POST /api/mcp/stop {"name": ...}` stops one
  server while an omitted name still stops all; new
  `runtime.stop_server` / `is_running` / `running_names` power the
  Library status chips.

## [1.7.0] — 2026-10-06

Overlay rebuilt from zero as HUD 4.0, a one-click Library for skill
packs and MCP servers, plus cross-cutting polish.

### Added
- **LIBRARY tab — one-click installs**: a curated catalog
  (`library/catalog.json`) of **13 bundled skill packs** (word
  counter, percent / tip / BMI calculators, date distance, age,
  ROT13, password generator, coin flip, random picker, JSON
  formatter, Roman numerals, palindrome check) and **12 MCP
  servers** (memory, filesystem, everything, time, fetch, git,
  sqlite, github, brave-search, puppeteer, playwright, postgres).
  `GET /api/library`, `POST /api/library/skill`,
  `POST /api/library/mcp` — packs hot-load through the same
  validator as community plugins (no restart), MCP entries expand
  `{HOME}`/`{DOCUMENTS}` placeholders, auto-start when they can and
  clearly defer when an API key is required. The tab has
  client-side search and per-entry ADDED state.
- **HUD 4.0 "Glass Command Deck"** — `system/overlay.py` rebuilt
  from zero: 20px rounded transparent corners with a double bezel
  and top accent line, a wider 760px deck whose compact input mode
  expands into a scrollable reply well, live JARVIS header (title,
  mood · model, version, status dot that pulses amber while
  thinking and turns red on errors), hover-lit chips, a key-hint
  footer with COPY, typewriter replies that cancel when superseded,
  100-entry history, dictation auto-send and header drag. Esc / ✕ /
  Alt+Space still hide outright while focus-away only dismisses an
  idle, empty deck.
- **`secrets` allowed in generated skills** — the validator accepts
  the crypto-RNG module so password packs can be truly random.

### Fixed
- **MCP server starts died under `mcp` SDK 2.x** — the client read
  `Tool.inputSchema`, which 2.x renamed to `input_schema`, so every
  start failed during tool listing; it now reads either shape.
- **Library `time` entry pointed at a nonexistent npm package** —
  repointed to the official PyPI server (`uvx mcp-server-time`); all
  12 catalog entries were verified live against npm/PyPI.
- **MCP `add_server` accepts list args** — arguments were split on
  whitespace, breaking any path containing spaces; one-click
  library entries now pass real argument lists.
- Plugin template and generator prompt now document the complete
  allowed-import list (including `time`, `random`, `secrets`).

### Changed
- 18 new tests (302 total) covering catalog shape, pack validation,
  install/add flows, placeholder expansion and the library API.

## [1.6.0] — 2026-10-05

Backup story completed, HUD refresh made dynamic, dev mode visible,
agent loop hardened, and the app catalog widened.

### Added
- **Backup restore** — the missing half of the backup story:
  `restore_backup` engine (`POST /api/backup/restore`), voice skill
  ("restore backup" → preview, "restore confirm" → apply), and a
  BACKUPS section in the Marketplace (BACK UP + RESTORE per zip).
  Restore is a two-step confirm; it snapshots current state first,
  refuses zip-slip and invalid names, closes the live SQLite handle,
  swaps files atomically, and reopens lazily. Live roundtrip proven.
- **Dynamic HUD refresh**: header now refreshes ~10s (was ~30s) and
  immediately after every command, so mood/model changes show at once.
- **Dev-mode badge**: `/api/info` exposes `dev`; the dashboard brand
  reads `v1.6.0 · DEV` under `FLASK_DEBUG=1`, and `run.py` prints
  the mode at boot.
- **~40 new native app aliases** (Office, 7-Zip, WinRAR, Blender,
  GIMP, JetBrains, GitHub Desktop, Signal, regedit, mstsc, charmap,
  magnifier, resmon…) plus 5 more instant-launch safe tools.

### Fixed
- **Aliases no longer dead-end**: `resolve_app` used to trust an
  alias unconditionally, so uninstalling the app broke "open X"
  even when the Start Menu had it. Aliases now verify (URI / PATH /
  App Paths) and fall through to Start Menu / fuzzy search.
- **Agent loop**: each sub-task retries once on transient failure
  (or an empty answer), merge is told how many sub-tasks failed so
  it answers with what survived, and `run()` never raises.

### Changed
- 19 new tests (284 total) covering restore roundtrip, zip-slip,
  alias fall-through, retry, dev flag, refresh cadence.

## [1.5.1] — 2026-10-05

Full error-and-logic sweep: a systematic audit of every subsystem
for crashes, silent failures, unbounded growth and unguarded input.

### Fixed
- **MCP tool calls timing out**: the client runtime used
  `run_coroutine_threadsafe` only when the server's event loop was
  NOT running (inverted check), so idle loops went down a fallback
  path that never worked. Idle loops are now driven directly with a
  timeout, running loops use `run_coroutine_threadsafe` — proven by
  a test that fails on the old code (60s timeout) and passes now.
- **Directory deletes lost data**: `fs_delete` and `code delete`
  only backed up files, so deleting a folder rmtree'd it with no
  recovery. Both now copy the whole tree first (50MB cap) and
  REFUSE the delete if the backup fails or the tree is too large.
- **Garbage numerics crashed endpoints**: unguarded `int()` on
  `minutes`/`hours`/personality sliders turned `"lots"` into a 500.
  New `_to_int` helper parses defensively and clamps to safe ranges.
- **Unbounded growth**: `jarvis.log` now rotates at 5MB × 3
  backups; research jobs pruned to 20 finished; overlay command
  history capped at 100; dashboard log honors the `log_max` pref;
  `tidy clean` LRU-trims the TTS voice cache (was 561 files / 20MB).
- **Cosmetic**: inline `__import__('os')` in the MCP stdio banner.

### Added
- 19 new tests (265 total): MCP loop-state dispatch, directory
  backup/refusal paths, input-clamp endpoints, log rotation, voice
  cache LRU, research job pruning.

## [1.5.0] — 2026-10-05

Autonomy + storefront batch: the box keeps working when models
misbehave, and everything installable lives in one Marketplace tab.

### Added
- **Admin terminal** (`code run-admin` / `run X as admin`):
  Code-Mode gate + forbidden list + structural checks, elevation
  ALWAYS asks (auto mode ignored by design), Windows UAC is the
  final guard, everything audited. Launcher yields `as admin`
  inputs to it instead of mis-opening apps.
- **Marketplace tab** (Settings → MARKET, `GET /api/market`): one
  catalog for everything installable — 133 skills with ON/OFF
  toggles, pending drafts with approve/reject, community plugins
  (file-upload install + reload), 8 MCP presets with one-click
  install, MCP servers with start/stop, pinned sites with remove.
  Every action reuses the existing validated endpoints; verified
  live with zero console errors.

### Fixed
- **Default-mood chat 400s**: the `fast` preset passed a stray
  string as `temperature`, so every default chat was rejected by
  the provider. Removed it (0.1/60 back in their fields) plus a
  regression test pinning numeric provider params on all presets.
- **Temperature-sensitive models**: new `create_with_temp_fallback`
  helper retries once without `temperature` on 400/invalid-request
  rejections; wired into chat streaming, agents, dream summary,
  reality check, vision and research synthesis. Other errors still
  fail loudly.

## [1.4.0] — 2026-10-04

Autonomy + resilience batch: research agent, HUD rebuild, loops
that survive dead models, native apps, backups.

### Added
- **Deep Research Agent** (`system/research_agent.py`): multi-step
  technical research — `search_all` finds candidates, top URLs are
  fetched (same-host one level, capped), BeautifulSoup strips
  layout noise and keeps code blocks, then LLM synthesis (or an
  extractive digest when keyless). Reports land timestamped in
  `docs/research/*.md` (gitignored vault) with TL;DR, key points,
  code fences and links; a one-line summary is remembered for later
  recall. Served as async `POST /api/research` + poll
  `GET /api/research/<job>`, and as the `deep_research` skill
  (`research <topic>` returns the report path). Verified live
  end-to-end (3 sources → report → recall).

- **DEV terminal upgrades**: output appends per run (no more
  overwrite), elapsed time on every command, Up/Down history,
  one-click CLEAR.
- **Logon task with working directory**: the scheduled task is now
  created from XML (`InteractiveToken`, 15s delay) with
  `WorkingDirectory` set to the project root — the old form started
  in System32 so `.env` never loaded. Legacy command kept as
  fallback. Still needs one elevated run to apply.
- **Overlay HUD 3.0 — command-deck rebuild**: the fixed panel is
  now a floating command bar (emblem + entry + mic/send + status
  dot) that expands into reply + chips + footer on submit.
  DPI-aware native rendering (the actual blur cure on scaled
  displays), bigger readable type, data-driven chips, live header
  refresh while visible, idle-only click-away still intact.

- **Agent loop that survives dead models**: split/merge/vision/
  dream/reality-check all use the configured default model instead
  of hardcoded IDs, plan/merge calls have timeouts, and expired /
  retired / sunset offers now trigger the fallback chain instead
  of failing chat (the exact Qwen-expiry 404 seen live is covered
  by test).
- **More native apps**: Zoom, Notion, Slack, Obsidian, Notepad++,
  Everything and Snipping Tool resolve instantly; Obsidian opens
  straight into your vault via deep link when one is configured.
- **One-click backup** (`backup` / `POST /api/backup`): memory DB
  + `.env` zipped to `logs/backups` (last 5 kept), list via
  `GET /api/backups`. Verified live (209 KB).

## [1.3.0] — 2026-10-04

Add-anything + fast-web batch: one verb installs everything, search
grows a keyed AI tier with a keyless reader fallback, sessions go
stable.

### Added
- **Universal add** (`add ...` / `POST /api/add`): sites
  (`remember <url> as <name>`, pinned to `logs/custom_sites.json`,
  `open <name>` resolves them, `forget site <name>` removes),
  MCP presets (`install mcp fetch`) and servers, apps
  (learn-without-launch), forced skill drafts — one router over the
  existing validated backends, unknown shapes fall through.
- **Tavily AI search tier** (fast depth, `TAVILY_API_KEY` optional):
  verified against the live API docs; silent skip when keyless.
- **Jina reader fallback**: pages raw HTML can't see resolve to
  readable markdown (verified live, no key).
- **Stable session secret**: first boot generates `FLASK_SECRET_KEY`
  into `.env` (never logged, never committed) and reuses it —
  sessions no longer reset on every restart. Falls back to
  ephemeral only if `.env` is unwritable.
- `mcp_servers.json` is now gitignored (it can hold server env
  secrets) — found by audit before it ever landed with any.

## [1.2.0] — 2026-10-04

Autonomy + self-care batch: the assistant opens, closes, cleans
and tours on its own; skills can't break it; agents get a memory.

### Added
- **Self-cleaning tidy**: `tidy` reports stale temp files, `tidy
  confirm` removes them (in-use skipped, MB reclaimed reported);
  Dream runs tidy nightly while idle (`dream_tidy_temp` pref).
- **Self-removing guided tour**: brand-new installs get a 4-step
  spotlight tour (command bar → log → settings → HUD) that deletes
  its own DOM on finish/skip and records `onboarded`; the
  GETTING STARTED card offers re-tours.
- **Windows theme control** (`win_theme` skill): dark/light mode
  and transparency effects via HKCU + instant broadcast, verified
  against the live registry both directions.
- **Faster memory**: `count_facts()` replaces full-table pulls,
  `idx_facts_status_id` covers the hot query (measured ms-range at
  50k rows, so no migration was justified — numbers first).
- **Voice pre-warmed**: TTS engine primes in a background thread
  at boot (console + desktop paths); first reply skips the cold
  model/network hit.
- **Skill-maker hijack guards**: catch-all, empty-matching, broad
  (2+ everyday utterances) and clone-of-another-skill patterns are
  rejected at validation; same-name refreshes and trusted system
  templates still pass.
- **Agent continuity files**: `.agent-state.md` (gitignored live
  session memory, updated every unit) and `AGENTS.md` (the full
  developer loop for any AI continuing this repo, linked from
  README).

## [1.1.0] — 2026-10-04

Big update: keyless-first onboarding, app open/close autonomy,
unbreakable skill loading, and a rewritten README.

### Added
- **Unbreakable skill loading**: core skill modules import
  isolated — one broken file logs a warning and boot continues
  with the rest (proven live with a syntax-broken probe module);
  broken regex patterns are skipped per-skill instead of failing
  the request. Community plugins already had this; now everything
  does.
- **Installer health report**: `setup.ps1` runs the 11-point
  `check.py` at the end and, on a fresh keyless install, points at
  Settings → GENERAL instead of failing the install.
- **First-run onboarding card**: fresh installs (no key, or zero
  memory facts) get a GETTING STARTED card atop the log — add key,
  try a local skill, open an app — each one click, dismiss persists
  in the new durable `onboarded` pref.
- **Overlay HUD usefulness pass**: `＋ OPEN` / `✕ CLOSE` chips
  prefill `open `/`close ` (one tap + app name runs it), a `⧉ COPY`
  button copies the last answer, the header shows a `NO KEY`
  suffix in skills-only mode, click-away only dismisses an idle
  empty HUD (never mid-answer or mid-typing — Esc/✕/Alt+Space
  still hide outright), and the HUD now resolves the server URL
  without requiring an API key.
- **Auto mode for apps**: the durable `auto_approve_skills` pref
  ("enable auto approve skills") is now a standing yes for app
  open/close gates — open and close run with zero prompts while
  system-critical and self-process refusals still apply. Also fixes
  repeat-`open` of learned non-safe apps, which previously dead-ended
  at "OK, not opening it." (generated skills had no asker); they now
  share one `ask_user` helper, paths are canonicalized on learn, and
  `POST /api/apps/close` honors auto mode too.
- **Close any app by voice** (`close`/`kill <app>`): companion to
  the universal opener. Resolves through the learner store, curated
  aliases and running processes; refuses Windows-critical processes
  and JARVIS's own interpreters; asks before closing anything that
  wasn't explicitly learned or aliased; closes gracefully first
  (apps may prompt to save), forces only leftovers, verifies gone,
  and audits like launches. Served also as `POST /api/apps/close`
  (`{query, confirm}`). Tab/window phrases stay with the
  browser/desktop hotkey skills (pattern-level guard plus dispatch
  order).
- **In-app API key setup** (Settings → GENERAL): paste
  `DEEPSEEK_API_KEY`, SAVE+TEST verifies it live against the
  provider (model count shown) and persists it to `.env` (with a
  `.env.bak` backup, now gitignored) preserving every other line;
  chat works immediately, the banner clears, and only voice features
  still ask for a restart. `GET /api/settings/key` reports a masked
  key (`thk•••d_hv` style — the secret is never sent to the page),
  and `config` gains `masked_key()`, `validate_key_format()` and
  `write_env_key()`.
- **Skills-only mode**: JARVIS now boots without `DEEPSEEK_API_KEY`.
  Local skills (time, math, notes, timers, opening apps, 100+ more)
  answer normally; only LLM chat degrades, returning a setup hint
  (`no_key` flag) instead of refusing to start. The dashboard shows
  an amber "Skills-only mode" banner (dismissible, links to
  Settings), `/api/info` reports `key` / `no_key_mode`, and
  `config` gains `Settings.load(require_key=False)`, `has_key`,
  `try_settings()` and `key_status()`. A dead speaker can no longer
  turn a good text reply into a failed request (chat TTS is
  best-effort).
- Known limitation: mic/speaker features stay unavailable until a
  key is set (`voice/output.py` reads settings at import and is
  intentionally untouched) — voice endpoints fail with a clear
  error while text chat and skills are unaffected.

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
- **Autonomous app learner** (`system/app_learner.py`): "open <unknown
  app>" deep-scans Program Files / LocalAppData / Start Menu / %PATH%
  (parallel, 1h cache, warmed at boot), launches the hit behind the
  usual confirm gate, then writes a permanent `@register` skill at the
  front of the dispatch order — next call is instant. Manage via
  `GET /api/apps/learned`, `POST /api/apps/learn` / `/api/apps/forget`.
- App finder, site finder, MCP presets/import, community plugin
  installer, DEV drawer (files / term / call / logs).
- **Persistent remember**: the `remember` skill writes facts
  (text + timestamp + source) into the core SQLite memory store —
  recalled via `memory.recall()` and injected into the system prompt
  (`facts_block()`); JSON sidecar fallback so a broken DB never loses a
  note.
- **Durable auto-approve gate** (`auto_approve_skills` preference):
  "enable/disable auto approve skills" or `POST
  /api/auto_skills/auto_approve` dynamically switches new-skill
  registration between explicit human approval and instant (only for
  code that passed validation + isolated test); app-learner skills
  stage through the same approval queue when the gate is off, and
  `forget()` / direct writes clean stale queue entries.
- Health surface: `GET /api/info` reports `facts` + `auto_approve`,
  `/api/auto_skills/pending` reports the gate state, `check.py` runs
  11 preflight checks (memory store + approval gate added).
- **One-line installer** (`setup.ps1`): a single copy/paste command
  (PowerShell or cmd) clones the repo to `%USERPROFILE%\jarvis`,
  builds `.venv`, installs every requirement group + Playwright
  Chromium and seeds `.env` from the template; run from inside an
  existing checkout it reuses the current `.venv` / `.env` untouched.
- GitHub packaging: CI, issue templates, PR template, MIT license,
  CONTRIBUTING, ARCHITECTURE.

### Changed
- **Full UI refresh — dashboard**: premium glass rebuild (gradient
  hairline panels, blurred topbar strip, pill dock), accent system now
  derived from `--theme-hue` so every glow follows the active mood,
  state-driven colors for the status pill / tagline / input ring
  (boot · idle · listening · thinking · speaking · tool · error),
  entrance choreography, hover micro-interactions, accent scrollbars,
  text selection and `prefers-reduced-motion` support.
- **Full UI refresh — overlay HUD**: bezel + accent edge with glowing
  hex emblem and halo status dot, letterspaced header with mood/model
  pill, readable Segoe UI reply well with accent bar, hover-reactive
  chips and buttons, focus-lit input border, slide+fade entrance and a
  proper fade-out dismissal.
- Layout pass: scroll-safe sidebar, richer log-entry styling (user
  messages get an accent stripe), sharper typography throughout.

### Fixed
- Fresh installs (`install.bat` / `pip install -r requirements.txt`)
  crashed on a dependency deadlock: `open-interpreter==0.4.3` pins
  `tiktoken<0.8` while every modern `litellm<2` needs `>=0.8`, sending
  pip through an unsatisfiable backtrack into a source-only build that
  needs Rust. Integrations now declare open-interpreter's real runtime
  dependencies with bounds that resolve (and match the shipped
  environment), the package itself installs with `--no-deps`, and a
  `setuptools<82` pin keeps the `pkg_resources` module open-interpreter
  still imports (removed in setuptools 82).
- Overlay "(no reply)": SSE `error` payloads now surfaced; bytes
  stream lines decoded; `/api` prefix restored on header fetch.
- Overlay queue pump could die silently after one failed action (HUD
  stopped responding while looking alive); actions now isolate errors,
  Tk callback exceptions are logged instead of lost under pythonw.
- App-learner fuzzy matching tightened: sub-4-char keys can no longer
  hijack long queries ("open totally-unknown-app" no longer matches).
- Skill approval pipeline: dead duplicate `test_in_isolation`
  definition removed; re-approving a changed candidate never
  double-registers, and approval after `forget()` re-registers even
  when Python has the module cached.
- The `auto_approve_skills` voice command now reports the persisted
  state instead of flipping an in-memory flag that died on restart.
- Duplicate `btn-dev` id in the dock: the visible DEV button had no
  listener (the id resolved to a hidden copy), so the drawer would not
  open — one button now works in both UI modes.

### Community
- README live overlay screenshot (`docs/overlay.png`), HUD demo callout
  with GIF placeholder, `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1),
  `SECURITY.md` (private reporting, scope, user hardening notes).
- Rogue venv launcher binaries replaced (single-process boots).
- MCP SDK shadowed by local `mcp/` package (`_sdk()` workaround).

### Security
- `.env` and runtime data gitignored; no keys in the repository;
  port sentinel refuses self/system PIDs; terminal command guards.
