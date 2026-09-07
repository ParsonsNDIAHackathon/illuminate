from __future__ import annotations

from fastapi import Header


async def user_id(x_user: str | None = Header(default=None)) -> str:
    """Single workspace; credentials are per user record (hackathon cut: no real auth)."""
    return (x_user or "local").strip()[:64] or "local"
