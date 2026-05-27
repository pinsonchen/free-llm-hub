"""Tests for QuotaTracker."""

from pathlib import Path

from app.core.quota import QuotaTracker, Window


def _make_tracker(tmp_path: Path) -> QuotaTracker:
    db = str(tmp_path / "test.db")
    return QuotaTracker(db)


def test_record_and_check(tmp_path: Path) -> None:
    tracker = _make_tracker(tmp_path)
    tracker.record_request("groq", "k1", "llama-3.3-70b")
    tracker.record_tokens("groq", "k1", "llama-3.3-70b", 500)

    reqs, toks = tracker.get_usage("groq", "k1", "llama-3.3-70b", Window.MINUTE)
    assert reqs == 1
    assert toks == 500


def test_quota_ok_within_limits(tmp_path: Path) -> None:
    tracker = _make_tracker(tmp_path)
    tracker.record_request("groq", "k1", "m1")

    status = tracker.check_quota("groq", "k1", "m1", rpm=30, rpd=1000, tpm=6000, tpd=None)
    assert status.ok
    assert status.requests_remaining == 29


def test_quota_exhausted(tmp_path: Path) -> None:
    tracker = _make_tracker(tmp_path)
    for _ in range(30):
        tracker.record_request("groq", "k1", "m1")

    status = tracker.check_quota("groq", "k1", "m1", rpm=30, rpd=1000, tpm=None, tpd=None)
    assert not status.requests_ok
    assert not status.ok


def test_token_quota_exhausted(tmp_path: Path) -> None:
    tracker = _make_tracker(tmp_path)
    tracker.record_tokens("groq", "k1", "m1", 6000)

    status = tracker.check_quota("groq", "k1", "m1", rpm=None, rpd=None, tpm=6000, tpd=None)
    assert not status.tokens_ok
    assert not status.ok


def test_compact(tmp_path: Path) -> None:
    tracker = _make_tracker(tmp_path)
    tracker.record_request("groq", "k1", "m1")
    removed = tracker.compact(max_age_seconds=0)
    assert removed == 1

    reqs, _ = tracker.get_usage("groq", "k1", "m1", Window.MINUTE)
    assert reqs == 0


def test_no_limits_means_ok(tmp_path: Path) -> None:
    tracker = _make_tracker(tmp_path)
    for _ in range(1000):
        tracker.record_request("x", "k", "m")
    status = tracker.check_quota("x", "k", "m", rpm=None, rpd=None, tpm=None, tpd=None)
    assert status.ok
