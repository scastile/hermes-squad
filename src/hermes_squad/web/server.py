"""
FastAPI server for Hermes Squad web dashboard.

Serves the SPA dashboard, REST API, and image upload endpoint.
"""

import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from hermes_squad.web.routes import router

logger = logging.getLogger("hermes_squad.web")

STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Hermes Squad",
        description="Team coordination dashboard for Hermes Agent",
        version="0.1.0",
    )

    # API routes
    app.include_router(router)

    # Static files (frontend)
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Uploads directory
    from hermes_squad.db import get_db_path

    uploads_dir = get_db_path().parent / "uploads"
    uploads_dir.mkdir(exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

    # SPA catch-all — serve index.html for any non-API route.
    # The empty default lets "/" match here too, so no separate root() needed.
    @app.get("/{path:path}")
    async def spa(path: str = ""):
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            from fastapi.responses import FileResponse

            return FileResponse(str(index_path))
        return {"message": "Hermes Squad API", "docs": "/docs"}

    return app


# Module-level app for uvicorn (uvicorn hermes_squad.web.server:app)
app = create_app()


def start(port: int = 8093, host: str = "127.0.0.1"):
    """Start the web server."""
    logger.info("Starting Hermes Squad dashboard on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")
