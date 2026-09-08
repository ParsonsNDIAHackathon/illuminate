"""WebSocket chat plus the broadcast channel for permission requests and
enrichment job updates."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import load_workspace
from ..llm.chat import get_conversation, list_conversations, run_turn
from ..llm.client import has_key
from ..tools.handlers import ToolContext

router = APIRouter(tags=["chat"])


class ConnectionManager:
    def __init__(self) -> None:
        self.active: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.active.discard(ws)

    async def broadcast(self, event: str, payload: dict) -> None:
        msg = json.dumps({"type": event, **({"payload": payload})}, default=str)
        for ws in list(self.active):
            try:
                await ws.send_text(msg)
            except Exception:
                self.active.discard(ws)


manager = ConnectionManager()


@router.get("/api/conversations")
async def conversations():
    return list_conversations()


@router.get("/api/conversations/{cid}")
async def conversation(cid: str):
    c = get_conversation(cid)
    return {"id": c.id, "title": c.title, "messages": [m for m in c.messages if m["role"] in ("user", "assistant") and m.get("content")]}


@router.websocket("/ws/chat")
async def ws_chat(ws: WebSocket):
    await manager.connect(ws)
    user = ws.query_params.get("user") or "local"
    try:
        await ws.send_text(json.dumps({"type": "hello", "model_key": has_key(user), "workspace": load_workspace().model_dump()}))
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
                continue
            if msg.get("type") != "message":
                continue
            conv = get_conversation(msg.get("conversation_id"))
            ws_settings = load_workspace()
            # The focused program travels with the message: it is what the canvas is
            # showing right now, which the server has no other way of knowing.
            ctx = ToolContext(source="chat", conversation_id=conv.id, user=user,
                              layers=msg.get("layers") or ws_settings.layers,
                              include_simulated=ws_settings.include_simulated,
                              focus_id=msg.get("focus_id"), focus_label=msg.get("focus_label"))

            async def emit(ev: dict, _ws=ws, _cid=conv.id):
                ev = {**ev, "conversation_id": _cid}
                await _ws.send_text(json.dumps(ev, default=str))

            await ws.send_text(json.dumps({"type": "turn_start", "conversation_id": conv.id}))
            # run as a task so permission approvals over REST can interleave
            asyncio.create_task(_safe_turn(conv, msg.get("text", ""), ctx, emit, msg.get("canvas_ids")))
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)


async def _safe_turn(conv, text, ctx, emit, canvas_ids):
    try:
        await run_turn(conv, text, ctx, emit, canvas_ids)
    except Exception:
        try:
            await emit({
                "type": "error",
                "message": "Chat turn failed safely. Deterministic graph tools remain available.",
            })
        except Exception:
            pass
