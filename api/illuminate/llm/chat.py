"""The agent loop: streams the model's answer, executes tool calls through the
shared handler module, and aggregates subgraph + style_ops for the UI."""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..cypher.templates import match_intent
from ..graphio import merge_subgraphs
from ..styles import derive_legend, validate_ops
from ..tools.contract import openai_tools
from ..tools.handlers import ToolContext, ToolResult, dispatch
from .client import client_for, models
from .prompts import constant_prefix, turn_context

Emit = Callable[[dict], Awaitable[None]]
MAX_TOOL_ROUNDS = 8


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
    links: list[dict] = field(default_factory=list)

    def absorb(self, name: str, args: dict, r: ToolResult) -> None:
        self.tool_calls.append({"name": name, "args": args, "ok": r.ok})
        if r.cypher:
            self.cypher.append({"tool": name, "statement": r.cypher, "params": r.params or {}, "notes": r.notes})
        if r.subgraph:
            self.subgraph = merge_subgraphs(self.subgraph or {}, r.subgraph)
        if r.style_ops:
            self.style_ops.extend(r.style_ops)
        if r.permission:
            self.permissions.append(r.permission)
        # A turn's links are collected whole and de-duplicated by destination: asking for the
        # same report twice in one turn should still leave one button under the answer.
        for link in r.links:
            if link["href"] not in {l["href"] for l in self.links}:
                self.links.append(link)

    def final(self, answer: str) -> dict:
        ops = validate_ops(self.style_ops) if self.style_ops else []
        return {
            "type": "answer",
            "answer": answer,
            "cypher": self.cypher,
            "subgraph": self.subgraph,
            "style_ops": [o.model_dump(exclude_none=True) for o in ops],
            "legend": [l.model_dump() for l in derive_legend(ops)],
            "links": self.links,
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
                    await emit({"type": "delta", "text": delta.content})
                for tc in delta.tool_calls or []:
                    slot = tool_calls.setdefault(tc.index, {"id": tc.id or "", "name": "", "arguments": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            slot["name"] += tc.function.name
                        if tc.function.arguments:
                            slot["arguments"] += tc.function.arguments
        except Exception as e:
            msg = f"Model call failed: {e}"
            await emit({"type": "error", "message": msg})
            conv.messages.append({"role": "assistant", "content": msg})
            return acc.final(msg)

        if not tool_calls:
            conv.messages.append({"role": "assistant", "content": content})
            final = acc.final(content)
            await emit(final)
            return final

        calls = [tool_calls[i] for i in sorted(tool_calls)]
        conv.messages.append({
            "role": "assistant",
            "content": content or None,
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
                "type": "tool_result", "name": c["name"], "ok": result.ok, "cypher": result.cypher, "params": result.params,
                "summary": _summarise(result), "permission": result.permission, "notes": result.notes,
                "subgraph": result.subgraph, "style_ops": result.style_ops, "legend": result.legend, "links": result.links,
            })
            conv.messages.append({"role": "tool", "tool_call_id": c["id"] or f"call_{i}", "content": result.for_model()})

    msg = "Stopped after too many tool rounds; refine the question."
    conv.messages.append({"role": "assistant", "content": msg})
    final = acc.final(msg)
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
    if "scheme" in d:
        return f"{d['node_count']} node(s) coloured by {d['scheme']}"
    if "job_id" in d:
        return f"enrichment queued ({d['job_id']})"
    if "nodes" in d:
        return f"{len(d['nodes'])} node(s), {len(d.get('edges', []))} edge(s)"
    return "ok"


_ENTITY_HINT = re.compile(r"\b(?:of|for|owns?|about)\s+([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,4})")
# Asking for a report is worth catching without a key, because a report does not need one:
# its findings, paths, goods and mitigations are all computed from the graph, and the model
# only ever adds the summary paragraph on top.
_REPORT_INTENT = re.compile(r"\b(risk assessment|vendor profile|entity profile|"
                            r"(?:generate|write|make|produce|give me|create)\s+(?:me\s+)?(?:an?\s+)?report)\b", re.I)
_PROFILE_INTENT = re.compile(r"\b(vendor|entity|company|supplier)\s+profile\b", re.I)
# Colouring by a preset needs no model either — the scheme is the mapping, and without a key
# it is the only way to get the encoding at all, so it is worth matching on.
_SCHEME_INTENT = re.compile(r"\b(colou?r|shade|paint)\b[^.]{0,30}\bby\s+risk\b|\brisk\s+(?:gradient|heat\s?map)\b", re.I)


async def _template_only_turn(conv: Conversation, text: str, ctx: ToolContext, emit: Emit, acc: TurnAccumulator) -> dict:
    """No model key: degrade to template queries matched by intent, not an error."""
    if _REPORT_INTENT.search(text):
        return await _report_turn(conv, text, ctx, emit, acc)
    if _SCHEME_INTENT.search(text):
        return await _scheme_turn(conv, text, ctx, emit, acc)
    name = match_intent(text)
    if not name:
        msg = ("No OpenAI key is configured, so I can only run saved templates and write reports. Try: 'show sole-source suppliers', "
               "'foreign parent', 'shared directors', 'goods vs services', 'manufactures in CN', 'write a risk assessment', "
               "or add a key under Settings › Connectors.")
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


async def _report_turn(conv: Conversation, text: str, ctx: ToolContext, emit: Emit, acc: TurnAccumulator) -> dict:
    """Write a report with no model key. The document is a projection of the graph, so all
    that is lost is the summary paragraph — which the report says, rather than pretending."""
    kind = "entity_profile" if _PROFILE_INTENT.search(text) else "risk_assessment"
    args: dict[str, Any] = {"kind": kind}
    m = _ENTITY_HINT.search(text)
    if m:
        s = await dispatch(ctx, "search_entities", {"query": m.group(1), "kind": "entity", "limit": 1})
        if s.ok and s.data["results"]:
            args["subject_id"] = s.data["results"][0]["id"]
    await emit({"type": "tool_call", "name": "generate_report", "args": args})
    r = await dispatch(ctx, "generate_report", args)
    acc.absorb("generate_report", args, r)
    await emit({"type": "tool_result", "name": "generate_report", "ok": r.ok, "cypher": r.cypher, "params": r.params,
                "summary": _summarise(r), "subgraph": r.subgraph, "style_ops": r.style_ops, "legend": r.legend,
                "links": r.links, "notes": r.notes})
    if r.ok:
        d = r.data
        msg = (f"Wrote **{d['title']}** — {d.get('finding_count', 0)} finding(s), generated {d['generated_at']}. "
               "It is on the Reports tab and on the canvas beside its subject; regenerate it there once the graph "
               "has moved on. (No model key, so the report carries its computed summary rather than a written one.)")
    else:
        msg = f"Could not write that report: {r.data.get('error')}"
    conv.messages.append({"role": "assistant", "content": msg})
    final = acc.final(msg)
    await emit(final)
    return final


async def _scheme_turn(conv: Conversation, text: str, ctx: ToolContext, emit: Emit, acc: TurnAccumulator) -> dict:
    """Apply a preset colour scheme with no model key. The scheme *is* the reasoning, so
    nothing is lost here — the encoding is identical to the one a model would have asked for."""
    args = {"scheme": "risk"}
    await emit({"type": "tool_call", "name": "apply_color_scheme", "args": args})
    r = await dispatch(ctx, "apply_color_scheme", args)
    acc.absorb("apply_color_scheme", args, r)
    await emit({"type": "tool_result", "name": "apply_color_scheme", "ok": r.ok, "summary": _summarise(r),
                "style_ops": r.style_ops, "legend": r.legend, "links": r.links, "notes": r.notes})
    msg = f"Coloured the canvas by risk — {r.data['note']}" if r.ok else f"Could not colour by risk: {r.data.get('error')}"
    conv.messages.append({"role": "assistant", "content": msg})
    final = acc.final(msg)
    await emit(final)
    return final
