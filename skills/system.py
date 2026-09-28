import platform, shutil
from pathlib import Path
from skills.registry import register
try:
    import psutil
except ImportError:
    psutil = None


@register("system", [
    r"\b(?:system\s+(?:status|report)|diagnostics|status\s+report)\b",
    r"\b(?:cpu|memory|ram|disk|battery)\b",
    r"\bhow\s+are\s+you\s+doing\b",
], "System diagnostics")
def skill_system(text, match):
    b = []
    if psutil:
        b.append(f"CPU load {psutil.cpu_percent(interval=0.3):.0f} percent")
        b.append(f"memory {psutil.virtual_memory().percent:.0f} percent used")
        d = psutil.disk_usage(str(Path.home()))
        b.append(f"disk {d.percent:.0f} percent used")
        bat = getattr(psutil, "sensors_battery", lambda: None)()
        if bat:
            st = "charging" if bat.power_plugged else "on battery"
            b.append(f"battery {bat.percent:.0f} percent, {st}")
    else:
        t, u, _ = shutil.disk_usage(str(Path.home()))
        b.append(f"disk {u/t*100:.0f} percent used")
    b.append(f"running {platform.system()} on {platform.machine()}")
    return "All systems nominal: " + ", ".join(b) + "."
