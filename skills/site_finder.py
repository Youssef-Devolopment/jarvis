"""Site finder — bookmarks and most-visited sites."""
from skills.registry import register


@register("site_find", [
    r"^(?:list|show)\s+(?:my\s+)?(?:bookmarks|bookmarked(?:\s+sites)?|favorite\s+sites)[\?\.\!]?$",
    r"^(?:most\s+visited|frequent|top)\s+sites[\?\.\!]?$",
    r"^(?:where|what)\s+(?:is|are)\s+my\s+bookmarks[\?\.\!]?$",
], "List bookmarks and top sites")
def skill_site_find(text, match):
    try:
        from ai import site_index
        data = site_index.load_index()
        marks = data.get("bookmarks", [])[:10]
        hist = sorted(data.get("history", []),
                      key=lambda h: h.get("visits", 0), reverse=True)[:5]
        if not marks and not hist:
            return "No browser data found."
        parts = []
        if marks:
            parts.append("Bookmarks: " + ", ".join(
                m["title"][:40] for m in marks[:6]))
        if hist:
            parts.append("Most visited: " + ", ".join(
                f"{h['title'][:30]} ({h.get('visits', 0)}x)"
                for h in hist[:4]))
        return " ".join(parts)
    except Exception as exc:
        return f"Sites error: {str(exc)[:100]}"


@register("site_refresh", [
    r"^re(?:fresh|scan)(?:\s+the)?\s+sites?[\?\.\!]?$",
], "Rescan browser bookmarks and history")
def skill_site_refresh(text, match):
    try:
        from ai import site_index
        data = site_index.refresh()
        return (f"Sites rescanned: "
                f"{len(data.get('bookmarks', []))} bookmarks, "
                f"{len(data.get('history', []))} history entries.")
    except Exception as exc:
        return f"Rescan failed: {str(exc)[:100]}"
