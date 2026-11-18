"""Smoke, configuration, and endpoint tests for MAAYA."""

from pathlib import Path
from starlette.testclient import TestClient

from app.config import (
    AppSettings,
    InferenceSettings,
    PersonalitySettings,
    Settings,
    StorageSettings,
    load_settings,
)
from app.main import app


def test_default_settings():
    """Verify default settings align with target device requirements."""
    settings = Settings()
    assert settings.app.app_name == "MAAYA"
    assert settings.app.host == "127.0.0.1"
    assert settings.app.port == 8000
    assert settings.inference.mode in ["cli", "server"]
    assert settings.inference.threads == 2
    assert settings.inference.context_size == 512
    assert settings.inference.max_tokens == 256
    assert settings.inference.timeout == 180.0
    assert settings.app.max_message_length == 4096
    assert "Watson" in settings.personality.system_prompt


def test_load_settings_fallback():
    """Verify load_settings returns a valid Settings object when no file is present."""
    cfg = load_settings(Path("non_existent_file.toml"))
    assert isinstance(cfg, Settings)
    assert cfg.app.host == "127.0.0.1"


def test_load_settings_from_toml(tmp_path):
    """Verify load_settings correctly loads and filters values from a TOML file."""
    toml_content = """
    [app]
    app_name = "MAAYA-TEST"
    host = "127.0.0.1"
    port = 9000
    debug = true
    max_message_length = 1000
    unknown_field = "ignore_me"

    [inference]
    threads = 4
    context_size = 1024
    timeout = 30.0
    """
    cfg_file = tmp_path / "config.test.toml"
    cfg_file.write_text(toml_content, encoding="utf-8")

    cfg = load_settings(cfg_file)
    assert cfg.app.app_name == "MAAYA-TEST"
    assert cfg.app.port == 9000
    assert cfg.app.debug is True
    assert cfg.app.max_message_length == 1000
    assert cfg.inference.threads == 4
    assert cfg.inference.context_size == 1024
    assert cfg.inference.timeout == 30.0
    # Default preserved for fields not specified
    assert cfg.storage.database_path == "data/maaya.db"


def test_health_endpoint():
    """Verify the /health endpoint returns HTTP 200 with application status."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == "MAAYA"
    assert "environment" in data
