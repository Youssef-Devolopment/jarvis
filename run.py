from __future__ import annotations
import sys
from logger import get_logger, setup_logging

setup_logging("INFO")
log = get_logger("run")

try:
    from config import get_settings
    from errors import ConfigError
    from server import app
except Exception as exc:
    log.critical("Startup failed: %s", exc, exc_info=True)
    print(f"\n[!] Startup failed: {exc}\n    See logs/jarvis.log\n")
    sys.exit(1)


def main():
    from system import singleton
    if not singleton.acquire():
        print("\n[!] JARVIS is already running "
              "(see logs/jarvis.lock). Not starting a second copy.\n")
        sys.exit(2)
    try:
        s = get_settings()
        skills_only = False
    except ConfigError:
        from config import Settings
        s = Settings.load(require_key=False)
        skills_only = True
        print("\n  [!] No API key — skills-only mode "
              "(local skills work, LLM chat needs DEEPSEEK_API_KEY).")
    import moods, memory
    print(f"\n  JARVIS online  ->  http://{s.host}:{s.port}")
    print(f"  Model   : {s.model}{'  (skills-only)' if skills_only else ''}")
    print(f"  Voice   : {s.voice_name}  (British)")
    print(f"  Mood    : {moods.current_name()}")
    print(f"  Memory  : {len(memory.all_facts())} facts on file")
    print(f"  Mode    : {'DEV (debug on)' if getattr(s, 'debug', False) else 'production'}")
    print(f"  Logs    : logs/jarvis.log\n")

    # One registry boots every background service — the same set the
    # desktop launcher uses. Each service is isolated and timed;
    # immediate failures print here, async results land in /api/health.
    from system import services
    summary = services.boot(mode="console")
    degraded = (" — degraded: " + ", ".join(summary["failed"])
                if summary["failed"] else "")
    print(f"  Services : {summary['launched']} launched{degraded}"
          f" ({summary['ms']}ms)")

    # A health glance lands in logs/jarvis.log ~20s after boot, once
    # async services (MCP, voice warmup) have settled.
    from server import schedule_health_log
    schedule_health_log()

    try:
        from memory import context as ctx_tracker
        _sid = ctx_tracker.start_session()
        import atexit
        atexit.register(lambda: ctx_tracker.end_session(_sid, "server stopped"))
    except Exception:
        pass

    app.run(host=s.host, port=s.port, debug=s.debug, threaded=True)


if __name__ == "__main__":
    main()
