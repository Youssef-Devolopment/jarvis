"""The /api blueprint — assembled from per-domain route modules.

The shared imports, helpers and the single `bp` blueprint live in
``routes/_common.py``. Importing each module below registers its
routes on that one blueprint, so the URL surface is identical to the
old monolithic ``routes/api.py``.
"""
from routes import (  # noqa: F401
    api_chat,
    api_core,
    api_desktop,
    api_market,
    api_mcp,
    api_memory,
    api_reasoning,
    api_skills,
    api_voice,
)
from routes._common import bp  # noqa: F401
