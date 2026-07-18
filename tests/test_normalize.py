"""Normalize/dedup tests — uses a temp SQLite DB, no network."""

from pathlib import Path

from sqlalchemy.orm import Session

from src.db import Posting, get_engine
from src.normalize import normalize
from src.sources.base import RawPosting


def _posting(**overrides: object) -> RawPosting:
    defaults: dict[str, object] = dict(
        source="greenhouse",
        company="Apple",
        company_slug="apple",
        title="ML Engineer",
        location="Cupertino, CA",
        url="https://example.com/1",
        description="...",
        remote=False,
        raw={},
    )
    return RawPosting(**(defaults | overrides))


def test_normalize_inserts(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "test.db")
    inserted, skipped = normalize([_posting()], engine=engine)
    assert inserted == 1
    assert skipped == 0
    with Session(engine) as s:
        assert s.query(Posting).count() == 1


def test_normalize_dedup(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "test.db")
    p = _posting()
    normalize([p], engine=engine)
    inserted, skipped = normalize([p], engine=engine)
    assert inserted == 0
    assert skipped == 1
    with Session(engine) as s:
        assert s.query(Posting).count() == 1


def test_normalize_distinct_postings(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "test.db")
    p1 = _posting(title="ML Engineer", location="Cupertino, CA")
    p2 = _posting(title="Research Scientist", location="Cupertino, CA")
    inserted, skipped = normalize([p1, p2], engine=engine)
    assert inserted == 2
    assert skipped == 0


def test_normalize_status_new(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "test.db")
    normalize([_posting()], engine=engine)
    with Session(engine) as s:
        row = s.query(Posting).first()
        assert row is not None
        assert row.status == "new"
