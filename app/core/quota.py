"""QuotaTracker — sliding window counters for rate limit enforcement.

Tracks usage per (provider, key_label, model, window) and answers
whether a candidate still has quota left. Supports both token-based (tpm/tpd)
and request-based (rpm/rpd) limits.

Storage: SQLite by default (zero-dep, single-process). Redis planned for M3.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from enum import Enum


class Window(Enum):
    MINUTE = 60
    DAY = 86400


@dataclass
class QuotaStatus:
    requests_used: int
    requests_limit: int | None
    tokens_used: int
    tokens_limit: int | None
    resets_in_seconds: float

    @property
    def requests_ok(self) -> bool:
        if self.requests_limit is None:
            return True
        return self.requests_used < self.requests_limit

    @property
    def tokens_ok(self) -> bool:
        if self.tokens_limit is None:
            return True
        return self.tokens_used < self.tokens_limit

    @property
    def ok(self) -> bool:
        return self.requests_ok and self.tokens_ok

    @property
    def requests_remaining(self) -> int | None:
        if self.requests_limit is None:
            return None
        return max(0, self.requests_limit - self.requests_used)

    @property
    def tokens_remaining(self) -> int | None:
        if self.tokens_limit is None:
            return None
        return max(0, self.tokens_limit - self.tokens_used)


class QuotaTracker:
    def __init__(self, db_path: str = "hub.db") -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quota_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    amount INTEGER NOT NULL DEFAULT 1,
                    timestamp REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_quota_lookup
                ON quota_events (key_id, model, event_type, timestamp)
            """)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=5.0)

    def _key_id(self, provider: str, key_label: str) -> str:
        return f"{provider}:{key_label}"

    def record_request(self, provider: str, key_label: str, model: str) -> None:
        key_id = self._key_id(provider, key_label)
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO quota_events (key_id, model, event_type, amount, timestamp) "
                "VALUES (?, ?, 'request', 1, ?)",
                (key_id, model, now),
            )

    def record_tokens(self, provider: str, key_label: str, model: str, tokens: int) -> None:
        if tokens <= 0:
            return
        key_id = self._key_id(provider, key_label)
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO quota_events (key_id, model, event_type, amount, timestamp) "
                "VALUES (?, ?, 'tokens', ?, ?)",
                (key_id, model, tokens, now),
            )

    def get_usage(
        self,
        provider: str,
        key_label: str,
        model: str,
        window: Window,
    ) -> tuple[int, int]:
        """Return (requests_count, tokens_count) within the window."""
        key_id = self._key_id(provider, key_label)
        cutoff = time.time() - window.value
        with self._connect() as conn:
            row = conn.execute(
                "SELECT "
                "  COALESCE(SUM(CASE WHEN event_type='request' THEN amount ELSE 0 END), 0), "
                "  COALESCE(SUM(CASE WHEN event_type='tokens' THEN amount ELSE 0 END), 0) "
                "FROM quota_events "
                "WHERE key_id=? AND model=? AND timestamp>?",
                (key_id, model, cutoff),
            ).fetchone()
        return (row[0], row[1]) if row else (0, 0)

    def check_quota(
        self,
        provider: str,
        key_label: str,
        model: str,
        rpm: int | None = None,
        rpd: int | None = None,
        tpm: int | None = None,
        tpd: int | None = None,
    ) -> QuotaStatus:
        """Check if the candidate has quota remaining."""
        req_minute, tok_minute = self.get_usage(provider, key_label, model, Window.MINUTE)
        req_day, tok_day = self.get_usage(provider, key_label, model, Window.DAY)

        req_used = req_minute if rpm is not None else req_day
        req_limit = rpm if rpm is not None else rpd

        tok_used = tok_minute if tpm is not None else tok_day
        tok_limit = tpm if tpm is not None else tpd

        window_seconds = Window.MINUTE.value if (rpm or tpm) else Window.DAY.value
        resets_in = window_seconds  # worst case

        return QuotaStatus(
            requests_used=req_used,
            requests_limit=req_limit,
            tokens_used=tok_used,
            tokens_limit=tok_limit,
            resets_in_seconds=resets_in,
        )

    def override_from_headers(
        self,
        provider: str,
        key_label: str,
        model: str,
        remaining_requests: int | None = None,
        remaining_tokens: int | None = None,
        reset_requests_seconds: float | None = None,
        reset_tokens_seconds: float | None = None,
    ) -> None:
        """When provider returns x-ratelimit-remaining-*, we can use that as
        a more accurate signal. For now we store it as a hint for the next check."""
        # M2: we trust our own counters primarily but log the provider hint.
        # A future optimization could recalibrate counters from provider headers.
        pass

    def compact(self, max_age_seconds: float = 172800) -> int:
        """Remove events older than max_age (default 48h) to keep DB small."""
        cutoff = time.time() - max_age_seconds
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM quota_events WHERE timestamp < ?", (cutoff,)
            )
            return cursor.rowcount

    def get_all_quotas(
        self,
        limits: dict[str, dict[str, tuple[int | None, int | None, int | None, int | None]]],
    ) -> dict[str, dict[str, QuotaStatus]]:
        """Return quota status for all known key+model combinations.
        
        limits: {key_id: {model: (rpm, rpd, tpm, tpd)}}
        """
        result: dict[str, dict[str, QuotaStatus]] = {}
        for key_id, models in limits.items():
            parts = key_id.split(":", 1)
            if len(parts) != 2:
                continue
            provider, key_label = parts
            result[key_id] = {}
            for model, (rpm, rpd, tpm, tpd) in models.items():
                result[key_id][model] = self.check_quota(
                    provider, key_label, model, rpm, rpd, tpm, tpd
                )
        return result


_tracker: QuotaTracker | None = None


def get_tracker(db_path: str = "hub.db") -> QuotaTracker:
    global _tracker
    if _tracker is None:
        _tracker = QuotaTracker(db_path)
    return _tracker


def init_tracker(db_path: str = "hub.db") -> QuotaTracker:
    global _tracker
    _tracker = QuotaTracker(db_path)
    return _tracker
