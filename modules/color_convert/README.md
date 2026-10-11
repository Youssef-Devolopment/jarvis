# Color Converter module

Hex ⇄ RGB ⇄ HSL conversions for designers and developers.

## What it does

| Say | Get |
| --- | --- |
| `what color is #ff8800 in rgb` | `#ff8800 is rgb(255, 136, 0).` |
| `convert #f80 to hsl` | `#f80 is hsl(31, 100%, 50%).` |

- Accepts 3-digit (`#f80`) and 6-digit (`#ff8800`) hex, with or without
  the `#`.
- RGB answers always include the hex form, so you can copy either one.
- HSL is rounded to whole degrees/percentages.

## Permissions

`none` — pure math. Nothing is read, written, or sent anywhere.

## Files

- `module.json` — the manifest (metadata, capabilities, permissions)
- `skill.py` — the skill entry (validated with the same AST rules as
  community plugins before it ever imports)
