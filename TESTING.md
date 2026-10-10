# Testing JARVIS

How this repo is verified: automated suites, clean-environment
reproduction, health checks, CI, and the manual smoke tests that only
a human on Windows can do. Follow this and "works on my machine"
stays a scare story instead of a bug report.

**Ground truth:** 47 test files · **578 tests** · 144 API endpoints ·
142 shipped skills · `check.py` 11 preflight checks (exit 0 ready /
1 fix core / 2 skills-only).

---

## 1. Quick start — dependencies

The normal install (`setup.ps1`, see README) builds `.venv` and
installs every requirement group. If you are setting up by hand:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements-core.txt
.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
.venv\Scripts\python.exe -m pip install -r requirements-voice.txt     # mic + TTS
.venv\Scripts\python.exe -m pip install -r requirements-browser.txt   # + playwright install chromium
.venv\Scripts\python.exe -m pip install -r requirements-integrations.txt
```

- The **test suite needs only `requirements-core.txt` +
  `requirements-desktop.txt`** — exactly what CI installs. Voice,
  browser, vision and integration extras are exercised by probes and
  smoke tests, not required for `unittest` to pass.
- `python-dotenv` comes with core; without it `import voice` raises
  `ConfigError` — that is why several tests are written to tolerate a
  missing `.env` (see §9).

---

## 2. Running the suite

```powershell
cd "C:\path\to\jarvis"
$env:PYTHONIOENCODING="utf-8"
& ".\.venv\Scripts\python.exe" -m unittest discover -s tests
```

Expected tail:

```
----------------------------------------------------------------------
Ran 578 tests in ~30s
OK
```

`OK` is the pass line; `FAILED` with a list of errors is not. In
PowerShell also check `$LASTEXITCODE` (0 = pass) — unittest writes
its verdict to stderr and a truncated pipe can hide it.

**One file / one test:**

```powershell
& ".\.venv\Scripts\python.exe" -m unittest tests.test_service_control -v
& ".\.venv\Scripts\python.exe" -m unittest tests.test_health.HealthLogSummaryTests -v
```

**PowerShell 5.1 quirks that bite this repo:**

- No `&&` — use `;` between commands.
- No `??` or `? :` — not valid in scripts run under 5.1.
- `python -c "…embedded quotes…"` is unreliable — write a temp script
  file instead.
- Always set `PYTHONIOENCODING=utf-8` before running suites; several
  skills and loggers emit non-ASCII output that otherwise crashes the
  runner on Windows.

---

## 3. What each test group covers

46 files under `tests/`, grouped by the seam they protect.

**Core engine & routing**

| File | Covers |
|---|---|
| `test_dispatch.py` | Skill dispatch routing — no launches, no tabs, no network |
| `test_moods.py` | Mood state + model routing between personalities |
| `test_agents.py` | Agent loop: default-model routing (no hardcoded IDs), split flows |
| `test_memory.py` | Facts: dedup, supersede, ranked recall (scratch DB per test) |
| `test_memory_schema.py` | `user_version`, migrations, backup-before-migrate, `integrity_check` |
| `test_merge.py` | Community-skill merges register exactly once |
| `test_onboarding.py` | First-run onboarding flag lives in prefs |
| `test_polish_wiring.py` | "Remember…" skill + auto-approve gate wiring |
| `test_config_audit.py` | `audit_settings()` drift warnings (never raises; hermetic env) |

**API & failure paths**

| File | Covers |
|---|---|
| `test_failure_paths.py` | How JARVIS degrades when a subsystem breaks (provider down, corrupt DB, …) |
| `test_health.py` | `/api/health` snapshot, probes, boot service marks, post-boot log line |
| `test_services.py` | One boot registry: isolated, timed, pref-gated services |
| `test_service_control.py` | `describe()` + `stop_service()`/`restart()` + `POST /api/services/<name>` |
| `test_no_key_mode.py` | Skills-only boot: local skills work, LLM paths return a setup hint |
| `test_api_guards.py` | Garbage numerics become defaults, never 500s |
| `test_overlay_sse.py` | HUD SSE stitching (deltas reassemble into whole events) |
| `test_web_tiers.py` | Tavily/Jina tiers — keyed and keyless paths |
| `test_settings_key.py` | In-app key setup: validation, masking, `.env` backup before save |
| `test_webhook_bridge.py` | n8n-style webhook bridge inbound events |
| `test_updater.py` | Version check + safe self-update (no partial writes) |

**Safety & refusal**

| File | Covers |
|---|---|
| `test_skill_safety.py` | Skill-maker output pattern safety |
| `test_skill_isolation.py` | A broken module can't kill boot (import guard) |
| `test_shell_guards.py` | Shell safety rails (pure logic — never executes) |
| `test_tiers.py` | Autonomy tiers: dry-run gating for risky actions |
| `test_app_auto.py` | `auto_approve_skills` pref semantics |
| `test_app_close.py` | Close-app skill: pattern safety, refusal guards |
| `test_win_theme.py` | Windows-theme skill pattern safety |
| `test_tidy.py` | Tidy engine: confirm-only deletion, never silent |

**Platform & system**

| File | Covers |
|---|---|
| `test_system_guard.py` | RAM watchdog hysteresis + alerts |
| `test_singleton_ports.py` | Single instance + port sentinel |
| `test_autostart_xml.py` | Scheduled-task XML: working dir, delay kept |
| `test_logging.py` | Log rotation + secret redaction |
| `test_backup.py` | Backup: zips memory DB + `.env` into tmp, prunes, lists |
| `test_launch.py` | Universal open resolver + URL rules |
| `test_first_run.py` | First-run surface: boot status block, safe-mode verdicts, toasts, port probe, `check.py` buckets/exit codes/capabilities |
| `test_app_learner.py` | App-learning engine (no real launches) |
| `test_scaffold.py` | Boilerplate scaffolder output shape |

**Skills, library & suites**

| File | Covers |
|---|---|
| `test_adder.py` | Universal add: pin/remove sites, MCP presets, app learning |
| `test_library.py` | One-click library catalog / install / API |
| `test_market.py` | Marketplace catalog + site unpin |
| `test_mcp_runtime.py` | MCP client dispatch across loop states |
| `test_mcp_server.py` | Native stdio MCP server, end-to-end JSON-RPC |
| `test_notify_alert.py` | Toast + HUD pulse for background jobs |
| `test_interleave.py` | Workspace interleaver + its API (safe targets) |
| `test_research.py` | Deep research async jobs |
| `test_docnav_explore.py` | `doc_navigator` + multi_search (Deep Web suite) |

---

## 4. Fresh-copy / clean-env validation

Bugs in this repo have repeatedly been *environment* bugs — code that
only works because your machine has a `.env`, a warm `__pycache__`, or
a running server. The CI repro is a pristine tree without `.env`:

```powershell
$src = "C:\path\to\jarvis"
$dst = "$env:TEMP\jarvis_fresh"
if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
robocopy $src $dst /E /XD .git logs .venv /XF .env .agent-state.md | Out-Null
Push-Location $dst
& "$src\.venv\Scripts\python.exe" -m unittest discover -s tests
$code = $LASTEXITCODE
Pop-Location
$code    # 0 = clean
```

What this catches that an in-tree run misses:

- imports that only succeed because `.env` was loaded
  (the `import voice` → `ConfigError` guard bug was caught exactly
  this way);
- tests accidentally depending on a previously created file
  (`logs/jarvis.lock`, `memory/*.db`, `__pycache__`);
- anything a developer "fixed" by hand in their local tree instead of
  in the repo.

Run the fresh-copy suite before every push; CI runs the same idea on
a genuinely new machine.

---

## 5. Health verification — six layers

| Layer | How | What "healthy" looks like |
|---|---|---|
| Preflight | `.venv\Scripts\python.exe check.py` | Exit 0 + `All 11 checks passed` (a fresh placeholder-key install exits 2 with a capabilities block — that is skills-only, not broken) |
| API | `GET http://127.0.0.1:5001/api/health` | `"overall": "ok"`, every `checks.*.status` ok/warn |
| UI | Settings → **SYSTEM** tab | All rows green; degraded rows name the failing service |
| UI | Page banner (under the topbar) | **Hidden** when ok; amber = config warnings; red = degraded |
| Console | `python run.py` | `Health : OK — all systems healthy` (or `still starting: X`, a WARN count, or a SAFE MODE block with the next step) |
| Log | `logs/jarvis.log` | `Health after boot: ok` (INFO) or a WARNING naming the failures |

The health snapshot covers: config drift + key status, memory (facts,
schema version, `PRAGMA integrity_check`), voice engine, RAM guard,
updater, MCP servers, every boot service with its start timing, model
availability, and dependency probes. Config warnings appear as a
counted WARN row, not a wall of text.

Slow requests (> 2s) are logged as WARNING with method/path/ms —
grep `Slow request` when something "feels laggy".

---

## 6. What "CI green" means in this repo

`.github/workflows/ci.yml` runs on every push to `master`/`main` and
on pull requests, on a **Windows** runner (`windows-latest`,
Python 3.10) — same OS family as the product:

1. install `requirements-core.txt` + `requirements-desktop.txt`
   (the same two files §1 says the suite needs);
2. **syntax-check every `.py`** outside `.venv`
   (`python -m py_compile`, all files, any failure fails the job);
3. `node --check static/js/app.js` (the UI bundle must parse);
4. `python -m unittest discover -s tests -v` — the whole suite.

"CI green" therefore means: *every file compiles, the UI script
parses, and all 578 tests pass on a machine that has never seen your
checkout*. It does **not** mean smoke tests ran — §7 stays manual.

Check the latest run:
`https://github.com/Youssef-Devolopment/jarvis/actions` (or via API:
`GET /repos/Youssef-Devolopment/jarvis/actions/runs?per_page=1`).

---

## 7. Manual smoke tests

Automated tests prove logic; these prove the machine actually works.
Start JARVIS (`desktop.bat` or `run.py`), then:

**Product surface** (the 90-second demo covers all of these — see
`DEMO.md` for the exact script and per-step fallbacks)
- Fresh console shows the four starter chips; clicking one runs it
  and the chips disappear (`/clear` brings them back).
- Topbar pill reads READY (green); with a degraded subsystem it
  reads ATTENTION/SAFE MODE with a plain-English tooltip; clicking
  it opens Settings → SYSTEM.
- SYSTEM tab: human check names, Overall row explains its verdict
  in words.
- Ask a skill command ("tell me the time") → pill cycles
  PROCESSING → READY, never sticks on SPEAKING (muted or unmuted).
- Over-long command (>4000 chars) → error entry shows the server's
  reason, not "HTTP 400".

**Voice**
- Say **"mic test"** → pre-flight answers: mic name, STT latency,
  voice engine, confidence.
- `POST /api/speak {"text":"systems online"}` → you hear Ryan.
- `GET /api/voices` → the configured engine's voices list.
- SYSTEM tab → **voice** row green (`TTS warmed`).

**Browser**
- SYSTEM tab → **browser** row green (Playwright prewarm, with `ms`).
- Ask JARVIS to open/search something → tab opens, no traceback.
- Freshness: `requirements-browser.txt` + `playwright install chromium`.

**MCP**
- `GET /api/mcp` → configured servers with status;
  `GET /api/mcp/tools` → tool inventory.
- SYSTEM tab → **mcp** row: any server that failed boots *degraded*,
  never silently. (A known-real state: some servers need `npx`/network
  and fail on misconfigured machines — the row must say so.)

**Scheduler**
- `GET /api/briefing` → scheduler composes the daily briefing.
- `GET /api/reminders` → list renders.
- SYSTEM tab → **scheduler** row shows its job loop.

**Hotkeys & tray**
- `Ctrl+Alt+J` → JARVIS window opens/closes.
- `Alt+Space` → HUD overlay toggles.
- Tray icon present with its menu (both entry points: `desktop.bat`
  and `run.py` should expose the same services — that parity is what
  `test_services.py` protects).

**UI**
- Page loads with 0 console errors.
- **SYSTEM tab** → RESTART/STOP buttons on every restartable service;
  click RESTART on a background service → busy `…` → row refreshes.
- Banner behaves: hidden when healthy; red + names the failed service
  when degraded; "Open SYSTEM" jumps to the dashboard.

---

## 8. When the system is degraded

1. **Read the banner / SYSTEM tab first** — the red banner names the
   failed checks; SYSTEM rows name the specific service and why
   (`detail`).
2. **Try the lifecycle controls** — SYSTEM tab → RESTART on the
   failed row (or `POST /api/services/<name>` with
   `{"action":"restart"}`). Refusals are structured 400s with a
   reason (e.g. boot-only services), not crashes.
3. **Check the log** — `logs/jarvis.log`: the `Health after boot:`
   line summarizes startup; `grep -i "error\|degraded\|Slow request"`
   for the timeline. Secrets are redacted by default (`logger.redact`).
4. **Reproduce clean** — run the fresh-copy suite (§4). If it passes
   fresh but fails in-tree, your environment is the bug.
5. **Config, not code** — most sustained degradation is config:
   `check.py` + the config-warning rows in `/api/health` point at
   wrong keys, bad ports, missing engine paths.
6. **File it with evidence** — CI run URL, the health JSON
   (secrets redacted), the failing test name, and whether
   fresh-copy reproduces it.

---

## 9. Test-writing conventions (hermetic by default)

New tests must pass on a machine with **no `.env`, no network, no
API keys, no running server**:

- **No real network.** Patch the client/fetcher; assert on the error
  shape you *would* return (`502`, structured JSON), not on live data.
  Tests that need a key-sentinel (e.g. Tavily) patch `os.environ` in
  `setUp`/`tearDown` or `mock.patch.dict` — see `test_config_audit`
  for the pattern.
- **No shared global state.** `health.reset()` in `setUp`/`tearDown`;
  use the scratch/`tempfile` DB helpers (`test_memory.py`); never
  mutate real prefs without restoring them.
- **Threaded services record asynchronously** — poll with a `_settle`
  helper instead of `sleep()` (see `test_services.py`).
- **One seam per file.** Tests target a module's contract
  (function/registry/route), not its internals, so refactors that
  keep the contract keep the tests green.
- **Never touch** `skills/auto_generated/*` (the maintainer's own
  skills) or `logs/auto_skills/pending.json` (verdict queue) in test
  fixtures — write to temp paths instead.
- **Failure-path tests belong with their subsystem** or in
  `test_failure_paths.py`; if a subsystem can degrade, there should
  be a test that it degrades *gracefully* (structured error + logged
  reason), not silently.

---

## 10. Definition of done (per change)

A change is done when **all** of these hold:

1. full suite: `Ran 578 tests … OK` (or the new count);
2. fresh-copy suite: OK without `.env`;
3. `check.py`: 11/11;
4. `node --check static/js/app.js`: clean (if JS changed);
5. CI green on the pushed commit;
6. if a subsystem was touched: its §7 smoke test done by hand;
7. counts in README/CHANGELOG updated if tests/routes/skills moved.
