from skills.registry import register

@register("this_project_is_you", [
    r"this\s+(?P<thing>project|repo|repository|codebase|app|thing)\s+is\s+you\b",
    r"you\s+are\s+(?:this|the)\s+(?P<thing>project|repo|repository|codebase|app)\b",
    r"(?:is|are)\s+you\s+(?:the\s+)?(?P<thing>project|repo|repository|codebase)\b",
], "Confirms that this project is JARVIS itself")
def this_project_is_you(text, match):
    thing = (match.group("thing") or "project").lower()
    lines = {
        "repo": "this repo",
        "repository": "this repository",
        "codebase": "this codebase",
        "app": "this app",
    }
    label = lines.get(thing, "this project")
    return (
        "Guilty as charged - " + label + " is me. "
        "I'm JARVIS: the registry, the regex router, and the voice you're hearing. "
        "Every skill in here is a little piece of my own brain, so patching this code "
        "is literally self-improvement. What should I learn next?"
    )