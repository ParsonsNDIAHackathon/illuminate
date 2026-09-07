"""Model access with the user's own key (D7) and two tiers (D8)."""
from __future__ import annotations

from openai import AsyncOpenAI

from ..config import load_workspace, settings
from ..vault import vault


class NoModelKey(Exception):
    pass


def has_key(user: str = "local") -> bool:
    return bool(vault().get(user, "openai"))


def client_for(user: str = "local") -> AsyncOpenAI | None:
    key = vault().get(user, "openai")
    if not key:
        return None
    ws = load_workspace()
    return AsyncOpenAI(api_key=key, base_url=ws.openai_base_url or settings.openai_base_url or None)


def models(user: str = "local") -> tuple[str, str]:
    """(strong, fast)"""
    ws = load_workspace()
    return ws.model_strong or settings.model_strong, ws.model_fast or settings.model_fast


async def check_key(user: str = "local") -> dict:
    c = client_for(user)
    if not c:
        return {"ok": False, "error": "no key"}
    try:
        page = await c.models.list()
        ids = [m.id for m in page.data][:200]
        strong, fast = models(user)
        return {"ok": True, "models": len(ids), "strong_available": strong in ids or not ids, "fast_available": fast in ids or not ids}
    except Exception as e:
        return {"ok": False, "error": str(e)}
