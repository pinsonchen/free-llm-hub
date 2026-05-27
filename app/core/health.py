"""HealthProbe — background task that periodically pings configured keys.

Tracks per-(provider, key_label) status:
- last_check_at, last_latency_ms
- consecutive_failures
- status: "healthy" | "degraded" | "down" | "unknown"

The probe is intentionally cheap (max_tokens=1) and respects QuotaTracker —
probes themselves count against quota, so we throttle to avoid burning budget.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass
from typing import Literal

from app.core.config import get_config
from app.core.logger import logger
from app.core.quota import get_tracker
from app.core.registry import get_models_for_provider
from app.core.router import Candidate

HealthStatus = Literal["healthy", "degraded", "down", "unknown"]


@dataclass
class HealthState:
    status: HealthStatus = "unknown"
    last_check_at: float = 0.0
    last_latency_ms: float | None = None
    consecutive_failures: int = 0
    last_error: str | None = None


class HealthProbe:
    def __init__(self, interval_seconds: float = 300.0) -> None:
        self._interval = interval_seconds
        self._states: dict[str, HealthState] = {}
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None

    def _state_key(self, provider: str, key_label: str) -> str:
        return f"{provider}:{key_label}"

    def get_state(self, provider: str, key_label: str) -> HealthState:
        return self._states.get(self._state_key(provider, key_label), HealthState())

    def all_states(self) -> dict[str, HealthState]:
        return dict(self._states)

    def is_healthy(self, provider: str, key_label: str) -> bool:
        state = self.get_state(provider, key_label)
        return state.status in ("healthy", "unknown")

    async def probe_once(self) -> None:
        cfg = get_config()
        for kc in cfg.keys:
            if not kc.enabled:
                continue

            models = get_models_for_provider(kc.provider)
            if not models:
                self._record(kc.provider, kc.label, "unknown", None, "no model in registry")
                continue

            entry = models[0]
            tracker = get_tracker()
            quota = tracker.check_quota(
                kc.provider,
                kc.label,
                entry.model,
                rpm=entry.rate_limit.rpm,
                rpd=entry.rate_limit.rpd,
                tpm=entry.rate_limit.tpm,
                tpd=entry.rate_limit.tpd,
            )
            if not quota.ok:
                continue  # avoid burning quota when nearly exhausted

            candidate = Candidate(
                provider=kc.provider,
                model=entry.model,
                endpoint=entry.endpoint,
                protocol=entry.protocol,
                auth_style=entry.auth_style,
                key=kc.key.get_secret_value(),
                key_label=kc.label,
                context_window=entry.context_window,
                rate_limit_rpm=entry.rate_limit.rpm,
                rate_limit_rpd=entry.rate_limit.rpd,
                rate_limit_tpm=entry.rate_limit.tpm,
                rate_limit_tpd=entry.rate_limit.tpd,
            )
            await self._probe_candidate(candidate)

    async def _probe_candidate(self, candidate: Candidate) -> None:
        from app.providers.litellm_provider import call_provider

        start = time.time()
        try:
            await call_provider(
                candidate,
                [{"role": "user", "content": "hi"}],
                stream=False,
                max_tokens=1,
            )
            latency = (time.time() - start) * 1000
            self._record(candidate.provider, candidate.key_label, "healthy", latency, None)
        except Exception as e:
            latency = (time.time() - start) * 1000
            self._record(
                candidate.provider, candidate.key_label, "down", latency, str(e)[:200]
            )

    def _record(
        self,
        provider: str,
        key_label: str,
        status: HealthStatus,
        latency_ms: float | None,
        error: str | None,
    ) -> None:
        sk = self._state_key(provider, key_label)
        state = self._states.setdefault(sk, HealthState())
        state.last_check_at = time.time()
        state.last_latency_ms = latency_ms
        state.last_error = error

        if status == "healthy":
            state.consecutive_failures = 0
            state.status = "healthy"
        elif status == "down":
            state.consecutive_failures += 1
            state.status = "degraded" if state.consecutive_failures < 3 else "down"
        else:
            state.status = status

    async def _run_loop(self) -> None:
        assert self._stop_event is not None
        try:
            while not self._stop_event.is_set():
                try:
                    await self.probe_once()
                except Exception as e:
                    logger.warning(f"HealthProbe loop error: {e}")
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval)
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
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None


_probe: HealthProbe | None = None


def get_probe() -> HealthProbe:
    global _probe
    if _probe is None:
        _probe = HealthProbe()
    return _probe


def init_probe(interval_seconds: float = 300.0) -> HealthProbe:
    global _probe
    _probe = HealthProbe(interval_seconds=interval_seconds)
    return _probe
