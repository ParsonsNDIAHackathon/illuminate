"""The agent loop: streams the model's answer, executes tool calls through the
shared handler module, and aggregates subgraph + style_ops for the UI."""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..config import load_workspace  # compatibility hook for existing chat integrations/tests
from ..cypher.templates import match_intent
from ..graphio import merge_subgraphs
from ..styles import derive_legend, validate_ops
from ..tools.contract import openai_tools
from ..tools.handlers import ToolContext, ToolResult, dispatch, safe_tool_data
from .client import client_for, models
from .prompts import constant_prefix, turn_context

Emit = Callable[[dict], Awaitable[None]]
MAX_TOOL_ROUNDS = 8
SAFE_NO_RESULT = (
    "I can only state supplier facts from current deterministic graph results. "
    "Please ask me to search the graph or run a named analysis."
)


@dataclass
class Conversation:
    id: str
    messages: list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    title: str | None = None


_conversations: dict[str, Conversation] = {}


def get_conversation(cid: str | None) -> Conversation:
    if cid and cid in _conversations:
        return _conversations[cid]
    c = Conversation(id=cid or "conv_" + uuid.uuid4().hex[:10])
    _conversations[c.id] = c
    return c


def list_conversations() -> list[dict]:
    return [{"id": c.id, "title": c.title, "created_at": c.created_at, "turns": sum(1 for m in c.messages if m["role"] == "user")} for c in _conversations.values()]


@dataclass
class TurnAccumulator:
    cypher: list[dict] = field(default_factory=list)
    subgraph: dict | None = None
    style_ops: list[dict] = field(default_factory=list)
    permissions: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    guarded_answer: str | None = None
    deterministic_notes: list[str] = field(default_factory=list)

    def absorb(self, name: str, args: dict, r: ToolResult) -> None:
        self.tool_calls.append({"name": name, "args": args, "ok": r.ok})
        self.deterministic_notes.append(f"{name}: {_summarise(r)}")
        if r.cypher:
            self.cypher.append({"tool": name, "statement": r.cypher, "params": r.params or {}, "notes": r.notes})
        if r.subgraph:
            self.subgraph = merge_subgraphs(self.subgraph or {}, r.subgraph)
        if r.style_ops:
            self.style_ops.extend(r.style_ops)
        if r.permission:
            self.permissions.append(r.permission)
        if name == "get_entity_report" and isinstance(r.data, dict):
            summary = r.data.get("summary")
            if isinstance(summary, dict) and summary.get("text"):
                citations = summary.get("citations") or []
                suffix = f"\n\nEvidence: {', '.join(citations)}" if citations else ""
                self.guarded_answer = str(summary["text"]) + suffix

    def safe_answer(self) -> str:
        if self.guarded_answer:
            return self.guarded_answer
        if self.deterministic_notes:
            return "Deterministic tool results — " + "; ".join(self.deterministic_notes) + "."
        return SAFE_NO_RESULT

    def final(self, answer: str) -> dict:
        ops = validate_ops(self.style_ops) if self.style_ops else []
        return {
            "type": "answer",
            "answer": self.guarded_answer or answer,
            "cypher": self.cypher,
            "subgraph": self.subgraph,
            "style_ops": [o.model_dump(exclude_none=True) for o in ops],
            "legend": [l.model_dump() for l in derive_legend(ops)],
            "permissions": self.permissions,
            "tool_calls": self.tool_calls,
        }


async def run_turn(conv: Conversation, text: str, ctx: ToolContext, emit: Emit, canvas_ids: list[str] | None = None) -> dict:
    conv.messages.append({"role": "user", "content": text})
    if not conv.title:
        conv.title = text[:60]
    acc = TurnAccumulator()
    client = client_for(ctx.user)
    if client is None:
        return await _template_only_turn(conv, text, ctx, emit, acc)

    strong, _fast = models(ctx.user)
    system = [
        {"role": "system", "content": constant_prefix()},
        {"role": "system", "content": turn_context(ctx.focus_id, ctx.focus_label, ctx.layers, canvas_ids)},
    ]
    tools = openai_tools()

    for _round in range(MAX_TOOL_ROUNDS + 1):
        content = ""
        tool_calls: dict[int, dict] = {}
        try:
            stream = await client.chat.completions.create(model=strong, messages=system + conv.messages, tools=tools, stream=True)
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta is None:
                    continue
                if delta.content:
                    content += delta.content
                for tc in delta.tool_calls or []:
                    slot = tool_calls.setdefault(tc.index, {"id": tc.id or "", "name": "", "arguments": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            slot["name"] += tc.function.name
                        if tc.function.arguments:
                            slot["arguments"] += tc.function.arguments
        except Exception:
            msg = "The model is unavailable. Deterministic graph results and evidence remain available; no scores or findings were changed."
            await emit({"type": "model_unavailable", "message": msg})
            final = acc.final(msg)
            conv.messages.append({"role": "assistant", "content": final["answer"]})
            await emit(final)
            return final

        if not tool_calls:
            final = acc.final(acc.safe_answer())
            conv.messages.append({"role": "assistant", "content": final["answer"]})
            if final["answer"]:
                await emit({"type": "delta", "text": final["answer"]})
            await emit(final)
            return final

        calls = [tool_calls[i] for i in sorted(tool_calls)]
        conv.messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": c["id"] or f"call_{i}", "type": "function", "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}} for i, c in enumerate(calls)],
        })
        for i, c in enumerate(calls):
            try:
                args = json.loads(c["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            await emit({"type": "tool_call", "name": c["name"], "args": args})
            result = await dispatch(ctx, c["name"], args)
            acc.absorb(c["name"], args, result)
            await emit({
                "type": "tool_result", "name": c["name"], "ok": result.ok, "cypher": result.cypher, "params": safe_tool_data(result.params),
                "summary": _summarise(result), "permission": result.permission, "notes": result.notes,
                "subgraph": result.subgraph, "style_ops": result.style_ops, "legend": result.legend,
            })
            conv.messages.append({"role": "tool", "tool_call_id": c["id"] or f"call_{i}", "content": result.for_model(c["name"])})

    msg = "Stopped after too many tool rounds; refine the question."
    final = acc.final(acc.safe_answer())
    conv.messages.append({"role": "assistant", "content": final["answer"]})
    await emit(final)
    return final


def _summarise(r: ToolResult) -> str:
    d = r.data if isinstance(r.data, dict) else {}
    if not r.ok:
        return str(d.get("error") or "failed")
    if "row_count" in d:
        return f"{d['row_count']} row(s)"
    if "results" in d:
        return f"{len(d['results'])} match(es)"
    if "counters" in d:
        c = d["counters"]
        return f"created {c.get('nodes_created',0)} node(s), {c.get('relationships_created',0)} rel(s)"
    if "applied" in d:
        return f"{d['applied']} style op(s)"
    if "job_id" in d:
        return f"enrichment queued ({d['job_id']})"
    if "nodes" in d:
        return f"{len(d['nodes'])} node(s), {len(d.get('edges', []))} edge(s)"
    return "ok"


_ENTITY_HINT = re.compile(r"\b(?:of|for|owns?|about)\s+([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,4})")


async def _template_only_turn(conv: Conversation, text: str, ctx: ToolContext, emit: Emit, acc: TurnAccumulator) -> dict:
    """No model key: degrade to template queries matched by intent, not an error."""
    name = match_intent(text)
    if not name:
        msg = ("No OpenAI key is configured, so I can only run saved templates. Try: 'show sole-source suppliers', "
               "'foreign parent', 'shared directors', 'goods vs services', 'manufactures in CN', or add a key under Settings › Connectors.")
        conv.messages.append({"role": "assistant", "content": msg})
        final = acc.final(msg)
        await emit(final)
        return final
    params: dict[str, Any] = {}
    m = _ENTITY_HINT.search(text)
    if m and name in ("vendors_of", "color_by_category", "ownership_chain", "people_of", "as_of_board"):
        s = await dispatch(ctx, "search_entities", {"query": m.group(1), "kind": "entity", "limit": 1})
        if s.ok and s.data["results"]:
            params["entity_id"] = s.data["results"][0]["id"]
    cm = re.search(r"\b(?:in|from)\s+(?:country\s+)?([A-Z]{2})\b", text)
    if cm:
        params["country"] = cm.group(1)
    tm = re.search(r"tier\s+(\d)", text, re.I)
    if tm:
        params["min_tier"] = int(tm.group(1))
    dm = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if dm:
        params["date"] = dm.group(1)
    await emit({"type": "tool_call", "name": "run_template", "args": {"name": name, "params": params}})
    r = await dispatch(ctx, "run_template", {"name": name, "params": params})
    acc.absorb("run_template", {"name": name, "params": params}, r)
    await emit({"type": "tool_result", "name": "run_template", "ok": r.ok, "cypher": r.cypher, "params": r.params, "summary": _summarise(r),
                "subgraph": r.subgraph, "style_ops": r.style_ops, "legend": r.legend, "notes": r.notes})
    if r.ok:
        n = r.data.get("row_count", 0)
        msg = f"Template `{name}` returned {n} row(s) (no model key — template mode)."
    else:
        msg = f"Template `{name}` could not run: {r.data.get('error')}"
    conv.messages.append({"role": "assistant", "content": msg})
    final = acc.final(msg)
    await emit(final)
    return final
