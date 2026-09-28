"""Snippet vault, layouts, URL cleaner, time summary skills."""
from skills.registry import register

@register("snippet_save", [
    r"^(?:save|حفظ)\s+snippet\s+(?P<title>.+?)[\?\.\!]?$",
], "Save clipboard as snippet")
def skill_snippet_save(text, match):
    try:
        from ai import snippets
        import pyperclip
        code = pyperclip.paste() or ""
        if not code: return "Clipboard empty."
        title = match.group("title").strip()
        r = snippets.save(title, code)
        return f"Saved snippet: {title}" if r.get("ok") else "Could not save snippet."
    except Exception as exc:
        return f"Snippet error: {str(exc)[:100]}"

@register("snippet_list", [
    r"^(?:list|show)\s+snippets(?:\s+(?P<q>.+))?[\?\.\!]?$",
], "List snippets")
def skill_snippet_list(text, match):
    try:
        from ai import snippets
        q = (match.groupdict().get("q") or "").strip()
        items = snippets.list_all(query=q)
        if not items: return "No snippets."
        lines = [f"{len(items)} snippet(s):"]
        for s in items[:5]:
            lines.append(f"  #{s['id']} {s['title']}")
        return " ".join(lines)
    except Exception as exc:
        return f"Snippet error: {str(exc)[:100]}"

@register("layout_save", [
    r"^(?:save|حفظ)\s+(?:window\s+)?layout\s+(?P<name>\w+)[\?\.\!]?$",
], "Save window layout")
def skill_layout_save(text, match):
    try:
        from ai import window_layouts
        name = match.group("name")
        r = window_layouts.save(name)
        return f"Saved layout '{name}' ({r.get('count',0)} windows)." if r.get("ok") else "Could not save."
    except Exception as exc:
        return f"Layout error: {str(exc)[:100]}"

@register("layout_restore", [
    r"^(?:load|restore|استرجع)\s+(?:window\s+)?layout\s+(?P<name>\w+)[\?\.\!]?$",
], "Restore window layout")
def skill_layout_restore(text, match):
    try:
        from ai import window_layouts
        name = match.group("name")
        r = window_layouts.restore(name)
        return f"Restored {r.get('restored',0)}/{r.get('total',0)} windows from '{name}'." if r.get("ok") else f"Failed: {r.get('error')}"
    except Exception as exc:
        return f"Layout error: {str(exc)[:100]}"

@register("url_clean", [
    r"^(?:clean|نضف)\s+(?:the\s+)?url[\?\.\!]?$",
    r"^(?:clean|نضف)\s+(?:the\s+)?link[\?\.\!]?$",
], "Clean URL in clipboard")
def skill_url_clean(text, match):
    try:
        from ai import url_cleaner
        r = url_cleaner.clean_clipboard()
        return f"Cleaned: {r['after']}" if r.get("ok") else f"URL error: {r.get('error')}"
    except Exception as exc:
        return f"URL error: {str(exc)[:100]}"

@register("time_summary", [
    r"^(?:time|وقت)\s+(?:summary|report|تقرير)[\?\.\!]?$",
    r"^(?:where|إيه)\s+(?:did|my)\s+time\s+go[\?\.\!]?$",
], "Time tracking summary")
def skill_time_summary(text, match):
    try:
        from ai import time_tracker
        rows = time_tracker.summary(hours=24)
        if not rows: return "No time entries yet."
        lines = ["Last 24h:"]
        for r in rows[:5]:
            mins = r["seconds"] // 60
            lines.append(f"  {r['app']}: {mins} min")
        return " ".join(lines)
    except Exception as exc:
        return f"Time error: {str(exc)[:100]}"
