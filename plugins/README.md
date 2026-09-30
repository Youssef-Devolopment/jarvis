# JARVIS Community Plugins

Drop a `.py` file in this folder, restart the server (or `POST
/api/plugins/reload`), and your skill is live. No core changes needed.

## Minimal plugin

```python
from skills.registry import register

@register("my_skill", [
    r"^do something cool[\?\.\!]?$",
], "What my skill does")
def skill_mine(text, match):
    return "It works."
```

Copy `_template.py` to start. See the running example in `hello.py`.

## Rules (enforced — violations are rejected with a reason)

- File directly in `plugins/`, `_`-prefixed files are skipped.
- Skill name: `[a-z][a-z0-9_]{1,30}`, 1–5 literal regex patterns.
- Allowed imports: `re json math datetime urllib.parse html time
  random` + `from skills.registry import register`.
- No files, no subprocess, no eval, no sockets. Handler returns a
  short spoken string or `None`.

## Replaceable parts

| Part | How to replace |
|---|---|
| Skills | this folder |
| LLM tools | `ai/tool_schemas.py` + `ai/tool_dispatch.py` |
| Moods/personalities | `moods/presets.py`, `moods/personality.py` |
| HTTP endpoints | add a Flask `Blueprint` in `routes/` |
| Voice output | `voice/output.py` (any TTS behind `speak_async`) |
| Speech input | `voice/input.py` (any STT behind `listen_until_silence`) |
| Models | `.env` (`DEEPSEEK_*`, providers are OpenAI-compatible) |

Details: `../ARCHITECTURE.md`. Contributions: `../CONTRIBUTING.md`.
