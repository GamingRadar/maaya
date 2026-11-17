"""Basic smoke and configuration tests for MAAYA."""

from app.config import Settings, load_settings
from app.main import app


def test_default_settings():
    """Verify default settings align with target device requirements."""
    settings = Settings()
    assert settings.app.app_name == "MAAYA"
    assert settings.app.host == "127.0.0.1"
    assert settings.inference.mode in ["cli", "server"]
    assert settings.inference.threads == 4
    assert settings.inference.context_size == 2048


def test_load_settings_fallback():
    """Verify load_settings returns a valid Settings object."""
    cfg = load_settings()
    assert isinstance(cfg, Settings)
    assert cfg.app.host == "127.0.0.1"


def test_fastapi_app_metadata():
    """Verify FastAPI application instance is configured."""
    assert app.title == "MAAYA"
    assert app.version == "0.1.0"

