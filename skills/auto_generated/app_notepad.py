# Auto-learned by JARVIS (system/app_learner.py).
# Safe: opens one known local application.
from skills.registry import register

@register('app_notepad',
          ['^(?:open|launch|start|run)\\s+(?:the\\s+)?(?:app\\s+)?notepad[\\?\\.\\!]?$'],
          "Open notepad (learned app)", front=True)
def app_notepad(text, match):
    from system.app_learner import launch_learned, ask_user
    return launch_learned('C:\\Windows\\system32\\notepad.exe', 'notepad', ask_fn=ask_user) \
        or "OK, not opening it."
