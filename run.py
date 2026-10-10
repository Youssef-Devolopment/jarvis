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

    from system import startup

    # Fail fast: a busy port says so BEFORE we boot the world (werkzeug
    # would otherwise exit 1 after everything started, with a message
    # nobody can act on).
    err = startup.ensure_port(s.host, s.port)
    if err:
        print(startup.bind_error(err, s.host, s.port), end="", flush=True)
        sys.exit(3)

    # First-run status block: mode, model, voice, mood, memory — each
    # line guarded so a broken subsystem degrades to "unavailable"
    # instead of crashing the boot.
    print()
    for line in startup.status_lines(s, skills_only):
        print(line)
    print()

    # One registry boots every background service — the same set the
    # desktop launcher uses. Each service is isolated and timed;
    # immediate failures print here, async results land in /api/health.
    from system import services
    summary = services.boot(mode="console")
    degraded = (" — degraded: " + ", ".join(summary["failed"])
                if summary["failed"] else "")
    print(f"  Services : {summary['launched']} launched{degraded}"
          f" ({summary['ms']}ms)")

    # One consistent health voice: the same reporter that writes the
    # log line prints the friendly verdict here ~20s after boot, once
    # async services (MCP, voice warmup) have settled. ok/warn/degraded
    # all get an explicit, actionable line.
    from server import schedule_health_log
    schedule_health_log(
        on_summary=lambda snap: print(*startup.health_block(snap),
                                      sep="\n", flush=True))

    try:
        from memory import context as ctx_tracker
        _sid = ctx_tracker.start_session()
        import atexit
        atexit.register(lambda: ctx_tracker.end_session(_sid, "server stopped"))
    except Exception:
        pass

    try:
        app.run(host=s.host, port=s.port, debug=s.debug, threaded=True)
    except OSError as exc:
        # Port race after the probe — plain words, not a traceback.
        print(startup.bind_error(exc, s.host, s.port), end="", flush=True)
        sys.exit(3)


if __name__ == "__main__":
    main()
