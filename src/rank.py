"""LLM relevance scoring against profile.yaml."""

import json
import logging
from pathlib import Path
from typing import Any, cast

import anthropic
import yaml
from anthropic.types import ToolChoiceToolParam, ToolParam
from dotenv import load_dotenv
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.db import Posting, get_engine

load_dotenv()

log = logging.getLogger(__name__)

_PROFILE_PATH = Path("config/profile.yaml")
# ponytail: haiku is cheap enough for per-posting ranking; swap to sonnet if quality is poor
_DEFAULT_MODEL = "claude-haiku-4-5-20251001"

_SCORE_TOOL: ToolParam = {
    "name": "score_posting",
    "description": "Score a job posting against the candidate profile.",
    "input_schema": {
        "type": "object",
        "properties": {
            "relevance_score": {
                "type": "integer",
                "description": "Raw fit score 0-10 before dealbreaker penalties.",
            },
            "level_match": {
                "type": "string",
                "enum": ["junior", "match", "stretch"],
                "description": "junior=below anchor, match=appropriate, stretch=above anchor",
            },
            "one_line_rationale": {
                "type": "string",
                "description": "One sentence explaining the score.",
            },
            "dealbreakers_hit": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Dealbreaker ids triggered (empty list if none).",
            },
        },
        "required": [
            "relevance_score",
            "level_match",
            "one_line_rationale",
            "dealbreakers_hit",
        ],
    },
}


def _build_prompt(profile: dict[str, Any], posting: Posting) -> str:
    _keys = (
        "level",
        "target_roles",
        "signals_positive",
        "signals_negative",
        "dealbreakers",
        "ranking",
    )
    key = {k: profile[k] for k in _keys}
    return f"""Score this job posting against the candidate profile.

## Candidate Profile
{yaml.dump(key, allow_unicode=True, sort_keys=False)}

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

Call score_posting with your assessment.
"""


def _score_one(
    client: anthropic.Anthropic,
    model: str,
    profile: dict[str, Any],
    posting: Posting,
) -> dict[str, Any]:
    resp = client.messages.create(
        model=model,
        max_tokens=512,
        tools=[_SCORE_TOOL],
        tool_choice=ToolChoiceToolParam(type="tool", name="score_posting"),
        messages=[{"role": "user", "content": _build_prompt(profile, posting)}],
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == "score_posting":
            return cast(dict[str, Any], block.input)
    raise RuntimeError(f"No score_posting block in response: {resp}")


def rank_postings(
    engine: Any = None,
    profile_path: Path = _PROFILE_PATH,
    client: anthropic.Anthropic | None = None,
    model: str = _DEFAULT_MODEL,
) -> int:
    """Score all 'new' postings; advance to 'ranked' (≥ threshold) or 'skipped'."""
    if engine is None:
        engine = get_engine()
    profile: dict[str, Any] = yaml.safe_load(profile_path.read_text())
    threshold: int = profile["ranking"]["threshold_advance"]
    penalty: int = abs(profile["ranking"]["hard_flag_penalty"])
    if client is None:
        client = anthropic.Anthropic()

    with Session(engine) as session:
        postings = list(session.scalars(select(Posting).where(Posting.status == "new")))
        if not postings:
            log.info("rank: no new postings")
            return 0

        scored = 0
        for p in postings:
            try:
                result = _score_one(client, model, profile, p)
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
