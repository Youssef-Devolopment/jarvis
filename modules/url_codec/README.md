# URL Codec module

Percent-encoding and decoding for query strings, redirects and API
parameters.

## What it does

| Say | Get |
| --- | --- |
| `url encode hello world` | `Encoded: hello%20world` |
| `url encode /search?q=café` | `Encoded: %2Fsearch%3Fq%3Dcaf%C3%A9` |
| `url decode hello%20world` | `Decoded: hello world` |

- Encoding escapes **everything** that is not strictly safe (`safe=""`),
  which is what query-string values need.
- Decoding handles `%xx` sequences and `+` spaces.
- Works on any text you paste — nothing is fetched.

## Permissions

`none` — pure string work. Nothing is read, written, or sent anywhere.

## Files

- `module.json` — the manifest (metadata, capabilities, permissions)
- `skill.py` — the skill entry (validated with the same AST rules as
  community plugins before it ever imports)
