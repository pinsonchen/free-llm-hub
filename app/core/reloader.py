"""Hot reload watcher — polls config.yaml and registry/*.yaml for mtime changes."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from pathlib import Path

from app.core.config import load_config
from app.core.registry import REGISTRY_DIR, load_registry

logger = logging.getLogger(__name__)


class HotReloader:
    def __init__(
        self,
        config_path: Path | str = "config.yaml",
        registry_dir: Path | None = None,
        interval_seconds: float = 2.0,
    ) -> None:
        self._config_path = Path(config_path)
        self._registry_dir = registry_dir or REGISTRY_DIR
        self._interval = interval_seconds
        self._mtimes: dict[Path, float] = {}
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None

    def _snapshot(self) -> dict[Path, float]:
        snap: dict[Path, float] = {}
        if self._config_path.exists():
            snap[self._config_path] = self._config_path.stat().st_mtime
        if self._registry_dir.exists():
            for p in sorted(self._registry_dir.glob("*.yaml")):
                snap[p] = p.stat().st_mtime
        return snap

    def _detect_changes(self) -> tuple[bool, bool]:
        current = self._snapshot()
        config_changed = False
        registry_changed = False
        for path, mtime in current.items():
            prev = self._mtimes.get(path)
            if prev is None or prev != mtime:
                if path == self._config_path:
                    config_changed = True
                else:
                    registry_changed = True
        for path in self._mtimes:
            if path not in current:
                if path == self._config_path:
                    config_changed = True
                else:
                    registry_changed = True
        self._mtimes = current
        return config_changed, registry_changed

    def reload_now(self) -> tuple[bool, bool]:
        config_changed, registry_changed = self._detect_changes()
        if config_changed:
            try:
                load_config(self._config_path)
                logger.info("HotReloader: config reloaded")
            except Exception as e:
                logger.warning(f"HotReloader: config reload failed: {e}")
                config_changed = False
        if registry_changed:
            try:
                load_registry(self._registry_dir)
                logger.info("HotReloader: registry reloaded")
            except Exception as e:
                logger.warning(f"HotReloader: registry reload failed: {e}")
                registry_changed = False
        return config_changed, registry_changed

    async def _run_loop(self) -> None:
        assert self._stop_event is not None
        self._mtimes = self._snapshot()
        try:
            while not self._stop_event.is_set():
                try:
                    self.reload_now()
                except Exception as e:
                    logger.warning(f"HotReloader loop error: {e}")
                with suppress(TimeoutError):
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=self._interval
                    )
        except asyncio.CancelledError:
            return

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self._task


_reloader: HotReloader | None = None


def init_reloader(
    config_path: Path | str = "config.yaml",
    registry_dir: Path | None = None,
    interval_seconds: float = 2.0,
) -> HotReloader:
    global _reloader
    _reloader = HotReloader(
        config_path=config_path,
        registry_dir=registry_dir,
        interval_seconds=interval_seconds,
    )
    return _reloader


def get_reloader() -> HotReloader:
    global _reloader
    if _reloader is None:
        _reloader = HotReloader()
    return _reloader
