"""Stage 3 match tests — no network, no real connections.csv required."""

import json
from pathlib import Path

from sqlalchemy.orm import Session

from src.db import Posting, get_engine
from src.match import _normalize, _warmth, match_postings
from src.normalize import normalize
from src.sources.base import RawPosting


def _posting(**overrides: object) -> RawPosting:
    defaults = dict(
        source="greenhouse",
        company="Apple Inc.",
        company_slug="apple",
        title="Senior ML Engineer",
        location="Tel Aviv",
        url="https://example.com/1",
        description="Strong ML role.",
        remote=False,
        raw={},
    )
    return RawPosting(**(defaults | overrides))  # type: ignore[arg-type]


def _seed_ranked(engine: object, postings: list[RawPosting]) -> None:
    """Insert postings already in 'ranked' status."""
    normalize(postings, engine=engine)
    with Session(engine) as s:  # type: ignore[arg-type]
        for p in s.query(Posting).all():
            p.status = "ranked"
            p.relevance_score = 8
        s.commit()


def _csv(tmp_path: Path, rows: list[str]) -> Path:
    """Write a minimal LinkedIn-export CSV with header notes."""
    csv_path = tmp_path / "Connections.csv"
    header = (
        "Notes:\n"
        '"Some note."\n'
        "\n"
        "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
    )
    csv_path.write_text(header + "\n".join(rows) + "\n")
    return csv_path


def test_match_finds_connection(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "test.db")
    _seed_ranked(engine, [_posting()])
    csv_path = _csv(
        tmp_path,
        ["Jane,Doe,https://linkedin.com/in/janedoe,,Apple,Senior Engineer,01 Jan 2024"],
    )
    n = match_postings(engine=engine, connections_path=csv_path)
    assert n == 1
    with Session(engine) as s:
        p = s.query(Posting).first()
        assert p is not None
        assert p.status == "matched"
        conns = json.loads(p.connections_json or "[]")
        assert len(conns) == 1
        assert conns[0]["name"] == "Jane Doe"


def test_match_no_connection_still_advances(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "test.db")
    _seed_ranked(engine, [_posting(company="Obscure Co", company_slug="obscure")])
    csv_path = _csv(
        tmp_path,
        ["Jane,Doe,https://linkedin.com/in/janedoe,,Apple,Engineer,01 Jan 2024"],
    )
    n = match_postings(engine=engine, connections_path=csv_path)
    assert n == 1
    with Session(engine) as s:
        p = s.query(Posting).first()
        assert p is not None
        assert p.status == "matched"
        assert json.loads(p.connections_json or "[]") == []


def test_match_missing_csv_returns_zero(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "test.db")
    _seed_ranked(engine, [_posting()])
    n = match_postings(engine=engine, connections_path=tmp_path / "no_such.csv")
    assert n == 0
    with Session(engine) as s:
        p = s.query(Posting).first()
        assert p is not None
        assert p.status == "ranked"  # unchanged


def test_match_idempotent(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "test.db")
    _seed_ranked(engine, [_posting()])
    csv_path = _csv(
        tmp_path,
        ["Jane,Doe,https://linkedin.com/in/janedoe,,Apple,Engineer,01 Jan 2024"],
    )
    match_postings(engine=engine, connections_path=csv_path)
    n = match_postings(engine=engine, connections_path=csv_path)
    assert n == 0  # no ranked postings remain


def test_normalize_strips_suffixes() -> None:
    assert _normalize("Apple Inc.") == "apple"
    assert _normalize("Meta Platforms") == "meta"
    assert _normalize("Google LLC") == "google"


def test_warmth_scores_senior_higher() -> None:
    assert _warmth("Senior Software Engineer") > _warmth("Software Engineer")
    assert _warmth("VP of Engineering") > _warmth("Junior Engineer")
