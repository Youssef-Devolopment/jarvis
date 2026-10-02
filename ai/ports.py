"""Port sentinel — see what's listening, kill what shouldn't be."""

from __future__ import annotations
import os
from logger import get_logger

log = get_logger(__name__)


def list_listeners() -> list:
    """All listening TCP/UDP sockets with owning process. Sorted by port."""
    try:
        import psutil
    except ImportError:
        return [{"error": "psutil not installed"}]
    out = []
    try:
        for c in psutil.net_connections(kind="inet"):
            if (c.status or "") != "LISTEN":
                continue
            try:
                laddr = c.laddr
                port = laddr.port if hasattr(laddr, "port") else laddr[1]
            except Exception:
                continue
            name, pid = "", 0
            try:
                if c.pid:
                    p = psutil.Process(c.pid)
                    name, pid = p.name(), c.pid
            except Exception:
                pass
            out.append({
                "port": port,
                "proto": "tcp" if c.type == 1 else "udp",
                "pid": pid,
                "process": name,
                "mine": pid == os.getpid(),
            })
    except Exception as exc:
        log.warning("Port scan failed: %s", exc)
        return [{"error": str(exc)[:120]}]
    return sorted(out, key=lambda e: (e.get("port") or 0))


def kill_listener(pid: int, port: int = 0) -> dict:
    """Kill the process holding a port. Refuses self + system PIDs."""
    import os
    try:
        pid = int(pid)
    except Exception:
        return {"ok": False, "error": "bad pid"}
    if pid <= 0:
        return {"ok": False, "error": "bad pid"}
    if pid == os.getpid():
        return {"ok": False, "error": "refusing to kill myself"}
    if pid in (0, 1, 4):
        return {"ok": False, "error": "refusing to kill a system process"}
    try:
        import psutil
        if not psutil.pid_exists(pid):
            return {"ok": False, "error": f"pid {pid} not running"}
        if port:
            held = [c for c in psutil.net_connections(kind="inet")
                    if c.pid == pid]
            ports = set()
            for c in held:
                try:
                    la = c.laddr
                    ports.add(la.port if hasattr(la, "port") else la[1])
                except Exception:
                    pass
            if int(port) not in ports:
                return {"ok": False,
                        "error": f"pid {pid} is not holding port {port}"}
        psutil.Process(pid).terminate()
        try:
            psutil.Process(pid).wait(timeout=5)
        except Exception:
            try:
                psutil.Process(pid).kill()
            except Exception:
                pass
        log.info("Port sentinel killed pid %d (port %s)", pid, port or "?")
        return {"ok": True, "pid": pid}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:160]}
