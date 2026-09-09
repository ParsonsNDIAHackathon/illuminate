from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, db, events
from .config import settings
from .enrichment.worker import worker
from .routers import chat, claims, connectors, enrichment, graph, permissions, query
from .routers import reports as reports_router
from .routers import risk as risk_router
from .routers import settings as settings_router
from .routers import styles as styles_router
from .schema import ensure_schema
from .tools.permissions import gate


from .mcp_server import build_server


class _MCPMount:
    """ASGI shim so the MCP transport (whose session manager runs once per
    lifespan) can be re-created each time the app starts — tests start it twice."""

    def __init__(self) -> None:
        self.app = None

    async def __call__(self, scope, receive, send):
        if self.app is None:
            await send({"type": "http.response.start", "status": 503, "headers": [(b"content-type", b"text/plain")]})
            await send({"type": "http.response.body", "body": b"MCP transport not started"})
            return
        await self.app(scope, receive, send)


_mcp_mount = _MCPMount()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await ensure_schema()
    except Exception as e:  # Neo4j may still be starting; endpoints will report via /api/health
        print(f"[illuminate] schema init deferred: {e}")
    gate.add_listener(chat.manager.broadcast)
    worker.add_listener(chat.manager.broadcast)
    events.add_listener(chat.manager.broadcast)
    worker.start()
    # MCP over streamable HTTP, same handlers (D1). Its session manager has its own lifespan; run it inside ours.
    server = build_server()
    _mcp_mount.app = server.streamable_http_app(streamable_http_path="/", stateless_http=True, json_response=True, host="0.0.0.0")
    async with server.session_manager.run():
        yield
    _mcp_mount.app = None
    await worker.stop()
    await db.close_driver()


app = FastAPI(title="Illuminate", version=__version__, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

for r in (graph.router, query.router, permissions.router, claims.router, enrichment.router, risk_router.router, reports_router.router, styles_router.router, connectors.router, settings_router.router, chat.router):
    app.include_router(r)

app.mount("/mcp", _mcp_mount)

# Serve the built frontend when present (docker image / single-process demo).
_dist = Path(__file__).resolve().parents[2] / "web" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        f = _dist / full_path
        if full_path and f.is_file():
            return FileResponse(f)
        return FileResponse(_dist / "index.html")


def run() -> None:
    import uvicorn
    uvicorn.run("illuminate.main:app", host="0.0.0.0", port=8000, reload=False)
