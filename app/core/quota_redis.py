"""Redis backend for QuotaTracker — optional multi-process variant.

Uses sorted sets (ZADD/ZRANGEBYSCORE) keyed by (key_id, model, event_type)
with the score = unix timestamp. Sliding window queries are O(log N + K).

Activate via config:
    storage:
      backend: redis
      url: redis://127.0.0.1:6379/0
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from app.core.quota import QuotaStatus, Window

try:
    import redis  # type: ignore
except ImportError:
    redis = None  # type: ignore


@dataclass
class _RedisConfig:
    url: str


class RedisQuotaTracker:
    def __init__(self, url: str = "redis://127.0.0.1:6379/0") -> None:
        if redis is None:
            raise RuntimeError(
                "redis package is not installed. Install with: pip install redis"
            )
        self._client = redis.Redis.from_url(url, decode_responses=True)
        # ping to fail fast on misconfig
        self._client.ping()

    def _zkey(self, provider: str, key_label: str, model: str, event_type: str) -> str:
        return f"freellm:quota:{provider}:{key_label}:{model}:{event_type}"

    def record_request(self, provider: str, key_label: str, model: str) -> None:
        now = time.time()
        member = f"req:{uuid.uuid4().hex}"
        zkey = self._zkey(provider, key_label, model, "request")
        with self._client.pipeline() as pipe:
            pipe.zadd(zkey, {member: now})
            pipe.zremrangebyscore(zkey, 0, now - Window.DAY.value)
            pipe.expire(zkey, Window.DAY.value + 60)
            pipe.execute()

    def record_tokens(self, provider: str, key_label: str, model: str, tokens: int) -> None:
        if tokens <= 0:
            return
        now = time.time()
        member = f"tok:{tokens}:{uuid.uuid4().hex}"
        zkey = self._zkey(provider, key_label, model, "tokens")
        with self._client.pipeline() as pipe:
            pipe.zadd(zkey, {member: now})
            pipe.zremrangebyscore(zkey, 0, now - Window.DAY.value)
            pipe.expire(zkey, Window.DAY.value + 60)
            pipe.execute()

    def get_usage(
        self,
        provider: str,
        key_label: str,
        model: str,
        window: Window,
    ) -> tuple[int, int]:
        now = time.time()
        cutoff = now - window.value

        req_zkey = self._zkey(provider, key_label, model, "request")
        tok_zkey = self._zkey(provider, key_label, model, "tokens")

        req_count = self._client.zcount(req_zkey, cutoff, now)

        token_members: list[str] = self._client.zrangebyscore(tok_zkey, cutoff, now)
        tokens_total = 0
        for m in token_members:
            try:
                parts = m.split(":")
                if len(parts) >= 2:
                    tokens_total += int(parts[1])
            except (ValueError, IndexError):
                continue

        return int(req_count), tokens_total

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
        req_minute, tok_minute = self.get_usage(provider, key_label, model, Window.MINUTE)
        req_day, tok_day = self.get_usage(provider, key_label, model, Window.DAY)

        req_used = req_minute if rpm is not None else req_day
        req_limit = rpm if rpm is not None else rpd

        tok_used = tok_minute if tpm is not None else tok_day
        tok_limit = tpm if tpm is not None else tpd

        window_seconds = Window.MINUTE.value if (rpm or tpm) else Window.DAY.value

        return QuotaStatus(
            requests_used=req_used,
            requests_limit=req_limit,
            tokens_used=tok_used,
            tokens_limit=tok_limit,
            resets_in_seconds=window_seconds,
        )

    def compact(self, max_age_seconds: float = 172800) -> int:
        """Redis auto-expires; nothing to do beyond returning 0."""
        return 0
