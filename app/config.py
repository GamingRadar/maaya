"""Configuration loader for MAAYA.

Reads configuration from config.toml (if present) or environment variables,
falling back to default parameters suitable for the Snapdragon 710 target device.

Uses Python standard library dataclasses and tomllib (with tomli fallback for <3.11)
to avoid heavyweight C/Rust extensions (such as pydantic-core) on Android / Termux.
"""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any, Dict, Optional

# Use standard library tomllib (Python 3.11+) or tomli fallback (Python 3.10)
try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore
    except ModuleNotFoundError:
        tomllib = None  # type: ignore


@dataclass
class AppSettings:
    app_name: str = "MAAYA"
    environment: str = "development"
    debug: bool = False
    host: str = "127.0.0.1"
    port: int = 8000
    max_message_length: int = 4096


@dataclass
class StorageSettings:
    database_path: str = "data/maaya.db"


@dataclass
class InferenceSettings:
    mode: str = "cli"  # "cli" or "server"
    llama_cli_path: str = "llama-cli"
    llama_server_url: str = "http://127.0.0.1:8080"
    model_name: str = "gemma-3-1b"
    # Default model path pointing to target device storage layout (~/MAAYA/models/)
    model_path: str = os.path.expanduser("~/MAAYA/models/google_gemma-3-1b-it-Q4_K_M.gguf")
    threads: int = 2
    context_size: int = 512
    max_tokens: int = 256
    timeout: float = 180.0
    temperature: float = 0.7
    top_p: float = 0.9


@dataclass
class PersonalitySettings:
    name: str = "MAAYA"
    system_prompt: str = (
        "You are MAAYA, a thoughtful, observant, and supportive personal companion "
        "inspired by the collaborative dynamic between Sherlock Holmes and Dr. John Watson. "
        "You listen carefully, remember important ideas, help organize thoughts, and offer "
        "balanced, insightful perspectives."
    )


@dataclass
class Settings:
    app: AppSettings = field(default_factory=AppSettings)
    storage: StorageSettings = field(default_factory=StorageSettings)
    inference: InferenceSettings = field(default_factory=InferenceSettings)
    personality: PersonalitySettings = field(default_factory=PersonalitySettings)


def _filter_dataclass_fields(cls: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract only keys that match the dataclass fields, ignoring unknown extra keys."""
    if not isinstance(data, dict):
        return {}
    valid_keys = cls.__dataclass_fields__.keys()
    return {k: v for k, v in data.items() if k in valid_keys}


def load_settings(config_path: Optional[Path] = None) -> Settings:
    """Load settings from a TOML configuration file if available, or return defaults."""
    if config_path is None:
        candidate = Path("config.toml")
        if candidate.is_file():
            config_path = candidate

    if config_path and Path(config_path).is_file() and tomllib is not None:
        with open(config_path, "rb") as f:
            raw_data = tomllib.load(f)

        app_data = _filter_dataclass_fields(AppSettings, raw_data.get("app", {}))
        storage_data = _filter_dataclass_fields(StorageSettings, raw_data.get("storage", {}))
        inference_data = _filter_dataclass_fields(InferenceSettings, raw_data.get("inference", {}))
        personality_data = _filter_dataclass_fields(PersonalitySettings, raw_data.get("personality", {}))

        return Settings(
            app=AppSettings(**app_data),
            storage=StorageSettings(**storage_data),
            inference=InferenceSettings(**inference_data),
            personality=PersonalitySettings(**personality_data),
        )

    return Settings()


# Global settings instance
settings = load_settings()
