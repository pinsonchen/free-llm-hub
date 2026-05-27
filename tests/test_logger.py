"""Tests for decision logger."""

import json
import logging

from app.core.logger import log_decision
from app.core.router import Candidate


def _make_candidate() -> Candidate:
    return Candidate(
        provider="groq",
        model="llama-3.3-70b",
        endpoint="https://api.groq.com/openai/v1",
        protocol="openai",
        auth_style="bearer",
        key="fake",
        key_label="test-key",
        context_window=131072,
    )


def test_log_decision_success(caplog: logging.LogRecord) -> None:
    candidate = _make_candidate()
    with caplog.at_level(logging.INFO, logger="freellm.decisions"):
        rid = log_decision(None, candidate, "success", 123.4, total_tokens=50)

    assert rid
    assert len(caplog.records) == 1
    event = json.loads(caplog.records[0].message)
    assert event["outcome"] == "success"
    assert event["provider"] == "groq"
    assert event["total_tokens"] == 50
    assert event["latency_ms"] == 123.4


def test_log_decision_failure(caplog: logging.LogRecord) -> None:
    candidate = _make_candidate()
    with caplog.at_level(logging.INFO, logger="freellm.decisions"):
        log_decision("req123", candidate, "failure", 500.0, error="rate limited")

    event = json.loads(caplog.records[0].message)
    assert event["outcome"] == "failure"
    assert event["request_id"] == "req123"
    assert "rate limited" in event["error"]
