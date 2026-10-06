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

    # Pre-warm browser in background so first search is instant
    import threading
    from system import health as healthmon

    def _prewarm():
        try:
            from skills.browser_agent import get_agent
            get_agent().prewarm()
            healthmon.mark("browser", True, "prewarmed")
        except Exception as _exc:
            healthmon.mark("browser", False, str(_exc)[:120])
        try:
            from voice import warmup
            warmup()  # prime TTS engine + first synth off the critical path
            healthmon.mark("voice", True, "TTS warmed")
        except Exception as _exc:
            healthmon.mark("voice", False, str(_exc)[:120])
        try:
            from ai import screen_context
            screen_context.start()   # RAM-only screen context loop
            healthmon.mark("screen_context", True)
        except Exception as _exc:
            healthmon.mark("screen_context", False, str(_exc)[:120])
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
            healthmon.mark("mcp", True,
                           f"{len(summary.get('started', []))} server(s) started")
        except Exception as exc:
            import logging
            logging.getLogger("run").warning("MCP autostart failed: %s", exc)
            healthmon.mark("mcp", False, str(exc)[:120])
    threading.Thread(target=_start_mcp, daemon=True).start()

    # Self-update: check GitHub once at boot, pull when allowed + clean
    try:
        from system import updater
        updater.boot_check()
        healthmon.mark("updater", True, "check running in background")
    except Exception as exc:
        log.warning("Update check skipped: %s", exc)
        healthmon.mark("updater", False, str(exc)[:120])

    # System Guard: RAM watchdog (pref-gated, one sample a minute)
    try:
        from system import guard
        guard.start()
        healthmon.mark("guard", True,
                       "enabled" if guard.status().get("enabled")
                       else "disabled by pref")
    except Exception as exc:
        log.warning("Guard start failed: %s", exc)
        healthmon.mark("guard", False, str(exc)[:120])

    # Start Dream Mode scheduler
    try:
        from system import dream_scheduler
        dream_scheduler.start()
        healthmon.mark("dream_scheduler", True)
    except Exception as _exc:
        import logging
        logging.getLogger("run").warning(
            "Dream scheduler failed: %s", _exc)
        healthmon.mark("dream_scheduler", False, str(_exc)[:120])

    try:
        from ai import clipboard_watcher
        clipboard_watcher.start()
        healthmon.mark("clipboard", True)
    except Exception as _exc:
        import logging
        logging.getLogger("run").warning("Clipboard failed: %s", _exc)
        healthmon.mark("clipboard", False, str(_exc)[:120])

    try:
        from system import reminder_loop
        reminder_loop.start()
        healthmon.mark("reminders", True)
    except Exception as _exc:
        import logging
        logging.getLogger("run").warning("Reminders failed: %s", _exc)
        healthmon.mark("reminders", False, str(_exc)[:120])

    try:
        from ai import time_tracker
        time_tracker.start()
        healthmon.mark("time_tracker", True)
    except Exception as _exc:
        import logging
        logging.getLogger("run").warning("Time tracker failed: %s", _exc)
        healthmon.mark("time_tracker", False, str(_exc)[:120])

    # Background scheduler: daily briefings + one-shot timers
    def _start_scheduler():
        try:
            from system.scheduler import start
            start()
            healthmon.mark("scheduler", True)
        except Exception as exc:
            import logging
            logging.getLogger("run").warning("Scheduler autostart failed: %s",
                                             exc)
            healthmon.mark("scheduler", False, str(exc)[:120])
    threading.Thread(target=_start_scheduler, daemon=True).start()

    # Folder sentinel: re-watch persisted folders
    def _start_sentinel():
        try:
            from skills.folder_sentinel import start_saved
            n = start_saved()
            if n:
                log.info("Sentinel restored %d folder(s)", n)
            healthmon.mark("folder_sentinel", True,
                           f"{n} folder(s) restored" if n else "idle")
        except Exception as exc:
            import logging
            logging.getLogger("run").warning("Sentinel autostart failed: %s",
                                             exc)
            healthmon.mark("folder_sentinel", False, str(exc)[:120])
    threading.Thread(target=_start_sentinel, daemon=True).start()

    # System integration: hotkey + tray
    try:
        from memory import get_pref
        if get_pref("hotkey_enabled", True):
            try:
                from system.hotkey import start_hotkey_listener
                threading.Thread(target=start_hotkey_listener, daemon=True).start()
                log.info("Hotkey thread started")
                healthmon.mark("hotkeys", True, "listener started")
            except Exception as exc:
                log.warning("Hotkey start failed: %s", exc)
                healthmon.mark("hotkeys", False, str(exc)[:120])
        else:
            healthmon.mark("hotkeys", True, "disabled by pref")
        if get_pref("tray_enabled", True):
            try:
                from system.tray import start_tray
                threading.Thread(target=start_tray, daemon=True).start()
                log.info("Tray thread started")
                healthmon.mark("tray", True)
            except Exception as exc:
                log.warning("Tray start failed: %s", exc)
                healthmon.mark("tray", False, str(exc)[:120])
        else:
            healthmon.mark("tray", True, "disabled by pref")
    except Exception as exc:
        log.warning("System integration skipped: %s", exc)
        healthmon.mark("hotkeys", False, str(exc)[:120])

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
