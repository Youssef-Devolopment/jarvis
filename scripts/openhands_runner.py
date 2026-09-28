#!/usr/bin/env python3
"""Standalone OpenHands runner. Runs under Python 3.12."""
from __future__ import annotations
import os
import sys
import time

try:
    from pydantic import SecretStr
    from openhands.sdk import LLM, Conversation, Workspace
    from openhands.tools.preset.default import get_default_agent
except ImportError as e:
    print(f"IMPORT_ERROR: {e}", file=sys.stderr)
    sys.exit(2)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: openhands_runner.py <task>", file=sys.stderr)
        return 1
    task = sys.argv[1].strip()
    if not task:
        print("Empty task.", file=sys.stderr)
        return 1

    host = os.getenv("OPENHANDS_HOST", "127.0.0.1")
    port = os.getenv("OPENHANDS_PORT", "8000")
    host_url = f"http://{host}:{port}"
    working_dir = os.getenv("OPENHANDS_WORKING_DIR", r"C:\jarvis V2")
    model = os.getenv("OPENHANDS_MODEL", "deepseek/deepseek-chat")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://tokenharbor.ai/v1")
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    session_key = os.getenv("OPENHANDS_SESSION_KEY", "").strip()

    if not api_key:
        print("DEEPSEEK_API_KEY not set.", file=sys.stderr)
        return 1

    llm = LLM(usage_id="agent", model=model, base_url=base_url,
              api_key=SecretStr(api_key))
    agent = get_default_agent(llm=llm, cli_mode=True)

    ws_kwargs = {"host": host_url, "working_dir": working_dir}
    if session_key:
        ws_kwargs["api_key"] = session_key
    workspace = Workspace(**ws_kwargs)

    collected = []

    def on_event(event):
        try:
            name = type(event).__name__
            if "Message" in name:
                src = str(getattr(event, "source", "") or "").lower()
                if src == "agent":
                    msg = getattr(event, "llm_message", None)
                    if msg is not None:
                        content = getattr(msg, "content", None) or []
                        for c in content:
                            t = getattr(c, "text", None)
                            if t and str(t).strip():
                                collected.append(str(t).strip())
        except Exception:
            pass

    try:
        conv = Conversation(agent=agent, workspace=workspace, callbacks=[on_event])
        conv.send_message(task)
        conv.run()
        time.sleep(2)
        try:
            conv.close()
        except Exception:
            pass
    except Exception as e:
        print(f"RUN_ERROR: {e}", file=sys.stderr)
        return 1

    if collected:
        print(collected[-1])
        return 0
    print("No agent reply captured.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
