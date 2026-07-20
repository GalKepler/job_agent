"""LLM relevance scoring against profile.yaml."""

import json
import logging
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

import yaml
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.db import Posting, get_engine
from src.llm import default_rank_model, make_client, score_posting_call

log = logging.getLogger(__name__)

_PROFILE_PATH = Path("config/profile.yaml")


def _build_prompt(profile: dict[str, Any], posting: Posting) -> str:
    keys = (
        "identity",
        "level",
        "target_roles",
        "signals_positive",
        "signals_negative",
        "dealbreakers",
        "ranking",
    )
    subset = {k: profile[k] for k in keys}
    return f"""Score this job posting against the candidate profile.

## Candidate Profile
{yaml.dump(subset, allow_unicode=True, sort_keys=False)}

## Job Posting
Company: {posting.company}
Title: {posting.title}
Location: {posting.location}

{posting.description[:3000]}

## Scoring rules
- relevance_score: 0-10 based on role family, domain signals, tech stack fit.
- level_match: compare inferred posting level to anchor (senior_ic).
- dealbreakers_hit: list `id` of any dealbreaker whose `match` keywords appear in title/description.
- one_line_rationale: one sentence, lead with the strongest signal for or against.

Provide your assessment.
"""


def rank_postings(
    engine: Any = None,
    profile_path: Path = _PROFILE_PATH,
    client: Any = None,
    model: str | None = None,
) -> int:
    """Score all 'new' postings; advance to 'ranked' (≥ threshold) or 'skipped'."""
    if engine is None:
        engine = get_engine()
    if client is None:
        client = make_client()
    if model is None:
        model = default_rank_model()

    profile: dict[str, Any] = yaml.safe_load(profile_path.read_text())
    threshold: int = profile["ranking"]["threshold_advance"]
    penalty: int = abs(profile["ranking"]["hard_flag_penalty"])

    with Session(engine) as session:
        postings = list(session.scalars(select(Posting).where(Posting.status == "new")))
        if not postings:
            log.info("rank: no new postings")
            return 0

        scored = 0
        for p in postings:
            try:
                result = score_posting_call(client, model, _build_prompt(profile, p))
            except Exception as exc:
                log.warning("rank: posting id=%d failed — %s", p.id, exc)
                continue

            raw_score: int = result["relevance_score"]
            hits: list[str] = result["dealbreakers_hit"]
            final_score = max(0, raw_score - penalty * len(hits))
            new_status = "ranked" if final_score >= threshold else "skipped"

            session.execute(
                update(Posting)
                .where(Posting.id == p.id)
                .values(
                    relevance_score=final_score,
                    level_match=result["level_match"],
                    rationale=result["one_line_rationale"],
                    dealbreakers_hit=json.dumps(hits),
                    status=new_status,
                )
            )
            log.info(
                "rank: id=%d %r @ %s — score=%d level=%s dealbreakers=%s → %s",
                p.id,
                p.title,
                p.company,
                final_score,
                result["level_match"],
                hits or "none",
                new_status,
            )
            scored += 1

        session.commit()

    return scored


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    n = rank_postings()
    print(f"Ranked {n} postings.")
