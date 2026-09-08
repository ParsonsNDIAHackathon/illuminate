from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from illuminate.llm import tasks
from illuminate.llm import chat
from illuminate.llm.chat import Conversation, TurnAccumulator
from illuminate.routers import graph
from illuminate.tools import handlers
from illuminate.tools.handlers import ToolContext, ToolResult, safe_tool_data, safe_tool_result
from illuminate.report import (
    IMMUTABLE_AI_FIELDS,
    approved_summary_findings,
    deterministic_summary,
    validate_model_summary,
)


def report_fixture() -> dict:
    return {
        "identity": {"id": "ent_acme", "name": "Acme", "simulated": True},
        "risk": {
            "score": 50,
            "note": "One family has no data.",
            "categories": [
                {
                    "id": "ownership",
                    "severity": "high",
                    "freshness": "current",
                    "factors": [{
                        "truth_status": "committed",
                        "evidence_refs": ["clm_parent", "edge_parent"],
                        "explanation": "Parent seated in GB",
                    }],
                },
                {
                    "id": "financial",
                    "severity": None,
                    "freshness": "missing",
                    "factors": [],
                },
            ],
        },
    }


def test_deterministic_summary_preserves_missing_data_and_immutable_boundary():
    summary = deterministic_summary(report_fixture(), "model_unavailable_or_invalid")

    assert summary["generated_by"] == "deterministic"
    assert summary["fallback_reason"] == "model_unavailable_or_invalid"
    assert "missing for 1 signal family" in summary["text"]
    assert "not treated as clear" in summary["text"]
    assert "simulated scenario entity" in summary["text"]
    assert summary["immutable_fields"] == list(IMMUTABLE_AI_FIELDS)
    assert summary["citations"] == ["clm_parent", "edge_parent"]


def test_model_summary_requires_only_approved_citations_and_fields():
    report = report_fixture()
    valid = validate_model_summary(
        {"finding_ids": ["finding:risk:ownership"]},
        report,
        "fast-model",
    )

    assert valid and valid["generated_by"] == "model-assisted"
    assert valid["selected_finding_ids"] == ["finding:risk:ownership"]
    assert valid["citations"] == ["clm_parent", "edge_parent"]
    assert validate_model_summary({"finding_ids": ["invented"]}, report, "fast-model") is None
    assert validate_model_summary({"finding_ids": ["finding:risk:financial"]}, report, "fast-model") is None
    assert validate_model_summary(
        {"finding_ids": ["finding:risk:ownership"], "composite": 0},
        report,
        "fast-model",
    ) is None


@pytest.mark.asyncio
async def test_summary_prompt_contains_only_approved_projection_and_falls_back(monkeypatch):
    captured: dict = {}
    report = report_fixture()
    report["restricted_raw_payload"] = {"Authorization": "Bearer secret-value"}

    async def fake_json_call(user, system, user_msg, *, strong=False):
        captured.update(system=system, payload=json.loads(user_msg))
        return {"finding_ids": ["not-approved"]}

    monkeypatch.setattr(tasks, "_json_call", fake_json_call)
    monkeypatch.setattr(tasks, "models", lambda user: ("strong", "fast"))

    result = await tasks.summarize_entity("local", report)

    assert result["generated_by"] == "deterministic"
    assert result["fallback_reason"] == "model_unavailable_or_invalid"
    serialized = json.dumps(captured["payload"])
    assert "secret-value" not in serialized
    assert "restricted_raw_payload" not in serialized
    assert set(captured["payload"]) == {"entity", "simulated", "findings"}
    assert all(set(f) == {"id", "family", "severity", "no_data"} for f in captured["payload"]["findings"])


@pytest.mark.asyncio
async def test_valid_model_summary_cannot_return_deterministic_fields(monkeypatch):
    report = report_fixture()

    async def fake_json_call(user, system, user_msg, *, strong=False):
        return {"finding_ids": ["finding:risk:ownership"]}

    monkeypatch.setattr(tasks, "_json_call", fake_json_call)
    monkeypatch.setattr(tasks, "models", lambda user: ("strong", "fast"))

    result = await tasks.summarize_entity("local", report)

    assert result["generated_by"] == "model-assisted"
    assert result["model"] == "fast"
    assert "composite" not in result
    assert result["immutable_fields"] == list(IMMUTABLE_AI_FIELDS)


def test_model_and_mcp_safe_projection_redacts_restricted_fields():
    source = {
        "name": "Acme",
        "Authorization": "Bearer sensitive",
        "nested": {"api_key": "sensitive", "finding": "approved"},
        "raw": {"safe_name": "still restricted"},
        "source_url": "https://evidence.test/doc?token=sensitive",
        "basic_auth_url": "https://user:password@evidence.test/doc",
        "comment": "Bearer sensitive-value",
    }

    safe = safe_tool_data(source)
    model_payload = json.loads(
        ToolResult(ok=True, data={**source, "unexpected": "must not pass"}).for_model("search_entities")
    )

    assert safe["Authorization"] == "[redacted]"
    assert safe["nested"] == {"api_key": "[redacted]", "finding": "approved"}
    assert safe["raw"] == "[redacted]"
    assert safe["source_url"] == "https://evidence.test/doc"
    assert safe["basic_auth_url"] == "https://evidence.test/doc"
    assert safe["comment"] == "[redacted]"
    assert model_payload["data"] == {}
    assert "sensitive" not in json.dumps(model_payload)
    assert "unexpected" not in json.dumps(model_payload)
    projected = safe_tool_result("search_entities", {"query": "Acme", "results": [], "raw": "restricted"})
    assert projected == {"query": "Acme", "results": []}
    custom_query = safe_tool_result(
        "run_cypher",
        {"classification": "READ", "row_count": 1, "rows": [{"innocent_alias": "session-secret"}]},
    )
    assert custom_query == {"classification": "READ", "row_count": 1}
    assert safe_tool_data("https://user:pass@[bad-host/doc") == "[redacted-invalid-url]"
    assert safe_tool_data("https://evidence.test:notaport/doc") == "[redacted-invalid-url]"


@pytest.mark.asyncio
async def test_report_transport_excludes_conflicting_legacy_risk(monkeypatch):
    report = report_fixture()
    report["identity"]["uei"] = "restricted-from-model-report"
    report["risk"].update({
        "composite": 100,
        "indicators": [{
            "family": "ownership",
            "severity": "high",
            "label": "Rejected foreign parent",
            "element_ids": ["rejected-parent-edge"],
        }],
        "contract_version": "uc11.vendor-risk.v1",
        "band": "not_assessed",
        "disposition": "complete_diligence",
        "confidence": 0,
        "completeness": 0,
        "freshness": "diligence_required",
        "diligence_flags": [],
    })
    report["risk"]["categories"][0].update(
        severity=None,
        factors=[],
    )
    report["summary"] = deterministic_summary(report)

    async def fake_build_report(entity_id, root_id=None):
        return report

    monkeypatch.setattr(handlers, "build_report", fake_build_report)

    result = await handlers.get_entity_report(
        ToolContext(source="mcp", root_id="root"),
        "ent_acme",
    )
    projected = safe_tool_result("get_entity_report", result.data)
    serialized = json.dumps(projected)

    assert set(projected) == {"identity", "risk", "summary"}
    assert set(projected["identity"]) == {"id", "name", "simulated"}
    assert "indicators" not in projected["risk"]
    assert "composite" not in projected["risk"]
    assert "Rejected foreign parent" not in serialized
    assert "rejected-parent-edge" not in serialized
    assert projected["risk"]["categories"][0]["severity"] is None


@pytest.mark.asyncio
async def test_http_summary_timeout_returns_and_persists_deterministic_fallback(monkeypatch):
    from illuminate.config import settings

    report = report_fixture()
    persisted = []

    async def fake_build_report(entity_id):
        return report

    async def slow_summary(user, rep):
        await asyncio.sleep(0.05)
        raise AssertionError("cancelled call should not complete")

    async def fake_persist(entity_id, summary):
        persisted.append((entity_id, summary))
        return False

    monkeypatch.setattr(graph, "build_report", fake_build_report)
    monkeypatch.setattr(tasks, "summarize_entity", slow_summary)
    monkeypatch.setattr(graph, "persist_summary", fake_persist)
    monkeypatch.setattr(settings, "summary_timeout_s", 0.001)

    result = await graph.regenerate_summary("ent_acme", "local")

    assert result["generated_by"] == "deterministic"
    assert result["fallback_reason"] == "model_timeout"
    assert persisted == [("ent_acme", result)]


def test_chat_report_answer_uses_guarded_summary_not_model_prose():
    acc = TurnAccumulator()
    acc.absorb(
        "get_entity_report",
        {"entity_id": "ent_acme"},
        ToolResult(
            ok=True,
            data={
                "summary": {
                    "text": "Deterministic guarded narrative.",
                    "citations": ["finding:risk:ownership", "ent_parent"],
                }
            },
        ),
    )

    final = acc.final("Model says the composite is zero.")

    assert "Deterministic guarded narrative." in final["answer"]
    assert "finding:risk:ownership" in final["answer"]
    assert "composite is zero" not in final["answer"]


@pytest.mark.asyncio
async def test_chat_report_stream_and_history_never_expose_model_prose(monkeypatch):
    class AsyncStream:
        def __init__(self, chunks):
            self.chunks = chunks

        def __aiter__(self):
            self.iterator = iter(self.chunks)
            return self

        async def __anext__(self):
            try:
                return next(self.iterator)
            except StopIteration:
                raise StopAsyncIteration

    tool_delta = SimpleNamespace(
        content="Unsafe pre-tool claim.",
        tool_calls=[
            SimpleNamespace(
                index=0,
                id="call_1",
                function=SimpleNamespace(name="get_entity_report", arguments='{"entity_id":"ent_acme"}'),
            ),
            SimpleNamespace(
                index=1,
                id="call_2",
                function=SimpleNamespace(name="expand_subgraph", arguments='{"entity_id":"ent_boeing"}'),
            ),
        ],
    )
    final_delta = SimpleNamespace(content="Composite is zero.", tool_calls=[])
    streams = [
        AsyncStream([SimpleNamespace(choices=[SimpleNamespace(delta=tool_delta)])]),
        AsyncStream([SimpleNamespace(choices=[SimpleNamespace(delta=final_delta)])]),
    ]

    class Completions:
        async def create(self, **kwargs):
            return streams.pop(0)

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    async def fake_dispatch(ctx, name, args):
        if name != "get_entity_report":
            return ToolResult(ok=True, data={"entity_id": args["entity_id"], "nodes": [], "edges": []})
        return ToolResult(
            ok=True,
            data={"summary": {"text": "Deterministic guarded narrative.", "citations": ["finding:risk:ownership"]}},
        )

    emitted = []

    async def emit(event):
        emitted.append(event)

    monkeypatch.setattr(chat, "client_for", lambda user: client)
    monkeypatch.setattr(chat, "models", lambda user: ("strong", "fast"))
    monkeypatch.setattr(chat, "openai_tools", lambda: [])
    monkeypatch.setattr(chat, "dispatch", fake_dispatch)
    monkeypatch.setattr(
        chat,
        "load_workspace",
        lambda: SimpleNamespace(root_id=None, root_label=None, layers={}),
    )

    conversation = Conversation(id="conv_test")
    final = await chat.run_turn(
        conversation,
        "Summarize Acme",
        ToolContext(source="chat", user="local"),
        emit,
    )

    serialized_events = json.dumps(emitted)
    assistant_history = [m.get("content") for m in conversation.messages if m["role"] == "assistant"]
    assert final["answer"].startswith("Deterministic guarded narrative.")
    assert "Unsafe pre-tool claim" not in serialized_events
    assert "Composite is zero" not in serialized_events
    assert assistant_history == [None, final["answer"]]

    streams.append(AsyncStream([SimpleNamespace(choices=[SimpleNamespace(delta=final_delta)])]))
    emitted.clear()
    second = await chat.run_turn(
        conversation,
        "Repeat that in two sentences",
        ToolContext(source="chat", user="local"),
        emit,
    )

    assert second["answer"] == chat.SAFE_NO_RESULT
    assert "Composite is zero" not in json.dumps(emitted)
    assert conversation.messages[-1]["content"] == second["answer"]

    streams.append(AsyncStream([SimpleNamespace(choices=[SimpleNamespace(delta=final_delta)])]))
    emitted.clear()
    third = await chat.run_turn(
        conversation,
        "Summarize Boeing again",
        ToolContext(source="chat", user="local"),
        emit,
    )

    assert third["answer"] == chat.SAFE_NO_RESULT
    assert "Acme" not in third["answer"]
    assert "Composite is zero" not in json.dumps(emitted)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prompt",
    ["List Acme findings", "Give an overview of Acme", "What are the implications?"],
)
async def test_chat_without_tool_results_always_fails_closed(monkeypatch, prompt):
    class AsyncStream:
        def __aiter__(self):
            self.done = False
            return self

        async def __anext__(self):
            if self.done:
                raise StopAsyncIteration
            self.done = True
            delta = SimpleNamespace(content="Acme has a zero score and is verified safe.", tool_calls=[])
            return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])

    class Completions:
        async def create(self, **kwargs):
            return AsyncStream()

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    emitted = []

    async def emit(event):
        emitted.append(event)

    monkeypatch.setattr(chat, "client_for", lambda user: client)
    monkeypatch.setattr(chat, "models", lambda user: ("strong", "fast"))
    monkeypatch.setattr(chat, "openai_tools", lambda: [])
    monkeypatch.setattr(
        chat,
        "load_workspace",
        lambda: SimpleNamespace(root_id=None, root_label=None, layers={}),
    )

    conversation = Conversation(id="conv_fail_closed")
    final = await chat.run_turn(
        conversation,
        prompt,
        ToolContext(source="chat", user="local"),
        emit,
    )

    assert final["answer"] == chat.SAFE_NO_RESULT
    assert conversation.messages[-1]["content"] == chat.SAFE_NO_RESULT
    assert "verified safe" not in json.dumps(emitted)


def test_malformed_report_evidence_url_falls_back_to_finding_identifier():
    report = report_fixture()
    report["risk"]["categories"][0]["source_url"] = "https://evidence.test:notaport/doc"

    findings = approved_summary_findings(report)

    assert findings[0]["evidence_ids"] == ["clm_parent", "edge_parent"]