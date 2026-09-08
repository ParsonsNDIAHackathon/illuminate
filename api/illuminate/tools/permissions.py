"""The permission gate (D4): read freely, write on approval.

A WRITE or DESTRUCTIVE classification suspends execution and returns a permission
request carrying the exact statement, parameters and a *real* impact preview
(the mutation runs in a transaction that is rolled back). The user approves,
edits or refuses. The same gate serves chat and MCP.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import time
import uuid
from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel, Field

from .. import db, events
from ..config import PermissionMode, load_workspace, settings
from ..cypher.validator import CypherRejected, Validated, is_pure_create, strip_strings_and_comments, validate

Status = Literal["pending", "approved", "refused", "expired", "executed", "failed"]


class ImpactPreview(BaseModel):
    counters: dict[str, int]
    sample_rows: list[dict] = Field(default_factory=list)
    error: str | None = None

    def summary(self) -> str:
        c = self.counters
        return (
            f"creates {c.get('nodes_created',0)} node(s), {c.get('relationships_created',0)} relationship(s); "
            f"sets {c.get('properties_set',0)} propert(ies); deletes {c.get('nodes_deleted',0)} node(s), "
            f"{c.get('relationships_deleted',0)} relationship(s)"
        )

    @property
    def deleted(self) -> int:
        return self.counters.get("nodes_deleted", 0) + self.counters.get("relationships_deleted", 0)


class PermissionRequest(BaseModel):
    id: str
    statement: str
    params: dict[str, Any]
    classification: str
    preview: ImpactPreview
    source: str  # chat | mcp | ui
    conversation_id: str | None = None
    tool: str | None = None
    rationale: str | None = None
    status: Status = "pending"
    created_at: float
    resolved_at: float | None = None
    decision_note: str | None = None
    shape: str


class Decision(BaseModel):
    status: Status
    request_id: str
    result: dict | None = None
    reason: str | None = None
    statement: str | None = None


Listener = Callable[[str, dict], Awaitable[None]]


def shape_of(statement: str) -> str:
    """Normalise a statement to its 'shape' (whitespace, literals, parameters)."""
    s = strip_strings_and_comments(statement)
    s = re.sub(r"\$\w+", "$p", s)
    s = re.sub(r"\b\d+(\.\d+)?\b", "0", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return hashlib.sha1(s.encode()).hexdigest()[:16]


class PermissionGate:
    def __init__(self) -> None:
        self.requests: dict[str, PermissionRequest] = {}
        self._futures: dict[str, asyncio.Future] = {}
        self._listeners: set[Listener] = set()
        self.session_allowlist: set[str] = set()

    # -- listeners (WebSocket broadcast) ------------------------------------------
    def add_listener(self, fn: Listener) -> None:
        self._listeners.add(fn)

    def remove_listener(self, fn: Listener) -> None:
        self._listeners.discard(fn)

    async def _emit(self, event: str, payload: dict) -> None:
        for fn in list(self._listeners):
            try:
                await fn(event, payload)
            except Exception:
                self._listeners.discard(fn)

    # -- main entry ---------------------------------------------------------------
    async def request(
        self,
        validated: Validated,
        params: dict[str, Any],
        *,
        source: str,
        conversation_id: str | None = None,
        tool: str | None = None,
        rationale: str | None = None,
        mode: PermissionMode | None = None,
    ) -> Decision:
        mode = mode or load_workspace().permission_mode
        preview = await self.preview(validated.statement, params)
        req = PermissionRequest(
            id="perm_" + uuid.uuid4().hex[:10],
            statement=validated.statement,
            params=params,
            classification=validated.classification,
            preview=preview,
            source=source,
            conversation_id=conversation_id,
            tool=tool,
            rationale=rationale,
            created_at=time.time(),
            shape=shape_of(validated.statement),
        )
        self.requests[req.id] = req

        if preview.error:
            req.status = "failed"
            req.decision_note = preview.error
            await self._emit("permission_failed", req.model_dump())
            return Decision(status="failed", request_id=req.id, reason=preview.error, statement=req.statement)

        # Auto-approval paths. Destructive statements never auto-approve.
        auto = False
        if validated.classification == "WRITE":
            if mode == "auto_create" and is_pure_create(validated.statement) and preview.deleted == 0:
                auto = True
            elif mode == "session_allowlist" and req.shape in self.session_allowlist:
                auto = True
        if auto:
            req.decision_note = f"auto-approved ({mode})"
            return await self._execute(req)

        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._futures[req.id] = fut
        await self._emit("permission_request", req.model_dump())
        try:
            return await asyncio.wait_for(fut, timeout=settings.permission_timeout_s)
        except asyncio.TimeoutError:
            req.status = "expired"
            req.resolved_at = time.time()
            await self._emit("permission_resolved", req.model_dump())
            return Decision(status="expired", request_id=req.id, reason="no decision within the timeout", statement=req.statement)
        finally:
            self._futures.pop(req.id, None)

    async def preview(self, statement: str, params: dict[str, Any]) -> ImpactPreview:
        try:
            res = await db.dry_run(statement, params)
            return ImpactPreview(counters=res["counters"], sample_rows=res["rows"][:10])
        except Exception as e:  # syntax/semantic errors surface here, before anything is committed
            return ImpactPreview(counters={}, error=str(e))

    async def _execute(self, req: PermissionRequest) -> Decision:
        try:
            res = await db.write(req.statement, req.params)
            req.status = "executed"
            req.resolved_at = time.time()
            await self._emit("permission_resolved", req.model_dump())
            # Every approved write is a graph change; tell the open canvases about it so a
            # new entity lands on the canvas without a reload, whether it came from chat or MCP.
            await events.announce(events.node_ids(req.params, res.get("rows")), reason=req.tool or "write", source=req.source)
            return Decision(status="executed", request_id=req.id, result=res, statement=req.statement)
        except Exception as e:
            req.status = "failed"
            req.decision_note = str(e)
            req.resolved_at = time.time()
            await self._emit("permission_resolved", req.model_dump())
            return Decision(status="failed", request_id=req.id, reason=str(e), statement=req.statement)

    # -- decisions from the UI -----------------------------------------------------
    async def approve(
        self,
        request_id: str,
        *,
        edited_statement: str | None = None,
        edited_params: dict[str, Any] | None = None,
        remember_shape: bool = False,
        acknowledge_count: int | None = None,
    ) -> Decision:
        req = self.requests.get(request_id)
        if not req:
            raise KeyError(request_id)
        if req.status != "pending":
            return Decision(status=req.status, request_id=req.id, reason="already resolved", statement=req.statement)

        if edited_statement is not None and edited_statement.strip() != req.statement.strip():
            try:
                v = validate(edited_statement, params=edited_params or req.params)
            except CypherRejected as e:
                return Decision(status="pending", request_id=req.id, reason=f"edited statement rejected: {e.reason}", statement=req.statement)
            req.statement = v.statement
            req.classification = v.classification
            req.params = edited_params if edited_params is not None else req.params
            req.shape = shape_of(req.statement)
            req.preview = await self.preview(req.statement, req.params)
            if req.preview.error:
                return Decision(status="pending", request_id=req.id, reason=f"edited statement failed preview: {req.preview.error}", statement=req.statement)

        if req.classification == "DESTRUCTIVE" and acknowledge_count != req.preview.deleted:
            return Decision(
                status="pending", request_id=req.id,
                reason=f"destructive statement: acknowledge the affected count ({req.preview.deleted}) to proceed",
                statement=req.statement,
            )

        if remember_shape:
            self.session_allowlist.add(req.shape)
        req.status = "approved"
        decision = await self._execute(req)
        fut = self._futures.get(request_id)
        if fut and not fut.done():
            fut.set_result(decision)
        return decision

    async def refuse(self, request_id: str, reason: str | None = None) -> Decision:
        req = self.requests.get(request_id)
        if not req:
            raise KeyError(request_id)
        if req.status != "pending":
            return Decision(status=req.status, request_id=req.id, reason="already resolved", statement=req.statement)
        req.status = "refused"
        req.decision_note = reason
        req.resolved_at = time.time()
        decision = Decision(status="refused", request_id=req.id, reason=reason or "refused by user", statement=req.statement)
        await self._emit("permission_resolved", req.model_dump())
        fut = self._futures.get(request_id)
        if fut and not fut.done():
            fut.set_result(decision)
        return decision

    def pending(self) -> list[PermissionRequest]:
        return [r for r in self.requests.values() if r.status == "pending"]

    def history(self, limit: int = 100) -> list[PermissionRequest]:
        return sorted(self.requests.values(), key=lambda r: r.created_at, reverse=True)[:limit]


gate = PermissionGate()
