# Number Base Converter module

Decimal ⇄ binary ⇄ octal ⇄ hex, the way developers actually type them.

## What it does

| Say | Get |
| --- | --- |
| `convert 255 to binary` | `255 is 0b11111111.` |
| `what is 0xff in decimal` | `0xff is 255.` |
| `convert 8 to oct` | `8 is 0o10.` |
| `what is 0b1010 in hex` | `0b1010 is 0xa.` |

- Accepts plain decimals and `0x` / `0b` / `0o` literals.
- Negative numbers keep their sign (`convert -1 to hex` → `-0x1`).
- Aliases: `bin`/`binary`, `oct`/`octal`, `hex`/`hexadecimal`,
  `dec`/`decimal`.

## Permissions

`none` — pure math. Nothing is read, written, or sent anywhere.

## Files

- `module.json` — the manifest (metadata, capabilities, permissions)
- `skill.py` — the skill entry (validated with the same AST rules as
  community plugins before it ever imports)
