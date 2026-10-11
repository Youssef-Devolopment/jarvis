# Secure Token Generator module

Random tokens and API keys from the operating system's cryptographic
random number generator (`secrets`), not `random`.

## What it does

| Say | Get |
| --- | --- |
| `generate a secure token` | a fresh 43-character URL-safe token |
| `make a secure api key` | the same, phrased for keys |
| `give me a secure random key` | the same |

- Uses `secrets.token_urlsafe(24)` — 192 bits of entropy, URL-safe
  alphabet, no ambiguous padding.
- Every call produces an independent token; nothing is stored or sent
  anywhere.
- Prefer this over `random`, which is predictable by design.

## Permissions

`none` — generates and prints a value. Nothing is read, written, or
sent anywhere.

## Files

- `module.json` — the manifest (metadata, capabilities, permissions)
- `skill.py` — the skill entry (validated with the same AST rules as
  community plugins before it ever imports)
