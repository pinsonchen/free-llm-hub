"""Tests for router."""

from app.core.config import HubConfig, KeyConfig, PolicyConfig
from app.core.registry import load_registry
from app.core.router import resolve_candidates, resolve_for_physical_model


def _make_config() -> HubConfig:
    return HubConfig(
        keys=[
            KeyConfig(provider="groq", label="groq-test", key="gsk_fake"),
            KeyConfig(provider="gemini", label="gemini-test", key="AIza_fake"),
        ],
        policies={
            "auto": PolicyConfig(prefer=["groq", "gemini"]),
            "coding-fast": PolicyConfig(prefer=["groq"], capabilities=["coding"]),
        },
    )


def test_resolve_auto() -> None:
    load_registry()
    cfg = _make_config()
    candidates = resolve_candidates("auto", cfg)
    assert len(candidates) > 0
    assert candidates[0].provider == "groq"


def test_resolve_coding_fast() -> None:
    load_registry()
    cfg = _make_config()
    candidates = resolve_candidates("coding-fast", cfg)
    assert len(candidates) > 0
    assert candidates[0].provider == "groq"


def test_resolve_physical_model() -> None:
    load_registry()
    cfg = _make_config()
    candidates = resolve_for_physical_model("gemini-2.5-flash", cfg)
    assert len(candidates) == 1
    assert candidates[0].provider == "gemini"
    assert candidates[0].model == "gemini-2.5-flash"
