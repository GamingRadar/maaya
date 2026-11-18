"""Starlette Application entrypoint for MAAYA."""

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from app.api.chat import chat_handler
from app.config import settings


async def health_check(request) -> JSONResponse:
    """Basic health check endpoint."""
    return JSONResponse(
        {
            "status": "healthy",
            "app": settings.app.app_name,
            "environment": settings.app.environment,
        }
    )


routes = [
    Route("/health", endpoint=health_check, methods=["GET"]),
    Route("/chat", endpoint=chat_handler, methods=["POST"]),
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
