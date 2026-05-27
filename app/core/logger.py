"""Structured decision logger — emits JSON logs for every routing decision."""

from __future__ import annotations

import json
import logging
import time
import uuid

from app.core.router import Candidate

logger = logging.getLogger("freellm.decisions")

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def log_decision(
    request_id: str | None,
    candidate: Candidate,
    outcome: str,
    latency_ms: float,
    total_tokens: int = 0,
    error: str | None = None,
) -> str:
    """Log a routing decision as structured JSON. Returns the request_id."""
    rid = request_id or uuid.uuid4().hex[:12]
    event = {
        "event": "decision",
        "request_id": rid,
        "timestamp": time.time(),
        "provider": candidate.provider,
        "model": candidate.model,
        "key_label": candidate.key_label,
        "outcome": outcome,
        "latency_ms": round(latency_ms, 1),
        "total_tokens": total_tokens,
    }
    if error:
        event["error"] = error[:200]

    logger.info(json.dumps(event, ensure_ascii=False))
    return rid
