"""Ranking tests — mocked Anthropic client, no network."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from src.db import Posting, get_engine
from src.normalize import normalize
from src.rank import rank_postings
from src.sources.base import RawPosting

PROFILE_PATH = Path("config/profile.yaml")


def _posting(**overrides: Any) -> RawPosting:
    defaults: dict[str, Any] = dict(
        source="greenhouse",
        company="Acme",
        company_slug="acme",
        title="Senior ML Engineer",
        location="Tel Aviv",
        url="https://example.com/1",
        description="We build ML systems. Requires Python and PyTorch. Senior level.",
        remote=False,
        raw={},
    )
    return RawPosting(**(defaults | overrides))


def _fake_client(
    score: int = 8,
    level: str = "match",
    rationale: str = "Strong domain fit.",
    dealbreakers: list[str] | None = None,
) -> MagicMock:
    """Return a mock Anthropic client whose messages.create returns a tool_use block."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = "score_posting"
    block.input = {
        "relevance_score": score,
        "level_match": level,
        "one_line_rationale": rationale,
        "dealbreakers_hit": dealbreakers or [],
    }
    resp = MagicMock()
    resp.content = [block]
    client = MagicMock()
    client.messages.create.return_value = resp
    return client


def test_rank_advances_to_ranked(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "test.db")
    normalize([_posting()], engine=engine)
    n = rank_postings(engine=engine, profile_path=PROFILE_PATH, client=_fake_client(score=8))
    assert n == 1
    with Session(engine) as s:
        p = s.query(Posting).first()
        assert p is not None
        assert p.status == "ranked"
        assert p.relevance_score == 8
        assert p.level_match == "match"


def test_rank_below_threshold_skipped(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "test.db")
    normalize([_posting()], engine=engine)
    n = rank_postings(engine=engine, profile_path=PROFILE_PATH, client=_fake_client(score=3))
    assert n == 1
    with Session(engine) as s:
        p = s.query(Posting).first()
        assert p is not None
        assert p.status == "skipped"


def test_rank_dealbreaker_penalty_applied(tmp_path: Path) -> None:
    """junior_level dealbreaker: penalty=4, raw=8 → final=4 → skipped (threshold=6)."""
    engine = get_engine(tmp_path / "test.db")
    normalize(
        [_posting(title="Junior ML Engineer", description="Entry-level, 0-2 years experience.")],
        engine=engine,
    )
    client = _fake_client(score=8, level="junior", dealbreakers=["junior_level"])
    n = rank_postings(engine=engine, profile_path=PROFILE_PATH, client=client)
    assert n == 1
    with Session(engine) as s:
        p = s.query(Posting).first()
        assert p is not None
        assert p.status == "skipped"
        assert p.relevance_score == 4  # 8 - 4 penalty
        assert json.loads(p.dealbreakers_hit or "[]") == ["junior_level"]


def test_rank_idempotent(tmp_path: Path) -> None:
    """Re-running rank on already-ranked postings is a no-op."""
    engine = get_engine(tmp_path / "test.db")
    normalize([_posting()], engine=engine)
    client = _fake_client(score=7)
    rank_postings(engine=engine, profile_path=PROFILE_PATH, client=client)
    # second run: no 'new' postings remain
    n = rank_postings(engine=engine, profile_path=PROFILE_PATH, client=client)
    assert n == 0
    assert client.messages.create.call_count == 1


def test_rank_llm_failure_continues(tmp_path: Path) -> None:
    """A crashed LLM call logs a warning but doesn't abort the rest."""
    engine = get_engine(tmp_path / "test.db")
    p1 = _posting(title="Senior ML Engineer", url="https://example.com/1")
    p2 = _posting(title="Research Scientist", url="https://example.com/2", company_slug="acme2")
    normalize([p1, p2], engine=engine)

    good_block = MagicMock()
    good_block.type = "tool_use"
    good_block.name = "score_posting"
    good_block.input = {
        "relevance_score": 9,
        "level_match": "match",
        "one_line_rationale": "Great fit.",
        "dealbreakers_hit": [],
    }
    good_resp = MagicMock()
    good_resp.content = [good_block]

    client = MagicMock()
    client.messages.create.side_effect = [RuntimeError("timeout"), good_resp]

    n = rank_postings(engine=engine, profile_path=PROFILE_PATH, client=client)
    assert n == 1  # only the second posting scored
    with Session(engine) as s:
        ranked = [p for p in s.query(Posting).all() if p.status == "ranked"]
        assert len(ranked) == 1
