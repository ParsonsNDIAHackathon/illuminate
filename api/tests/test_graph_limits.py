import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from illuminate.routers.graph import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.mark.parametrize(
    "path",
    [
        "/api/graph/search?q=x&limit=0",
        "/api/graph/search?q=x&limit=51",
        "/api/graph/subgraph?entity_id=x&depth=0",
        "/api/graph/subgraph?entity_id=x&depth=7",
        "/api/entities?limit=0",
        "/api/entities?limit=1001",
        "/api/entities?offset=-1",
        "/api/entities?offset=100001",
        "/api/people?limit=0",
        "/api/people?limit=1001",
        "/api/artifacts?limit=0",
        "/api/artifacts?limit=1001",
    ],
)
def test_graph_routes_reject_unbounded_inputs(client, path):
    response = client.get(path)
    assert response.status_code == 422