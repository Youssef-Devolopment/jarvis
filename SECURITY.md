# Security Policy

## Reporting a Vulnerability

Please **do not** report security vulnerabilities through public GitHub issues.

Instead, use one of these private channels:

* **GitHub Private Vulnerability Reporting** —
  [open a security advisory](../../security/advisories/new) (preferred)
* If neither is available, contact the maintainers privately via GitHub
  (profile → Contact) with the subject line `[SECURITY] JARVIS`

Include as much detail as you can:

* Affected version (`config.VERSION`, shown in `/api/info` and the About tab)
* Steps to reproduce or an exploit concept
* Impact (e.g. remote code execution, path traversal, secret leakage)
* Any suggested fix, if you have one

## What to expect

* **Acknowledgement** within 72 hours
* **Initial assessment** within 7 days
* A coordinated fix and credit (unless you prefer to stay anonymous)
* Public disclosure only after a fix or mitigation is available

## Scope

In scope:

* The JARVIS server (Flask routes, SSE endpoints, MCP server)
* Skill/plugin loading and execution (path injection, unsafe deserialization)
* The autonomous app learner (executable discovery / skill generation)
* Secret handling (`jarvis_config.json`, session cookies, API keys)
* The overlay, screen-context, and Obsidian bridge integrations

Out of scope:

* Denial of service against a local-only deployment
* Vulnerabilities in third-party dependencies with no JARVIS-specific impact
  (report those upstream)
* Social-engineering of the maintainer or users

## Security Notes for Users

JARVIS is a **local, single-user assistant with real system capabilities**
(it can launch applications, write notes, and read screen text by design):

* The server binds to `127.0.0.1` — do not reverse-proxy it to the public
  internet without adding authentication.
* API keys live in `jarvis_config.json` (git-ignored). Never commit it.
* Autostart is opt-in via **Login autostart** in Settings and can be removed
  with `python -m system.autostart remove`.
* Screen context is RAM-only and disabled unless you enable the pref.
* Learned skills (`skills/auto_generated/app_*.py`) only ever open local
  executables — you can revoke any of them via `POST /api/apps/forget`.
