"""Stage 5 queue rendering tests."""

import json
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from src.db import Posting, get_engine
from src.normalize import normalize
from src.queue import render_queue
from src.sources.base import RawPosting


def _posting(**overrides: object) -> RawPosting:
    defaults = dict(
        source="greenhouse",
        company="Apple",
        company_slug="apple",
        title="Research Scientist",
        location="Tel Aviv",
        url="https://example.com/1",
        description="Great role.",
        remote=False,
        raw={},
    )
    return RawPosting(**(defaults | overrides))  # type: ignore[arg-type]


def _seed_generated(engine: object) -> None:
    normalize([_posting()], engine=engine)
    with Session(engine) as s:  # type: ignore[arg-type]
        p = s.query(Posting).first()
        assert p is not None
        p.status = "generated"
        p.relevance_score = 9
        p.level_match = "match"
        p.rationale = "Strong biosignal domain fit."
        p.connections_json = json.dumps(
            [
                {
                    "name": "Jane Doe",
                    "position": "Senior Engineer",
                    "linkedin_url": "https://linkedin.com/in/janedoe",
                    "company": "Apple",
                    "connected_on": "01 Jan 2024",
                }
            ]
        )
        p.generated_content = "## Verdict\nStrong fit.\n\n## Gap analysis\n..."
        s.commit()


def test_render_queue_creates_file(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "test.db")
    _seed_generated(engine)
    path = render_queue(engine=engine, review_dir=tmp_path / "review", today=date(2026, 7, 18))
    assert path is not None
    assert path.name == "2026-07-18.md"
    text = path.read_text()
    assert "Apple" in text
    assert "Research Scientist" in text
    assert "Jane Doe" in text
    assert "Strong fit." in text
    assert "- [ ] Apply" in text


def test_render_queue_empty_returns_none(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "test.db")
    result = render_queue(engine=engine, review_dir=tmp_path / "review")
    assert result is None


def test_render_queue_ordered_by_score(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "test.db")
    normalize(
        [
            _posting(url="https://example.com/1", company_slug="apple"),
            _posting(url="https://example.com/2", company_slug="google", company="Google"),
        ],
        engine=engine,
    )
    with Session(engine) as s:
        postings = s.query(Posting).all()
        scores = [7, 9]
        for p, score in zip(postings, scores):
            p.status = "generated"
            p.relevance_score = score
            p.connections_json = "[]"
        s.commit()

    path = render_queue(engine=engine, review_dir=tmp_path / "review", today=date(2026, 7, 18))
    assert path is not None
    text = path.read_text()
    # Score 9 (Google) should appear before score 7 (Apple)
    assert text.index("Google") < text.index("Apple")
