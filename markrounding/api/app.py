"""FastAPI application factory.

The backend owns the /api prefix (edge-Caddy proxies straight through) and
serves the built Vue SPA from frontend/dist when present — one container
in production, mirroring gribranker.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from .. import db
from .. import matomo
from ..config import DEFAULT_DB_PATH
from .admin import auth_router
from .admin import router as admin_router
from .public import router as public_router
from .report import router as report_router

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def create_app(db_path: Path | str = DEFAULT_DB_PATH) -> FastAPI:
    app = FastAPI(title="Mark-rounding", version="0.1.0")
    app.state.db_path = Path(db_path)

    conn = db.connect(app.state.db_path)
    try:
        db.init_db(conn)
    finally:
        conn.close()

    @app.get("/api/status", include_in_schema=False)
    def status() -> dict:
        return {"status": "ok"}

    @app.middleware("http")
    async def matomo_middleware(request, call_next):
        response = await call_next(request)
        matomo.track_request(request, response.status_code)
        return response

    app.include_router(public_router)
    app.include_router(report_router)
    app.include_router(auth_router)
    app.include_router(admin_router)

    if FRONTEND_DIST.is_dir():
        index = FRONTEND_DIST / "index.html"

        app.mount(
            "/assets",
            StaticFiles(directory=FRONTEND_DIST / "assets"),
            name="assets",
        )

        # SPA fallback: any non-API path serves index.html so vue-router
        # can deep-link (/regatta/x, /report/y, /admin).
        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            candidate = FRONTEND_DIST / path
            if path and ".." not in path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(index)

    return app
