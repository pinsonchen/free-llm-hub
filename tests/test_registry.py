"""Tests for registry loader."""

from pathlib import Path

from app.core.registry import load_registry


def test_load_seed_registry() -> None:
    entries = load_registry()
    assert len(entries) >= 4
    providers = {e.provider for e in entries}
    assert "groq" in providers
    assert "gemini" in providers
    assert "siliconflow" in providers


def test_load_empty_dir(tmp_path: Path) -> None:
    entries = load_registry(tmp_path)
    assert entries == []
