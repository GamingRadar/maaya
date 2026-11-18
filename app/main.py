"""Starlette Application entrypoint for MAAYA."""

from pathlib import Path
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from app.api.chat import chat_handler
from app.config import settings

# Base directory paths
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


async def health_check(request) -> JSONResponse:
    """Basic health check endpoint."""
    return JSONResponse(
        {
            "status": "healthy",
            "app": settings.app.app_name,
            "environment": settings.app.environment,
        }
    )


async def index_page(request) -> HTMLResponse:
    """Serve the mobile-first chat UI template."""
    index_file = TEMPLATES_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")
    return HTMLResponse(content)


routes = [
    Route("/", endpoint=index_page, methods=["GET"]),
    Route("/health", endpoint=health_check, methods=["GET"]),
    Route("/chat", endpoint=chat_handler, methods=["POST"]),
    Mount("/static", app=StaticFiles(directory=str(STATIC_DIR)), name="static"),
]

app = Starlette(
    debug=settings.app.debug,
    routes=routes,
)


def start() -> None:
    """Run application via uvicorn bound strictly to the configured local interface."""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.debug,
    )


if __name__ == "__main__":
    start()
