"""Invoke the cv-tailoring skill per matched posting."""

import json
import logging
import zipfile
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.db import Posting, get_engine

load_dotenv()

log = logging.getLogger(__name__)

SKILL_PATH = Path("skills/cv-tailoring.skill")
MASTER_CV_PATH = Path("data/master_cv.md")
# ponytail: sonnet for generation quality; haiku is fine for ranking but skill output matters
_DEFAULT_MODEL = "claude-sonnet-4-6"


def _read_skill(skill_path: Path) -> tuple[str, str]:
    """Extract SKILL.md and positioning.md from the skill zip."""
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
    client: anthropic.Anthropic | None = None,
    model: str = _DEFAULT_MODEL,
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
        client = anthropic.Anthropic()

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
                resp = client.messages.create(
                    model=model,
                    max_tokens=4096,
                    system=skill_md,
                    messages=[
                        {
                            "role": "user",
                            "content": _build_user_message(p, master_cv, positioning_md),
                        }
                    ],
                )
                text_block = next(
                    (b for b in resp.content if getattr(b, "type", None) == "text"), None
                )
                if text_block is None:
                    raise RuntimeError("No text block in response")
                content: str = text_block.text  # type: ignore[union-attr]
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
