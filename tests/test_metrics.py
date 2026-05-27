"""Tests for metrics module."""

from app.core.metrics import _Metrics


def test_request_counter() -> None:
    m = _Metrics()
    m.inc_request("groq", "llama-3.3-70b", "success")
    m.inc_request("groq", "llama-3.3-70b", "success")
    m.inc_request("groq", "llama-3.3-70b", "failure")

    out = m.render()
    assert "freellm_requests_total" in out
    assert 'provider="groq"' in out
    assert 'outcome="success"' in out
    assert 'outcome="failure"' in out


def test_tokens_counter() -> None:
    m = _Metrics()
    m.add_tokens("gemini", "gemini-2.5-flash", 100)
    m.add_tokens("gemini", "gemini-2.5-flash", 250)

    out = m.render()
    assert "freellm_tokens_total" in out
    assert "350" in out


def test_zero_tokens_ignored() -> None:
    m = _Metrics()
    m.add_tokens("groq", "m1", 0)
    out = m.render()
    assert "freellm_tokens_total" not in out


def test_render_format() -> None:
    m = _Metrics()
    m.inc_request("groq", "m1", "success")
    out = m.render()
    assert "# TYPE freellm_requests_total counter" in out
