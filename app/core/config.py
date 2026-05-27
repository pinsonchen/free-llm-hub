"""Configuration schema and loader for free-llm-hub."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, SecretStr, field_validator


class RateLimitOverride(BaseModel):
    rpm: int | None = None
    rpd: int | None = None
    tpm: int | None = None
    tpd: int | None = None


class KeyConfig(BaseModel):
    provider: str
    label: str
    key: SecretStr
    enabled: bool = True
    override_limits: RateLimitOverride | None = None


class PolicyConfig(BaseModel):
    prefer: list[str] = []
    avoid: list[str] = []
    capabilities: list[str] = []
    min_context: int | None = None
    max_latency_ms: int | None = None


class StorageConfig(BaseModel):
    backend: str = "sqlite"
    url: str = "sqlite:///./hub.db"


class AuthConfig(BaseModel):
    local_api_key: str = ""
    admin_token: str = ""


class HubConfig(BaseModel):
    auth: AuthConfig = AuthConfig()
    storage: StorageConfig = StorageConfig()
    keys: list[KeyConfig] = []
    policies: dict[str, PolicyConfig] = {}

    @field_validator("keys", mode="before")
    @classmethod
    def filter_disabled(cls, v: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return v


_config: HubConfig | None = None


def load_config(path: Path | str = "config.yaml") -> HubConfig:
    global _config
    p = Path(path)
    if not p.exists():
        _config = HubConfig()
        return _config
    raw = yaml.safe_load(p.read_text()) or {}
    _config = HubConfig.model_validate(raw)
    return _config


def get_config() -> HubConfig:
    if _config is None:
        return load_config()
    return _config
