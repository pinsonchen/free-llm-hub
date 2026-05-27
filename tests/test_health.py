"""Tests for HealthProbe."""

from app.core.health import HealthProbe


def test_initial_state_unknown() -> None:
    probe = HealthProbe()
    state = probe.get_state("groq", "any")
    assert state.status == "unknown"
    assert probe.is_healthy("groq", "any")  # unknown is treated as healthy


def test_record_healthy() -> None:
    probe = HealthProbe()
    probe._record("groq", "k1", "healthy", 123.4, None)

    state = probe.get_state("groq", "k1")
    assert state.status == "healthy"
    assert state.last_latency_ms == 123.4
    assert state.consecutive_failures == 0
    assert state.last_error is None


def test_record_failure_then_recovery() -> None:
    probe = HealthProbe()
    probe._record("groq", "k1", "down", 500.0, "boom")

    state = probe.get_state("groq", "k1")
    assert state.status == "degraded"
    assert state.consecutive_failures == 1

    probe._record("groq", "k1", "down", 500.0, "still broken")
    probe._record("groq", "k1", "down", 500.0, "still broken")
    state = probe.get_state("groq", "k1")
    assert state.status == "down"
    assert state.consecutive_failures == 3

    probe._record("groq", "k1", "healthy", 100.0, None)
    state = probe.get_state("groq", "k1")
    assert state.status == "healthy"
    assert state.consecutive_failures == 0


def test_all_states() -> None:
    probe = HealthProbe()
    probe._record("groq", "k1", "healthy", 100.0, None)
    probe._record("gemini", "k2", "down", 500.0, "err")

    all_states = probe.all_states()
    assert "groq:k1" in all_states
    assert "gemini:k2" in all_states
    assert all_states["groq:k1"].status == "healthy"
