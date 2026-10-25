# JARVIS Roadmap

Where the project stands and where it's going. Written at v1.19.1 —
a documented, observably healthy, architecture-driven system that
also reads like a product. Priorities in order: **trust →
operability → capability**. A feature that makes the system harder
to trust or operate waits.

---

## Completed

Foundation (v1.0 – v1.7): skills-first engine, voice pipeline, local
SQLite memory, web UI with LIFE/DEV modes, installers, docs set.

| Release | What landed |
|---|---|
| **v1.8.0** | Library v2 (18 skill packs + 12 MCP entries), MCP stop/is-running, HUD streaming, background alerts |
| **v1.9.0** | Safe self-update (version check + atomic update + ABOUT tab + `auto_update` pref) |
| **v1.10.0** | Agentic suites: System Guard, Workspace Orchestrator, n8n Bridge, Deep Web Intelligence |
| **v1.11.0** | **Operational maturity**: `GET /api/health` + SYSTEM dashboard, `audit_settings()` config drift checks, schema versioning, log redaction |
| **v1.12.0** | **Lifecycle**: one `system/services.py` registry for both entry points — independent, timed, pref-gated services; failure-path test suite; slow-request logging |
| **v1.13.0** | **Integrity**: per-service STOP/RESTART (`POST /api/services/<name>` + SYSTEM tab buttons), `PRAGMA integrity_check` in health, backup-before-migration |
| **v1.14.0** | **Reliability**: persistent warn/degraded page banner, `Health after boot:` log line, key-format audit checks, silent-fallback audit |
| **v1.14.1** | **Documentation set**: this roadmap, `DECISIONS.md` (architecture story), `TESTING.md` (verification manual) |
| **v1.15.0** | **Productization, phase 1**: `system/startup.py` boot voice — guarded status block, safe-mode verdict + toasts from the one health snapshot, fail-fast port probe (exit 3); capability-aware `check.py` (0/1/2 exit codes, per-check hints); launch-first setup summary; DB errors → actionable 503 |
| **v1.16.0** | **Productization, phase 2**: health verdict in the topbar pill (READY/ATTENTION/SAFE MODE, click → SYSTEM); one-click starter chips on a fresh console; plain-English SYSTEM tab + errors; product-first README, landing page (`docs/index.html`), verified 90-second `DEMO.md`; static cache buster; stuck-SPEAKING fix |
| **v1.16.1** | **Brand identity**: SVG logo set — gradient diamond mark with negative-space J (banner, dark/light lockups, favicons), landing-page branding, brand-asset guard tests |
| **v1.16.2** | **Public site**: landing page rebuilt (nine sections, design-token stylesheet, two-column hero with terminal + status card, responsive) and verified live at youssef-devolopment.github.io/jarvis via GitHub Pages from `/docs` |
| **v1.17.0** | **Genuinely-ready pass**: status banners pinned below the topbar (were buried behind it), Alt+Space HUD 5.0 (brand mark + green accent, input hint, pulsing "thinking" reply well, plain-English errors), first-run card reframed around skills-only mode, SYSTEM tab verdict card with status-colored rows, UI-surface guard tests |
| **v1.17.1** | Live-verification micro-fixes: banner strip at 64px (cleared the topbar hairline), starter chips no longer suppressed by an invisible onboarding card on narrow windows |
| **v1.18.0** | **Final polish pass**: SYSTEM tab status chips (tinted pills per status), warning/error log rail, health-aware center tagline owned by the state machine, plain-English health banner, SKILLS ACTIVE badge on the first-run card, HUD cyan listening state + COPY pill + middle-dot hints + lit input well |
| **v1.19.0** | **Module ecosystem**: `module.json` framework (skill + MCP kinds, declared capabilities/permissions, docs, examples), install from folder/zip with validation and zip-slip guards, active/inactive/failed states with rollback on crash, MODULES tab (state chips, permission chips, DOCS panel, CHECK dry-run), 9 real starter modules, author templates + `MODULES.md`, update-status catalog, 6 new API endpoints |
| **v1.19.1** | Live-verification micro-fix: `GET /api/modules` no longer hangs behind slow MCP server spawns (one bounded running-status snapshot), boot configures module MCP servers without spawning them (the mcp service starts them right after) |
| **v1.34.0** | **Turn routing you can see**: `GET /api/turns` + the sidebar RECENT strip (which skill or model answered, which one, how long, ok/fail). Its first live run exposed `what time is it` being treated as chit-chat, so the local `time` skill was skipped for a 35,070 ms model call — fixed |
| **v1.35.0** | **A real installer**: `installer/` builds a per-user `JARVIS-Setup-<version>.exe` (Inno Setup 6) — Start Menu entries, optional autostart, a real uninstaller, and a dependency bootstrap that builds `.venv` itself. The shipped file list is generated from `git ls-files`, so untracked files cannot be packaged, and CI installs the artifact on every tag to prove it. Also fixed the tray link that ignored `PORT` |
| **v1.35.1** | **The installer's dependency step, actually working**: Windows PowerShell 5.1 rejects `Tee-Object -LiteralPath … -Append` and mangles embedded quotes and `|` in arguments to native commands, so the shipped bootstrap died at "creating the virtual environment". Fixed, and CI now runs the bootstrap against the installed artifact on every tag |
| **v1.35.2** | **Say how it was built**: README and landing page state plainly that JARVIS was written by AI coding agents, and name the gates that make that responsible — tests, lint, CI, the installer job, the changelog's own failures. `DECISIONS.md` #17 records why the disclosure is deliberate and why it never lowers the bar |
| **v1.35.3** | **Prove the launch mode, not just the branch**: `tests/test_pythonw_smoke.py` starts the real `pythonw.exe` with `DETACHED_PROCESS` and no inherited handles, requires `_errlog()` to give a banner-writing child a live stderr, requires the `stderr=None` child to die, and completes a real MCP handshake through `stdio_client` inside that windowless process. Removing the fix fails the test; it runs as its own CI step |
| **v1.36.0** | **Find things**: the 21 flat settings tabs become a rail grouped into ASSISTANT / WORK / EXTEND / SYSTEM, with one search box that matches what a tab *controls* ("microphone", "api key", "theme") rather than what it is named. `/` focuses search, `Enter` opens the first hit, `Escape` clears, and the match count is announced to screen readers. `tests/test_settings_find.py` holds the wiring still |
| **v1.36.1** | **The installer gate stops trusting the runner image**: the v1.36.0 tag failed "Verify the dependency bootstrap" twice at ~23 s, identically, and nothing in that diff touched the path — `installer.yml` was the one place in the repo that did not pin an interpreter. It now runs `setup-python` 3.10 like `ci.yml`, and on failure prints the tail of `logs\install.log` so the next failure explains itself |

*(The table is continuous in `CHANGELOG.md`; it resumes here at the
current release so this file does not silently claim the gap.)*

Stable today: 868 tests (in-tree + fresh-copy, no `.env`), 120 API
endpoints, 142 shipped skills + 9 shipped modules, a per-user Windows
installer that installs and uninstalls cleanly, green CI on
`windows-latest` (plus an installer job on every `v*` tag that installs
the artifact and asserts it carries no secrets or local models), health
visible in six layers (preflight / API / dashboard / banner / console /
log), lifecycle controls for 15 services, structured errors on every
known failure path.

---

## Direction, v1.34 onward: finish it for strangers

Set at v1.34.0 from a survey of how the app is actually used. The
survey ruled *out* new capabilities and ruled *in* three things: it
should feel finished, anyone should be able to install it, and it
should stay easy to build on. The friction named was "feels slow or
heavy", "can't see what it's doing", and "features are hard to find".

Five batches, no new features:

0. **Routing stays skill-first, and AI stays a choice, not a
   requirement** — stated by the maintainer at v1.36.0 and already
   how the dispatch chain is built (`skills.dispatch()` before the
   LLM; the 1.34.0 chit-chat gate is what keeps it honest). Skills
   answer when a skill matches. The model is the fallback, and it
   should be able to be either a **local** model (Ollama, any
   OpenAI-compatible local base URL) or a **cloud** one, chosen in
   settings rather than baked in. What this direction asks for is
   that no batch, and no future "AI" work, quietly reverses the
   order or makes a key necessary for the core loop to function.
1. **See what it's doing** — shipped in **v1.34.0**: `/api/turns` plus
   the sidebar RECENT strip, which found a 35-second misroute on its
   first live run.
2. **Find things** — shipped in **v1.36.0**: the 21 flat settings tabs
   regrouped into ASSISTANT / WORK / EXTEND / SYSTEM with one search
   box that matches what a tab controls ("microphone", "api key",
   "theme") rather than what it is named.
3. **Install in 10 minutes** — shipped in **v1.35.0**: a per-user
   Windows installer (`installer/`) with Start Menu entries, an
   uninstaller and a dependency bootstrap, wired into CI so the
   artifact is installed and uninstalled on every tag. What is left
   here: re-time a cold install end to end on a machine that has never
   seen Python and fold the remaining steps into one page.
4. **Feels lighter** — measure boot phases and first-token latency
   *first*, then trim what the numbers actually blame.
5. **Easy to build on** — the `app.js` ES-module split (DECISIONS #13).

---

## In progress / open threads

- **MCP server configuration** — 4 of 9 configured servers
  (Fetch, Puppeteer, Brave search, …) fail on the maintainer's
  machine: `npx`/network issues, not code. The mcp row is honestly
  degraded until fixed. Roadmap: preflight checks (§30d #2) make
  this class of failure self-diagnosing.
- **Health snapshot stalls while MCP starts** — `mcp/runtime.py`
  holds `_lock` across each server's full start (a 45s join, server
  after server), so `/api/health` and the boot verdict block until
  MCP settles (~60–90s on a loaded machine). Honest but slow; a fix
  wants lock-free status reads (separate state dict) without touching
  the start path.
- **Frontend monolith (`static/js/app.js`)** — one ~127 KB IIFE; a
  real split needs an ES-module conversion (see `DECISIONS.md` #13),
  deferred until a build step or a second contributor exists. The DOM
  smoke is the only guard today, so it should be expanded before any
  conversion.
- **README / landing media refresh** — `docs/overlay.png` + GIF still
  show the older HUD; recapture on a quiet session. The landing page
  (`docs/index.html`) is designed to be complete without screenshots —
  optional stills would go in `docs/screens/` (see `DEMO.md` §capture).
  Brand assets shipped in v1.16.1; the GitHub repo avatar is a
  user-side upload (use `assets/jarvis-logo-mark.svg`).
- **Lite repo parity** — `jarvis-lite` runs (32 skills, 15 routes)
  but lags the full repo's health/lifecycle work (§30d #1).
- **Skill verdict queue** — pending verdicts in
  `logs/auto_skills/pending.json` (user-side, never auto-merged).
- **Environment chores (user-side)** — elevated logon scheduled task
  for autostart; optional `TAVILY_API_KEY`; lite provider keys.
  (GitHub Pages is live from `/docs` — done.)

---

## Next 30 days

1. **Lite health + lifecycle parity (light port)** — a trimmed
   `/api/health` + service registry for `jarvis-lite`: same banner
   contract, fewer rows. Keeps the two repos honest instead of
   drifting apart.
2. **MCP preflight** — extend `check.py` + `/api/mcp/setup` with
   per-server diagnosis: `npx` present, network reachability, config
   parse. Turns "mcp degraded" into "server X needs Y".
3. **Backup restore story** — backups now *exist*
   (`memory/backups/`, kept ×3, integrity-checked): give them a
   restore path — `check.py` integrity already guards; add a documented
   restore procedure (and a test that restores a backup into a fresh DB).
4. **Health history** — keep the last N snapshots + uptime counter
   so the dashboard can answer "when did it break?" instead of only
   "is it broken?".
5. **Auto-heal, once** — the watchdog restarts a *failed background
   service* one time with backoff and logs it; boot-only services and
   repeat failures stay manual (no infinite restart loops). This is
   the natural completion of the lifecycle work.
6. **Docs cross-linking** — link `TESTING.md`/`DECISIONS.md` from
   `CONTRIBUTING.md` and `AGENTS.md` (the product-facing docs —
   README, landing page, `DEMO.md` — shipped in v1.16.0).

**Deliberately not in 30 days:** new feature suites, provider
expansion, marketplace work — capability waits behind trust.

---

## Next 90 days

- **Network safety** — the config audit already warns that the API
  has no auth on non-loopback hosts. Replace the warning with a
  real answer: token auth middleware for LAN exposure, so "listen on
  0.0.0.0" becomes a supported mode instead of a footgun.
- **Packaging** — installer/portable-zip story that doesn't depend on
  a GitHub one-liner: versioned releases, offline voice profile
  (Piper as default), first-run that works without the network.
- **Plugin SDK stabilization** — `plugins/` is already hot-addable,
  validated and isolated; freeze the contract (template + docs +
  isolation tests as the compatibility gate) so outside contributions
  have a surface to target.
- **Health → metrics** — the snapshot is point-in-time; add
  lightweight counters (request latency buckets, service restart
  counts, memory size) behind `/api/health` or a sibling, so
  regressions are visible before anyone complains.
- **E2E smoke in CI** — grow from unit + syntax toward one headless
  boot-and-fetch cycle per run (health must return `ok` on a fresh
  machine). Exploratory; only if it stays deterministic.

---

## Long-term vision

**From great personal assistant to trusted platform.** The three
legs:

1. **Trust you can verify** — health, integrity, honest degradation
   and auditability stop being features and become the floor: any
   subsystem, any skill, any plugin reports its state the same way,
   and nothing fails silently.
2. **Extensibility with a contract** — skills, plugins and MCP give
   three escalating integration levels; a stable, documented SDK and
   a reviewable safety model (dry-run tiers, approval gates) let a
   community extend JARVIS without forking its trust story.
3. **Local-first by default** — the user's data stays on the user's
   machine (SQLite, `.env`, redacted logs), offline voice and
   local models remain first-class options, and any cloud call is
   explicit and replaceable.

Concretely: a plugin ecosystem with a versioned API, a docs site
generated from this repo's own documents, multi-provider voice/LLM
abstraction deep enough that swapping backends is config not code,
and a security posture (auth, redaction, isolation tests) that can
be pointed at rather than promised.

---

## Not now (deliberate non-goals)

Saying no is the roadmap's job:

- **Mobile apps / cross-platform clients** — the product is the
  Windows desktop experience; a thin remote UI maybe, an app no.
- **Cloud sync / multi-user / hosted tier** — contradicts
  local-first memory and the single-user trust story.
- **Provider lock-in or exclusivity** — any OpenAI-compatible base
  URL works by design; rankings of providers are not a project goal.
- **Feature-count competition** — new suites are judged on the
  trust→operability→capability ladder, not on parity with any
  competitor's changelog.
- **Silent auto-fixing** — the system may auto-heal *once*, with a
  log line; it will never mutate user config or data to make a
  warning disappear.

---

*Revisit this file every release: move shipped items to Completed,
prune anything that stopped mattering, and keep the 30-day list
shorter than the team's patience.*
