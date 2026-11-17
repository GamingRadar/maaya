"""Configuration loader for MAAYA.

Reads configuration from config.toml (if present) or environment variables,
falling back to default parameters suitable for the Snapdragon 710 target device.
"""

from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

# Try importing tomli (Python < 3.11) or tomllib (Python 3.11+)
try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore
    except ModuleNotFoundError:
        tomllib = None  # Fall back to pure defaults if toml library is not yet installed


class AppSettings(BaseModel):
    app_name: str = "MAAYA"
    environment: str = "development"
    debug: bool = False
    host: str = "127.0.0.1"
    port: int = 8000


class StorageSettings(BaseModel):
    database_path: str = "data/maaya.db"


class InferenceSettings(BaseModel):
    mode: str = "cli"  # "cli" or "server"
    llama_cli_path: str = "llama-cli"
    llama_server_url: str = "http://127.0.0.1:8080"
    model_path: str = "models/google_gemma-3-1b-it-Q4_K_M.gguf"
    threads: int = 4
    context_size: int = 2048
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9


class PersonalitySettings(BaseModel):
    name: str = "MAAYA"
    system_prompt: str = (
        "You are MAAYA, a thoughtful, observant, and supportive personal companion "
        "inspired by the collaborative dynamic between Sherlock Holmes and Dr. John Watson. "
        "You listen carefully, remember important ideas, help organize thoughts, and offer "
        "balanced, insightful perspectives."
    )


class Settings(BaseModel):
    app: AppSettings = Field(default_factory=AppSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    inference: InferenceSettings = Field(default_factory=InferenceSettings)
    personality: PersonalitySettings = Field(default_factory=PersonalitySettings)


def load_settings(config_path: Optional[Path] = None) -> Settings:
    """Load settings from a TOML configuration file if available, or return defaults."""
    if config_path is None:
        # Check current working directory or project root
        candidate = Path("config.toml")
        if candidate.is_file():
            config_path = candidate

    if config_path and config_path.is_file() and tomllib is not None:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
            return Settings(**data)

    return Settings()


# Global settings instance
settings = load_settings()

