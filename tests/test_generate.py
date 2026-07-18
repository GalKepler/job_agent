"""Stage 4 generation tests — mocked Anthropic client, no network."""

from pathlib import Path
from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from src.db import Posting, get_engine
from src.generate import generate_postings
from src.normalize import normalize
from src.sources.base import RawPosting


def _posting(**overrides: object) -> RawPosting:
    defaults = dict(
        source="greenhouse",
        company="Apple",
        company_slug="apple",
        title="Research Scientist",
        location="Tel Aviv",
        url="https://example.com/1",
        description="ML research role.",
        remote=False,
        raw={},
    )
    return RawPosting(**(defaults | overrides))  # type: ignore[arg-type]


def _seed_matched(engine: object, postings: list[RawPosting]) -> None:
    normalize(postings, engine=engine)
    with Session(engine) as s:  # type: ignore[arg-type]
        for p in s.query(Posting).all():
            p.status = "matched"
            p.connections_json = "[]"
        s.commit()


def _fake_client(text: str = "## Verdict\nStrong fit.") -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    client = MagicMock()
    client.messages.create.return_value = resp
    return client


def test_generate_advances_to_generated(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "test.db")
    _seed_matched(engine, [_posting()])
    master_cv = tmp_path / "master_cv.md"
    master_cv.write_text("# CV\nGal Kepler, PhD ML Engineer.")

    n = generate_postings(
        engine=engine,
        master_cv_path=master_cv,
        skill_path=Path("skills/cv-tailoring.skill"),
        client=_fake_client("## Verdict\nStrong fit."),
    )
    assert n == 1
    with Session(engine) as s:
        p = s.query(Posting).first()
        assert p is not None
        assert p.status == "generated"
        assert p.generated_content is not None
        assert "Verdict" in p.generated_content


def test_generate_no_master_cv_returns_zero(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "test.db")
    _seed_matched(engine, [_posting()])
    n = generate_postings(
        engine=engine,
        master_cv_path=tmp_path / "no_cv.md",
        skill_path=Path("skills/cv-tailoring.skill"),
        client=_fake_client(),
    )
    assert n == 0


def test_generate_llm_failure_continues(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "test.db")
    p1 = _posting(url="https://example.com/1", company_slug="apple")
    p2 = _posting(url="https://example.com/2", company_slug="google", company="Google")
    _seed_matched(engine, [p1, p2])
    master_cv = tmp_path / "master_cv.md"
    master_cv.write_text("# CV")

    client = MagicMock()
    good_block = MagicMock()
    good_block.type = "text"
    good_block.text = "## Verdict\nGood fit."
    good_resp = MagicMock()
    good_resp.content = [good_block]
    client.messages.create.side_effect = [RuntimeError("timeout"), good_resp]

    n = generate_postings(
        engine=engine,
        master_cv_path=master_cv,
        skill_path=Path("skills/cv-tailoring.skill"),
        client=client,
    )
    assert n == 1


def test_generate_idempotent(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "test.db")
    _seed_matched(engine, [_posting()])
    master_cv = tmp_path / "master_cv.md"
    master_cv.write_text("# CV")
    client = _fake_client()

    generate_postings(
        engine=engine,
        master_cv_path=master_cv,
        skill_path=Path("skills/cv-tailoring.skill"),
        client=client,
    )
    n = generate_postings(
        engine=engine,
        master_cv_path=master_cv,
        skill_path=Path("skills/cv-tailoring.skill"),
        client=client,
    )
    assert n == 0
    assert client.messages.create.call_count == 1
