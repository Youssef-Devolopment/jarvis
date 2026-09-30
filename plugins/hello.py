"""Example community plugin — proves the pipeline works."""
from skills.registry import register


@register("plugin_hello", [
    r"^(?:hello|hey|hi)\s+community[\?\.\!]?$",
], "Greet the plugin community")
def skill_hello_community(text, match):
    return ("Hello from the community plugins folder. "
            "Copy _template.py to build your own.")
