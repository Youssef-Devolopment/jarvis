from __future__ import annotations
import json
import time
from typing import Iterator
from openai import OpenAI
from ai.tools import execute_tool
from config import get_settings
from errors import AIError
from logger import get_logger
from moods import current as current_mood
from moods.models import (get_active, set_active, theme_for, label_for,
                           build_fallback_list, is_free, speed_rank, sort_models)
from moods.router import pick_model

log = get_logger(__name__)

BASE_PROMPT = (
    "You are JARVIS, a concise, witty, unfailingly polite British voice "
    "assistant. Plain prose only — no markdown, no bullet points, no emoji — "
    "because your reply will be read aloud.\n\n"
    "CRITICAL RULES:\n"
    "- If you do not know something, say so plainly. Never invent facts.\n"
    "- Use tools to search the web when asked about live data or recent events.\n"
    "- If uncertain, say 'I am not certain'.\n"
    "- Never claim to have performed an action you did not perform.\n"
)

FALLBACK_CHAIN = [
    "qwen3.8-flash:free",
    "mimo-v2.5:free",
    "mimo-v2.6-flash:free",
    "deepseek-v4.1-flash:free",
    "deepseek-v4-flash:free",
]


def _is_model_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    keys = ["model not found", "does not exist", "invalid model",
            "no such model", "unsupported model", "not available",
            "model_not_found", "permission", "unauthorized"]
    return any(k in msg for k in keys)


def _friendly_error(exc: Exception) -> str:
    msg = str(exc)
    low = msg.lower()
    if "authentication" in low or "401" in low or "invalid_api_key" in low:
        return "API key is invalid. Check .env"
    if "rate limit" in low or "429" in low:
        return "Rate limit hit. Wait a minute or switch to Flash."
    if "insufficient" in low or "quota" in low or "balance" in low:
        return "Out of credits on this account."
    if "timeout" in low or "timed out" in low:
        return "Request timed out. Try again."
    if "connection" in low or "unreachable" in low:
        return "Cannot reach the AI backend. Check internet."
    if "model" in low and ("not found" in low or "does not exist" in low):
        return "This model is not available on your account."
    return "AI error: " + msg[:100]


class AIClient:
    def __init__(self, provider=None) -> None:
        from config import Provider
        s = get_settings()
        if provider is None:
            base_url, api_key, pname = s.base_url, s.api_key, "default"
        else:
            base_url, api_key, pname = (provider.base_url, provider.api_key,
                                        provider.name)
        self.provider_name = pname
        self.base_url = base_url
        self.default_model = s.model
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        if not get_active():
            set_active("auto")
        log.info("AIClient ready (provider=%s, default=%s, base=%s)",
                 pname, self.default_model, base_url)

    def _system_prompt(self) -> str:
        from memory import facts_block
        from memory import context as ctx_tracker
        from moods import current as current_mood
        from moods import personality
        mood = current_mood()
        pers = personality.current()
        parts = [BASE_PROMPT, mood.system_suffix, pers.system_suffix()]
        try:
            from skills import all_skills
            knacks = sorted({s.name for s in all_skills()})
            if knacks:
                parts.append("Extra voice-command skills you can suggest: "
                             + ", ".join(knacks))
        except Exception:
            pass
        facts = facts_block(limit=12)
        if facts:
            parts.append(facts)
        ctx = ctx_tracker.context_block(minutes=60)
        if ctx:
            parts.append(ctx)
        parts.append(
            "You are helping the user on their computer. Be aware of "
            "the recent activity above. Mention things briefly if they "
            "look like they need attention."
        )
        return "\n\n".join(parts)

    def _last_user_text(self, messages):
        for m in reversed(messages):
            if m.get("role") == "user":
                return m.get("content") or ""
        return ""

    def list_models(self):
        items = []
        try:
            resp = self._client.models.list()
            for m in resp.data:
                name = getattr(m, "id", None) or getattr(m, "name", "")
                if not name:
                    continue
                t = theme_for(name)
                items.append({
                    "id": name, "label": label_for(name),
                    "hue": t.hue, "accent": t.accent,
                    "fallback": False, "free": is_free(name),
                    "rank": speed_rank(name),
                    "provider": self.provider_name,
                })
        except Exception as exc:
            log.warning("Provider /models failed (%s), using fallback.", exc)
        free_items = [m for m in items if m.get("free")]
        if not free_items:
            return build_fallback_list()
        return sort_models(free_items)

    def _open_stream(self, model: str, messages, schemas, mood,
                       client=None):
        client = client or self._client
        return client.chat.completions.create(
            model=model, messages=messages,
            tools=schemas or None, stream=True,
            temperature=mood.temperature,
            max_tokens=mood.max_tokens)

    def stream(self, messages, tools=None, max_rounds=15) -> Iterator[tuple]:
        mood = current_mood()
        active = get_active() or "auto"
        user_text = self._last_user_text(messages)
        primary = pick_model(
            user_text,
            manual_override="" if active == "auto" else active,
            mood_reasoner=mood.use_reasoner,
            mood_fastest=mood.prefer_fastest,
        )

        working = list(messages)
        if working and working[0].get("role") == "system":
            working[0] = {"role": "system", "content": self._system_prompt()}
        else:
            working.insert(0, {"role": "system", "content": self._system_prompt()})

        stream = None
        used_model = primary
        used_client = self._client
        candidates = [(resolve_client(primary), primary)]
        candidates += [(self._client, m)
                       for m in FALLBACK_CHAIN if m != primary]
        for pname in extra_provider_names():
            fast = provider_fastest(pname)
            if fast:
                candidates.append((get_client(pname)._client, fast))
        seen = set()
        for client_obj, candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                stream = self._open_stream(candidate, working, tools, mood,
                                           client=client_obj)
                used_model = candidate
                used_client = client_obj
                if candidate != primary:
                    log.info("Fallback: %s -> %s", primary, candidate)
                    yield ("content", f"[fallback to {label_for(candidate)}] ")
                break
            except Exception as exc:
                if _is_model_error(exc):
                    log.warning("Model '%s' failed: %s", candidate, exc)
                    continue
                # Not a model problem — real error, stop trying
                raise AIError(_friendly_error(exc), detail=str(exc))

        if stream is None:
            raise AIError("No working model found. Try Flash.",
                          detail="All fallback models failed.")

        for _ in range(max_rounds):
            tool_acc = {}
            content = []
            finish = None
            try:
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    c = chunk.choices[0]
                    d = c.delta
                    piece = getattr(d, "content", None)
                    if piece:
                        content.append(piece)
                        yield ("content", piece)
                    # Yield reasoning tokens if present (DeepSeek reasoner)
                    reasoning = getattr(d, "reasoning_content", None)
                    if reasoning:
                        yield ("reasoning", reasoning)
                    tcs = getattr(d, "tool_calls", None)
                    if tcs:
                        for tc in tcs:
                            i = tc.index
                            if i not in tool_acc:
                                tool_acc[i] = {"id": "", "name": "", "arguments": ""}
                            if tc.id: tool_acc[i]["id"] = tc.id
                            fn = getattr(tc, "function", None)
                            if fn is not None:
                                if fn.name: tool_acc[i]["name"] += fn.name
                                if fn.arguments: tool_acc[i]["arguments"] += fn.arguments
                    if c.finish_reason:
                        finish = c.finish_reason
            except Exception as exc:
                raise AIError(_friendly_error(exc), detail=str(exc))

            if finish != "tool_calls" or not tool_acc:
                return

            working.append({
                "role": "assistant",
                "content": "".join(content) or None,
                "tool_calls": [{"id": t["id"], "type": "function",
                                "function": {"name": t["name"],
                                             "arguments": t["arguments"] or "{}"}}
                               for t in tool_acc.values()]})

            for t in tool_acc.values():
                name = t["name"]
                try:
                    args = json.loads(t["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                yield ("tool_call", {"name": name, "args": args})
                try:
                    result = execute_tool(name, args)
                except Exception as exc:
                    result = f"Tool error: {exc}"
                yield ("tool_result", {"name": name, "result": str(result)[:300]})
                working.append({"role": "tool", "tool_call_id": t["id"],
                                "content": str(result)})

            # Reopen stream for next round
            try:
                stream = self._open_stream(used_model, working, tools, mood,
                                           client=used_client)
            except Exception as exc:
                raise AIError(_friendly_error(exc), detail=str(exc))


_clients = {}
_model_ids_cache = {}
_CACHE_TTL = 300


def get_client(provider=None) -> AIClient:
    key = provider or "default"
    if key not in _clients:
        if key == "default":
            _clients[key] = AIClient()
        else:
            s = get_settings()
            match = [p for p in s.providers if p.name == key]
            if not match:
                raise AIError(f"Unknown provider: {key}")
            _clients[key] = AIClient(provider=match[0])
    return _clients[key]


def extra_provider_names() -> list:
    try:
        return [p.name for p in get_settings().providers]
    except Exception:
        return []


def _provider_model_ids(pname: str) -> list:
    now = time.time()
    hit = _model_ids_cache.get(pname)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    try:
        ids = [m["id"] for m in get_client(pname).list_models()
               if isinstance(m, dict)]
    except Exception:
        ids = []
    _model_ids_cache[pname] = (now, ids)
    return ids


def resolve_client(model_id: str):
    """OpenAI client owning a model id (default first, then extras)."""
    try:
        if model_id in _provider_model_ids("default"):
            return get_client()._client
        for pname in extra_provider_names():
            if model_id in _provider_model_ids(pname):
                return get_client(pname)._client
    except Exception as exc:
        log.debug("Provider resolve failed: %s", exc)
    return get_client()._client


def provider_fastest(pname: str) -> str:
    try:
        items = get_client(pname).list_models()
        free = [m for m in items
                if isinstance(m, dict) and m.get("free")]
        if free:
            return sort_models(free)[0]["id"]
    except Exception as exc:
        log.debug("Fastest lookup failed for %s: %s", pname, exc)
    return ""


def list_all_models() -> list:
    """Every provider's models, each tagged with its provider."""
    out = list(get_client().list_models())
    for pname in extra_provider_names():
        try:
            out += list(get_client(pname).list_models())
        except Exception as exc:
            log.warning("Provider %s list failed: %s", pname, exc)
    return out
