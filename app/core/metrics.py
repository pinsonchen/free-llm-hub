"""Lightweight Prometheus-format metrics — no external dependency.

Tracks counters and last-observed values to render at /metrics.
"""

from __future__ import annotations

import threading
from collections import defaultdict


class _Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple[str, frozenset], int] = defaultdict(int)
        self._gauges: dict[tuple[str, frozenset], float] = {}
        self._tokens: dict[tuple[str, frozenset], int] = defaultdict(int)

    def inc_request(self, provider: str, model: str, outcome: str) -> None:
        labels = frozenset({
            ("provider", provider),
            ("model", model),
            ("outcome", outcome),
        })
        with self._lock:
            self._counters[("freellm_requests_total", labels)] += 1

    def add_tokens(self, provider: str, model: str, tokens: int) -> None:
        if tokens <= 0:
            return
        labels = frozenset({("provider", provider), ("model", model)})
        with self._lock:
            self._tokens[("freellm_tokens_total", labels)] += tokens

    def set_gauge(self, name: str, value: float, **labels: str) -> None:
        lkey = frozenset(labels.items())
        with self._lock:
            self._gauges[(name, lkey)] = value

    def render(self) -> str:
        lines: list[str] = []

        emitted: set[str] = set()

        def header(name: str, mtype: str) -> None:
            if name in emitted:
                return
            emitted.add(name)
            lines.append(f"# TYPE {name} {mtype}")

        with self._lock:
            for (name, labels), value in self._counters.items():
                header(name, "counter")
                lines.append(_fmt(name, labels, value))

            for (name, labels), value in self._tokens.items():
                header(name, "counter")
                lines.append(_fmt(name, labels, value))

            for (name, labels), value in self._gauges.items():
                header(name, "gauge")
                lines.append(_fmt(name, labels, value))

        return "\n".join(lines) + "\n"


def _fmt(name: str, labels: frozenset, value: float) -> str:
    if not labels:
        return f"{name} {value}"
    parts = ",".join(f'{k}="{v}"' for k, v in sorted(labels))
    return f"{name}{{{parts}}} {value}"


metrics = _Metrics()
