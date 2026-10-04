# Auto-learned by JARVIS (system/app_learner.py).
# Safe: opens one known local application.
from skills.registry import register

@register('app_ex',
          ['^(?:open|launch|start|run)\\s+(?:the\\s+)?(?:app\\s+)?ex[\\?\\.\\!]?$'],
          "Open ex (learned app)", front=True)
def app_ex(text, match):
    from system.app_learner import launch_learned, ask_user
    return launch_learned('C:\\Program Files\\Git\\usr\\bin\\ex.exe', 'ex', ask_fn=ask_user) \
        or "OK, not opening it."
