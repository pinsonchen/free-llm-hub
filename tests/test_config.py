"""Tests for config loader."""

from pathlib import Path
from textwrap import dedent

from app.core.config import HubConfig, load_config


def test_load_missing_config(tmp_path: Path) -> None:
    config = load_config(tmp_path / "nonexistent.yaml")
    assert isinstance(config, HubConfig)
    assert config.keys == []


def test_load_valid_config(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(dedent("""\
        auth:
          local_api_key: test123
        storage:
          backend: sqlite
          url: sqlite:///./test.db
        keys:
          - provider: groq
            label: my-groq
            key: gsk_test
            enabled: true
        policies:
          auto:
            prefer: [groq]
    """))
    config = load_config(cfg_file)
    assert len(config.keys) == 1
    assert config.keys[0].provider == "groq"
    assert config.keys[0].key.get_secret_value() == "gsk_test"
    assert "auto" in config.policies
    assert config.policies["auto"].prefer == ["groq"]
