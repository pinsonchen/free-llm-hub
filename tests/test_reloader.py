"""Tests for app.core.reloader (HotReloader)."""

from __future__ import annotations

import time
from pathlib import Path

from app.core.reloader import HotReloader


def test_detect_no_change(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    reg_dir = tmp_path / "registry"
    reg_dir.mkdir()
    cfg.write_text("keys: []")
    (reg_dir / "test.yaml").write_text("[]")

    reloader = HotReloader(config_path=cfg, registry_dir=reg_dir)
    reloader._mtimes = reloader._snapshot()

    config_changed, registry_changed = reloader._detect_changes()
    assert not config_changed
    assert not registry_changed


def test_detect_config_change(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    reg_dir = tmp_path / "registry"
    reg_dir.mkdir()
    cfg.write_text("keys: []")

    reloader = HotReloader(config_path=cfg, registry_dir=reg_dir)
    reloader._mtimes = reloader._snapshot()

    time.sleep(0.05)
    cfg.write_text("keys: [changed]")

    config_changed, registry_changed = reloader._detect_changes()
    assert config_changed
    assert not registry_changed


def test_detect_registry_change(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    reg_dir = tmp_path / "registry"
    reg_dir.mkdir()
    cfg.write_text("keys: []")
    f = reg_dir / "groq.yaml"
    f.write_text("[]")

    reloader = HotReloader(config_path=cfg, registry_dir=reg_dir)
    reloader._mtimes = reloader._snapshot()

    time.sleep(0.05)
    f.write_text("[{changed: true}]")

    config_changed, registry_changed = reloader._detect_changes()
    assert not config_changed
    assert registry_changed


def test_detect_new_registry_file(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    reg_dir = tmp_path / "registry"
    reg_dir.mkdir()
    cfg.write_text("keys: []")

    reloader = HotReloader(config_path=cfg, registry_dir=reg_dir)
    reloader._mtimes = reloader._snapshot()

    (reg_dir / "new_provider.yaml").write_text("[]")

    config_changed, registry_changed = reloader._detect_changes()
    assert not config_changed
    assert registry_changed
