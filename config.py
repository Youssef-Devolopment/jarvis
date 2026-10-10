from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
from errors import ConfigError, ValidationError
from logger import get_logger

log = get_logger(__name__)
load_dotenv()

# Single source of truth for the app version. Bump on major releases.
VERSION = "1.16.2"

# Project .env file (gitignored). API keys live here, never in prefs.
ENV_PATH = Path(__file__).resolve().parent / ".env"


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    api_key: str


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    model: str
    providers: tuple
    temperature: float
    max_tokens: int
    host: str
    port: int
    log_level: str
    debug: bool
    voice_name: str
    voice_rate: str
    voice_pitch: str
    voice_volume: str
    whisper_model: str
    whisper_device: str
    whisper_compute: str
    whisper_language: str
    silence_threshold: float
    silence_duration: float
    max_record_sec: int
    browser_headless: bool
    browser_engine: str
    vision_model: str
    brave_api_key: str
    news_api_key: str
    whatsapp_token: str
    whatsapp_phone_id: str
    todoist_api_token: str
    groq_api_key: str
    groq_stt_model: str
    groq_stt_language: str
    obsidian_vault: str

    @property
    def has_key(self) -> bool:
        return bool(self.api_key and not self.api_key.startswith("sk-paste"))

    @classmethod
    def load(cls, require_key: bool = True) -> "Settings":
        key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
        if require_key and (not key or key.startswith("sk-paste")):
            raise ConfigError("DEEPSEEK_API_KEY is missing or placeholder.",
                              detail="Edit .env and set a valid key. "
                              "Without a key JARVIS still boots in "
                              "skills-only mode (local skills work, "
                              "LLM chat answers with a setup hint).")
        try:
            port = int(os.getenv("PORT", "5000"))
            temp = float(os.getenv("DEEPSEEK_TEMPERATURE", "0.2"))
            max_t = int(os.getenv("DEEPSEEK_MAX_TOKENS", "400"))
            sil_thr = float(os.getenv("SILENCE_THRESHOLD", "0.012"))
            sil_dur = float(os.getenv("SILENCE_DURATION", "1.2"))
            max_rec = int(os.getenv("MAX_RECORD_SEC", "30"))
        except ValueError as exc:
            raise ConfigError("Numeric env var malformed.", detail=str(exc)) from exc

        extras = []
        seen = set()

        def _add(pname, pbase, pkey):
            pname = (pname or "").strip().lower()
            pbase = (pbase or "").strip().rstrip("/")
            pkey = (pkey or "").strip()
            if (pname and pbase and pkey and not pkey.startswith("sk-paste")
                    and pname not in seen):
                seen.add(pname)
                extras.append(Provider(name=pname, base_url=pbase,
                                       api_key=pkey))

        for i in ("2", "3", "4"):
            _add(os.getenv(f"PROVIDER{i}_NAME"),
                 os.getenv(f"PROVIDER{i}_BASE_URL"),
                 os.getenv(f"PROVIDER{i}_KEY"))
        # Auto-discover user-named pairs: XXX_API_KEY + XXX_BASE_URL.
        _SKIP = {"DEEPSEEK", "GROQ", "BRAVE", "NEWS", "OPENHANDS",
                 "TODOIST", "WHATSAPP", "CLAWBOT"}
        import re as _re
        for var in os.environ:
            m = _re.fullmatch(r"([A-Z0-9]+)_API_KEY", var)
            if not m or m.group(1) in _SKIP:
                continue
            prefix = m.group(1)
            _add(prefix.lower(), os.getenv(prefix + "_BASE_URL"),
                 os.getenv(var))
        return cls(
            api_key=key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            providers=tuple(extras),
            temperature=temp, max_tokens=max_t,
            host=os.getenv("HOST", "127.0.0.1"), port=port,
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            debug=os.getenv("FLASK_DEBUG", "0") == "1",
            voice_name=os.getenv("VOICE_NAME", "en-GB-RyanNeural"),
            voice_rate=os.getenv("VOICE_RATE", "-3%"),
            voice_pitch=os.getenv("VOICE_PITCH", "-2Hz"),
            voice_volume=os.getenv("VOICE_VOLUME", "+0%"),
            whisper_model=os.getenv("WHISPER_MODEL", "small"),
            whisper_device=os.getenv("WHISPER_DEVICE", "cpu"),
            whisper_compute=os.getenv("WHISPER_COMPUTE", "int8"),
            whisper_language=os.getenv("WHISPER_LANGUAGE", "en"),
            silence_threshold=sil_thr, silence_duration=sil_dur,
            max_record_sec=max_rec,
            browser_headless=os.getenv("BROWSER_HEADLESS", "0") == "1",
            browser_engine=os.getenv("BROWSER_ENGINE", "duckduckgo").lower(),
            vision_model=os.getenv("VISION_MODEL", "deepseek-v4.1-flash:free"),
            brave_api_key=os.getenv("BRAVE_API_KEY", "").strip(),
            news_api_key=os.getenv("NEWS_API_KEY", "").strip(),
            whatsapp_token=os.getenv("WHATSAPP_TOKEN", "").strip(),
            whatsapp_phone_id=os.getenv("WHATSAPP_PHONE_ID", "").strip(),
            todoist_api_token=os.getenv("TODOIST_API_TOKEN", "").strip(),
            groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
            groq_stt_model=os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo"),
            groq_stt_language=os.getenv("GROQ_STT_LANGUAGE", "en"),
            obsidian_vault=os.getenv("OBSIDIAN_VAULT", "").strip(),
        )


_settings = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.load()
    return _settings


def try_settings() -> Settings | None:
    """Lenient settings for boot paths: None instead of raising."""
    global _settings
    if _settings is None:
        try:
            _settings = Settings.load()
        except ConfigError:
            return None
    return _settings


def key_status() -> dict:
    """Machine-readable API-key state for banners and diagnostics."""
    key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    ok = bool(key and not key.startswith("sk-paste"))
    return {"ok": ok,
            "error": "" if ok else
            "DEEPSEEK_API_KEY is missing or placeholder. Edit .env and "
            "set a valid key (or add one in Settings), then restart."}


def masked_key() -> str:
    """The current key, masked for display (never returns the secret)."""
    key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if not key or key.startswith("sk-paste"):
        return ""
    if len(key) <= 7:
        return "sk-" + ("\u2022" * 4)
    return key[:3] + "\u2022\u2022\u2022" + key[-4:]


def validate_key_format(key: str) -> str:
    """Stripped key or ValidationError. Format check only (no network)."""
    key = (key or "").strip()
    if len(key) < 8 or any(c.isspace() for c in key):
        raise ValidationError(
            "That doesn't look like an API key.",
            detail="Keys are at least 8 characters with no spaces.")
    if key.startswith("sk-paste"):
        raise ValidationError(
            "That is still the template placeholder.",
            detail="Paste a real key.")
    return key


# Browser engines the search layer actually implements (see tools/browser).
KNOWN_BROWSER_ENGINES = ("duckduckgo", "ddg", "brave", "bing", "google",
                         "searxng", "searx")
_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_LOOPBACK = ("127.0.0.1", "localhost", "::1")


def audit_settings(s: Settings) -> list[str]:
    """Static config-drift checks — warnings only, never raises.

    Catches the silent mismatches a flexible env causes: wrong model for
    the base URL, out-of-range numbers, a vault/engine that no longer
    exists, debug mode on a non-loopback host. Called once at boot
    (server.create_app) and served live via /api/health.
    """
    warns: list[str] = []
    try:
        if not (1 <= int(s.port or 0) <= 65535):
            warns.append(f"PORT {s.port} is outside 1-65535.")
    except (TypeError, ValueError):
        warns.append(f"PORT {s.port!r} is not an integer.")
    try:
        if not (0.0 <= float(s.temperature) <= 2.0):
            warns.append(f"DEEPSEEK_TEMPERATURE {s.temperature} is outside 0-2.")
    except (TypeError, ValueError):
        warns.append(f"DEEPSEEK_TEMPERATURE {s.temperature!r} is not a number.")
    try:
        if not (1 <= int(s.max_tokens) <= 65536):
            warns.append(f"MAX_TOKENS {s.max_tokens} is outside 1-65536.")
    except (TypeError, ValueError):
        warns.append(f"MAX_TOKENS {s.max_tokens!r} is not an integer.")
    base = (s.base_url or "").strip().rstrip("/")
    if s.has_key and base and not base.startswith(("http://", "https://")):
        warns.append(f"DEEPSEEK_BASE_URL is not an http(s) URL: {base[:60]}")
    model = (s.model or "").lower()
    if s.has_key and base and "deepseek.com" in base:
        other = ("gpt" in model or model.startswith(("claude", "qwen", "llama",
                                                     "gemini", "mistral")))
        if other:
            warns.append(
                f"MODEL '{s.model}' looks non-DeepSeek but BASE_URL points at "
                f"{base} — check DEEPSEEK_MODEL/DEEPSEEK_BASE_URL pairing.")
    # Deliberately NOT warning about "deepseek-*" model names on a foreign
    # base URL: proxies/rebadged providers (any OpenAI-compatible URL) are
    # a documented setup, so that pairing is legitimate by design.
    if not (s.voice_name or "").strip():
        warns.append("VOICE_NAME is empty — speech output is disabled.")
    if (s.browser_engine or "").strip().lower() not in KNOWN_BROWSER_ENGINES:
        warns.append(
            f"BROWSER_ENGINE '{s.browser_engine}' is unknown "
            f"(expected one of: {', '.join(KNOWN_BROWSER_ENGINES)}).")
    if (s.obsidian_vault or "").strip():
        vault = Path(s.obsidian_vault).expanduser()
        if not vault.exists():
            warns.append(f"OBSIDIAN_VAULT is set but not found: {vault}")
    if s.log_level not in _LOG_LEVELS:
        warns.append(f"LOG_LEVEL '{s.log_level}' is invalid — using INFO.")
    # Optional key formats — only checked when the key is actually set.
    # Template leftovers ("paste your … here") are called out explicitly:
    # they pass prefix checks but can never work.
    def _looks_like_template(v: str) -> bool:
        lv = v.lower()
        return any(t in lv for t in ("paste", "your-", "your_",
                                     "example", "replace"))

    groq = (s.groq_api_key or "").strip()
    if groq and not groq.startswith("gsk_"):
        warns.append("GROQ_API_KEY does not start with 'gsk_' — it looks "
                     "wrong (Groq keys are gsk_…).")
    elif groq and _looks_like_template(groq):
        warns.append("GROQ_API_KEY still looks like a template placeholder "
                     "— replace it or leave it empty.")
    tavily = (os.getenv("TAVILY_API_KEY") or "").strip()
    if tavily and not tavily.startswith("tvly-"):
        warns.append("TAVILY_API_KEY does not start with 'tvly-' — it "
                     "looks wrong (Tavily keys are tvly-…).")
    elif tavily and _looks_like_template(tavily):
        warns.append("TAVILY_API_KEY still looks like a template "
                     "placeholder — replace it or leave it empty.")
    # External dependency hint: node-based MCP servers need npx on PATH.
    # Say so at boot instead of leaving servers silently degraded.
    try:
        import shutil as _shutil
        from mcp import manager as _mcp_manager
        npx_servers = [x for x in _mcp_manager.all_servers()
                       if x.get("enabled") and
                       str(x.get("command", "")).strip().lower() == "npx"]
        if npx_servers and not any(
                _shutil.which(c) for c in ("npx.cmd", "npx", "npx.exe")):
            warns.append(
                f"{len(npx_servers)} MCP server(s) need npx (Node.js) but "
                "it is not on PATH — install Node.js from nodejs.org or "
                "disable those servers (Library -> MCP).")
    except Exception:
        pass
    if s.debug and s.host not in _LOOPBACK:
        warns.append(
            f"FLASK_DEBUG=1 while listening on {s.host} — debug mode is "
            "reachable from the network; use 127.0.0.1.")
    return warns


def write_env_key(key: str, path: Path | None = None) -> Path:
    """Persist DEEPSEEK_API_KEY to the .env file.

    Preserves every other line/comment; replaces the existing entry or
    appends one. Backs the previous file up to .env.bak (gitignored).
    Returns the path written. Raises ValidationError on bad format.
    """
    key = validate_key_format(key)
    p = Path(path) if path else ENV_PATH
    lines: list[str] = []
    if p.exists():
        text = p.read_text(encoding="utf-8")
        lines = text.splitlines()
        bak = p.with_suffix(".bak")
        try:
            bak.write_text(text, encoding="utf-8")
        except OSError as exc:
            raise ValidationError("Could not back up .env.",
                                  detail=str(exc)[:120])
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith("DEEPSEEK_API_KEY="):
            lines[i] = f"DEEPSEEK_API_KEY={key}"
            found = True
            break
    if not found:
        lines.append(f"DEEPSEEK_API_KEY={key}")
    try:
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as exc:
        raise ValidationError("Could not write .env.", detail=str(exc)[:120])
    return p


def ensure_flask_secret(path: Path | None = None) -> str:
    """Stable Flask SECRET_KEY, persisted in .env on first boot.

    Sessions previously reset on every restart (ephemeral key). Now
    the first boot generates 32 random bytes, appends them to .env
    (never logged, never committed), and every later boot reuses
    them. Falls back to ephemeral only if .env is unwritable.
    """
    import secrets
    secret = (os.getenv("FLASK_SECRET_KEY") or "").strip()
    if secret:
        return secret
    p = Path(path) if path else ENV_PATH
    if p.exists():
        for ln in p.read_text(encoding="utf-8").splitlines():
            if ln.strip().startswith("FLASK_SECRET_KEY="):
                saved = ln.split("=", 1)[1].strip()
                if saved:
                    os.environ["FLASK_SECRET_KEY"] = saved
                    return saved
    generated = secrets.token_hex(32)
    try:
        lines: list[str] = []
        if p.exists():
            lines = p.read_text(encoding="utf-8").splitlines()
            lines = [ln for ln in lines
                     if not ln.strip().startswith("FLASK_SECRET_KEY=")]
        lines.append(f"FLASK_SECRET_KEY={generated}")
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.environ["FLASK_SECRET_KEY"] = generated
        log.info("FLASK_SECRET_KEY generated and saved to .env.")
        return generated
    except OSError as exc:
        log.warning("Could not persist Flask secret (%s) — "
                    "sessions reset on restart.", exc)
        return generated
