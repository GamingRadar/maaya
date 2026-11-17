"""FastAPI Application entrypoint for MAAYA."""

from fastapi import FastAPI
from app.config import settings

app = FastAPI(
    title=settings.app.app_name,
    description="Offline-first personal AI companion API",
    version="0.1.0",
)


@app.get("/health")
def health_check() -> dict:
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "app": settings.app.app_name,
        "environment": settings.app.environment,
    }


def start() -> None:
    """Run application via uvicorn bound to local interface."""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.debug,
    )


if __name__ == "__main__":
    start()

