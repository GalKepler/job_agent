"""Invoke the cv-tailoring skill per matched posting."""

import json
import logging
import zipfile
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.db import Posting, get_engine
from src.llm import chat_call, default_gen_model, make_client

load_dotenv()

log = logging.getLogger(__name__)

SKILL_PATH = Path("skills/cv-tailoring.skill")
MASTER_CV_PATH = Path("data/master_cv.md")


def _read_skill(skill_path: Path) -> tuple[str, str]:
    with zipfile.ZipFile(skill_path) as zf:
        skill_md = zf.read("cv-tailoring/SKILL.md").decode()
        positioning_md = zf.read("cv-tailoring/references/positioning.md").decode()
    return skill_md, positioning_md


def _build_user_message(posting: Posting, master_cv: str, positioning_md: str) -> str:
    connections: list[dict[str, str]] = json.loads(posting.connections_json or "[]")
    conn_section = (
        "\n".join(f"- {c['name']} ({c['position']}) — {c['linkedin_url']}" for c in connections)
        if connections
        else "None"
    )
    return f"""## Job Posting
Company: {posting.company}
Title: {posting.title}
Location: {posting.location}

{posting.description[:4000]}

## Master CV
{master_cv}

## Positioning Reference
{positioning_md}

## Network Connections at {posting.company}
{conn_section}

Follow the skill workflow. If connections exist, also produce a referral outreach draft.
"""


def generate_postings(
    engine: Any = None,
    master_cv_path: Path = MASTER_CV_PATH,
    skill_path: Path = SKILL_PATH,
    client: Any = None,
    model: str | None = None,
) -> int:
    """Run the cv-tailoring skill for each matched posting.

    Advances status: matched → generated.
    Returns count of postings processed.
    """
    if engine is None:
        engine = get_engine()
    if not master_cv_path.exists():
        log.warning(
            "generate: %s not found — place your master CV there and re-run", master_cv_path
        )
        return 0
    if client is None:
        client = make_client()
    if model is None:
        model = default_gen_model()

    master_cv = master_cv_path.read_text()
    skill_md, positioning_md = _read_skill(skill_path)

    with Session(engine) as session:
        postings = list(session.scalars(select(Posting).where(Posting.status == "matched")))
        if not postings:
            log.info("generate: no matched postings")
            return 0

        count = 0
        for p in postings:
            try:
                content = chat_call(
                    client, model, skill_md, _build_user_message(p, master_cv, positioning_md)
                )
            except Exception as exc:
                log.warning("generate: id=%d failed — %s", p.id, exc)
                continue

            session.execute(
                update(Posting)
                .where(Posting.id == p.id)
                .values(generated_content=content, status="generated")
            )
            log.info("generate: id=%d %r @ %s — done", p.id, p.title, p.company)
            count += 1

        session.commit()

    return count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    n = generate_postings()
    print(f"Generated {n} postings.")
