# JARVIS Roadmap

Where the project stands and where it's going. Written at v1.15.0 —
a documented, observably healthy, architecture-driven system rather
than a pile of features. Priorities in order: **trust → operability →
capability**. A feature that makes the system harder to trust or
operate waits.

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

Stable today: 572 tests (in-tree + fresh-copy, no `.env`), 144 API
endpoints, 142 shipped skills, green CI on `windows-latest`, health
visible in six layers (preflight / API / dashboard / banner / console
/ log), lifecycle controls for 14 services, structured errors on every
known failure path.

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
- **README media refresh** — `docs/overlay.png` + GIF still show the
  older HUD; recapture on a quiet session.
- **Lite repo parity** — `jarvis-lite` runs (32 skills, 15 routes)
  but lags the full repo's health/lifecycle work (§30d #1).
- **Skill verdict queue** — pending verdicts in
  `logs/auto_skills/pending.json` (user-side, never auto-merged).
- **Environment chores (user-side)** — elevated logon scheduled task
  for autostart; optional `TAVILY_API_KEY`; lite provider keys.

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
6. **Docs polish** — link `TESTING.md`/`DECISIONS.md` from
   `CONTRIBUTING.md` and `AGENTS.md`; recapture README media.

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
