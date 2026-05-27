"""Tests for scheduler."""


from app.core.router import Candidate
from app.core.scheduler import Scheduler


def _make_candidate(provider: str = "groq", label: str = "k1", model: str = "m1") -> Candidate:
    return Candidate(
        provider=provider,
        model=model,
        endpoint="https://api.example.com/v1",
        protocol="openai",
        auth_style="bearer",
        key="fake",
        key_label=label,
        context_window=128000,
    )


def test_round_robin() -> None:
    s = Scheduler()
    c1 = _make_candidate(label="k1")
    c2 = _make_candidate(label="k2")
    candidates = [c1, c2]

    picked1 = s.pick(candidates)
    picked2 = s.pick(candidates)
    assert picked1 is c1
    assert picked2 is c2


def test_cooldown_skip() -> None:
    s = Scheduler()
    c1 = _make_candidate(label="k1")
    c2 = _make_candidate(label="k2")
    candidates = [c1, c2]

    s.pick(candidates)
    s.report_failure(c1)

    picked = s.pick(candidates)
    assert picked is c2


def test_all_cooled_down() -> None:
    s = Scheduler()
    c1 = _make_candidate(label="k1")
    candidates = [c1]

    s.pick(candidates)
    s.report_failure(c1)

    picked = s.pick(candidates)
    assert picked is None
