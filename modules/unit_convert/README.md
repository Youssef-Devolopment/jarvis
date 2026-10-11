# Unit Converter module

Length, weight and temperature conversions you can speak or type.

## What it does

| Say | Get |
| --- | --- |
| `convert 10 km to miles` | `10 km is 6.21 miles.` |
| `what is 72 f in c` | `72 degrees F is 22.22 degrees C.` |
| `convert 2.5 kg to lb` | `2.5 kg is 5.51 lb.` |
| `convert 300 k to c` | `300 degrees K is 26.85 degrees C.` |

- **Length:** km, m, cm, mm, mi, ft, yd (plus long forms like `miles`)
- **Weight:** kg, g, mg, lb, oz, ton (plus long forms like `pounds`)
- **Temperature:** C, F, K (plus long forms like `fahrenheit`)

Decimals and negatives are accepted (`convert -40 f to c`).

## Permissions

`none` — pure math. Nothing is read, written, or sent anywhere.

## Files

- `module.json` — the manifest (metadata, capabilities, permissions)
- `skill.py` — the skill entry (validated with the same AST rules as
  community plugins before it ever imports)
