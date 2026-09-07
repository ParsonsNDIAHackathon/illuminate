"""WebSocket chat in template-only mode (no model key) against live Neo4j."""
import json

import pytest
from fastapi.testclient import TestClient

from illuminate import db
from illuminate.config import load_workspace


@pytest.fixture
def client():
    from illuminate.main import app
    with TestClient(app) as c:
        if not c.get("/api/health").json().get("neo4j"):
            pytest.skip("neo4j not reachable")
        yield c


def test_template_only_turn(client):
    if not load_workspace().root_id:
        pytest.skip("no root seeded")
    with client.websocket_connect("/ws/chat?user=nokey-test-user") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["model_key"] is False
        ws.send_text(json.dumps({"type": "message", "text": "show sole-source suppliers"}))
        events = []
        for _ in range(20):
            ev = ws.receive_json()
            events.append(ev["type"])
            if ev["type"] == "answer":
                assert ev["cypher"], "cypher must be shown"
                assert ev["subgraph"]["nodes"], "subgraph returned"
                assert ev["legend"], "legend derived from style_ops"
                break
        assert "turn_start" in events and "tool_call" in events and "tool_result" in events and "answer" in events


def test_permission_flow_over_rest(client):
    r = client.post("/api/query/validate", json={"statement": "MATCH (e:Entity) DETACH DELETE e"})
    assert r.json()["classification"] == "DESTRUCTIVE"
    r = client.post("/api/query/validate", json={"statement": "CALL db.labels()"})
    assert r.json()["ok"] is False
