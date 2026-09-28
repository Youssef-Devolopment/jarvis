from __future__ import annotations
import sys
from logger import get_logger, setup_logging

setup_logging("INFO")
log = get_logger("run")

try:
    from config import get_settings
    from server import app
except Exception as exc:
    log.critical("Startup failed: %s", exc, exc_info=True)
    print(f"\n[!] Startup failed: {exc}\n    See logs/jarvis.log\n")
    sys.exit(1)


def main():
    s = get_settings()
    import moods, memory
    print(f"\n  JARVIS online  ->  http://{s.host}:{s.port}")
    print(f"  Model   : {s.model}")
    print(f"  Voice   : {s.voice_name}  (British)")
    print(f"  Mood    : {moods.current_name()}")
    print(f"  Memory  : {len(memory.all_facts())} facts on file")
    print(f"  Logs    : logs/jarvis.log\n")

    # Pre-warm browser in background so first search is instant
    import threading
    def _prewarm():
        try:
            from skills.browser_agent import get_agent
            get_agent().prewarm()
        except Exception:
            pass
    threading.Thread(target=_prewarm, daemon=True).start()

    # Auto-start enabled MCP servers in background
    def _start_mcp():
        try:
            from mcp import runtime
            summary = runtime.start_all()
            if summary.get("started"):
                import logging
                logging.getLogger("run").info(
                    "MCP started: %s", ", ".join(summary["started"]))
        except Exception as exc:
            import logging
            logging.getLogger("run").warning("MCP autostart failed: %s", exc)
    threading.Thread(target=_start_mcp, daemon=True).start()

    # Background scheduler: daily briefings + one-shot timers
    def _start_scheduler():
        try:
            from system.scheduler import start
            start()
        except Exception as exc:
            import logging
            logging.getLogger("run").warning("Scheduler autostart failed: %s",
                                             exc)
    threading.Thread(target=_start_scheduler, daemon=True).start()

    # Folder sentinel: re-watch persisted folders
    def _start_sentinel():
        try:
            from skills.folder_sentinel import start_saved
            n = start_saved()
            if n:
                log.info("Sentinel restored %d folder(s)", n)
        except Exception as exc:
            import logging
            logging.getLogger("run").warning("Sentinel autostart failed: %s",
                                             exc)
    threading.Thread(target=_start_sentinel, daemon=True).start()

    # System integration: hotkey + tray
    try:
        from memory import get_pref
        if get_pref("hotkey_enabled", True):
            try:
                from system.hotkey import start_hotkey_listener
                threading.Thread(target=start_hotkey_listener, daemon=True).start()
                log.info("Hotkey thread started")
            except Exception as exc:
                log.warning("Hotkey start failed: %s", exc)
        if get_pref("tray_enabled", True):
            try:
                from system.tray import start_tray
                threading.Thread(target=start_tray, daemon=True).start()
                log.info("Tray thread started")
            except Exception as exc:
                log.warning("Tray start failed: %s", exc)
    except Exception as exc:
        log.warning("System integration skipped: %s", exc)

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
