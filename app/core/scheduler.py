"""Scheduler — picks the best candidate with round-robin, cooldown awareness, and quota checks."""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.core.router import Candidate


@dataclass
class CooldownEntry:
    until: float = 0.0
    consecutive_failures: int = 0

    BACKOFF_STEPS = [10, 30, 60, 120, 300]

    def is_cooled_down(self) -> bool:
        return time.time() >= self.until

    def record_failure(self) -> None:
        idx = min(self.consecutive_failures, len(self.BACKOFF_STEPS) - 1)
        backoff = self.BACKOFF_STEPS[idx]
        self.until = time.time() + backoff
        self.consecutive_failures += 1

    def record_success(self) -> None:
        self.until = 0.0
        self.consecutive_failures = 0


class Scheduler:
    def __init__(self) -> None:
        self._rr_index: int = 0
        self._cooldowns: dict[str, CooldownEntry] = {}

    def _cooldown_key(self, c: Candidate) -> str:
        return f"{c.provider}:{c.key_label}:{c.model}"

    def pick(self, candidates: list[Candidate]) -> Candidate | None:
        if not candidates:
            return None

        n = len(candidates)
        for offset in range(n):
            idx = (self._rr_index + offset) % n
            candidate = candidates[idx]
            ck = self._cooldown_key(candidate)
            cd = self._cooldowns.get(ck)
            if cd and not cd.is_cooled_down():
                continue
            self._rr_index = (idx + 1) % n
            return candidate

        return None

    def report_success(self, candidate: Candidate) -> None:
        ck = self._cooldown_key(candidate)
        cd = self._cooldowns.get(ck)
        if cd:
            cd.record_success()

    def report_failure(self, candidate: Candidate) -> None:
        ck = self._cooldown_key(candidate)
        if ck not in self._cooldowns:
            self._cooldowns[ck] = CooldownEntry()
        self._cooldowns[ck].record_failure()

    def get_next_available_time(self) -> float | None:
        if not self._cooldowns:
            return None
        times = [cd.until for cd in self._cooldowns.values() if cd.until > time.time()]
        return min(times) if times else None


scheduler = Scheduler()
