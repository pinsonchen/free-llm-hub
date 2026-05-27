"""Registry loader — reads registry/*.yaml, validates schema, exposes model entries."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_DIR = ROOT / "registry"
SCHEMA_PATH = REGISTRY_DIR / "schema.json"


class RateLimit(BaseModel):
    rpm: int | None = None
    rpd: int | None = None
    tpm: int | None = None
    tpd: int | None = None


class RegistryEntry(BaseModel):
    provider: str
    model: str
    endpoint: str
    protocol: str
    auth_style: str
    rate_limit: RateLimit
    context_window: int
    capabilities: list[str] = []
    notes: str | None = None
    signup_url: str | None = None
    docs_url: str | None = None
    last_verified: str | None = None


class _StringDateLoader(yaml.SafeLoader):
    pass


def _date_as_string(loader: yaml.Loader, node: yaml.Node) -> str:
    return loader.construct_scalar(node)


_StringDateLoader.add_constructor("tag:yaml.org,2002:timestamp", _date_as_string)


_registry: list[RegistryEntry] = []


def load_registry(directory: Path | None = None) -> list[RegistryEntry]:
    global _registry
    d = directory or REGISTRY_DIR
    entries: list[RegistryEntry] = []
    for path in sorted(d.glob("*.yaml")):
        docs = yaml.load(path.read_text(), Loader=_StringDateLoader) or []
        if not isinstance(docs, list):
            continue
        for raw in docs:
            try:
                entries.append(RegistryEntry.model_validate(raw))
            except Exception:
                continue
    _registry = entries
    return _registry


def get_registry() -> list[RegistryEntry]:
    if not _registry:
        return load_registry()
    return _registry


def get_models_for_provider(provider: str) -> list[RegistryEntry]:
    return [e for e in get_registry() if e.provider == provider]
