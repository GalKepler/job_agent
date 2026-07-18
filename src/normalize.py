"""Dedup and persist raw postings into jobs.db."""

import json
import logging
from typing import Any

from sqlalchemy.dialects.sqlite import insert

from src.db import Posting, get_engine, make_dedup_hash
from src.sources.base import RawPosting

log = logging.getLogger(__name__)


def normalize(postings: list[RawPosting], engine: Any = None) -> tuple[int, int]:
    """Insert new postings; skip duplicates on (company_slug, title, location)."""
    if engine is None:
        engine = get_engine()
    inserted = skipped = 0
    with engine.begin() as conn:
        for p in postings:
            h = make_dedup_hash(p.company_slug, p.title, p.location)
            stmt = (
                insert(Posting)
                .values(
                    dedup_hash=h,
                    source=p.source,
                    company=p.company,
                    company_slug=p.company_slug,
                    title=p.title,
                    location=p.location,
                    url=p.url,
                    description=p.description,
                    remote=p.remote,
                    status="new",
                    raw_json=json.dumps(p.raw),
                )
                .on_conflict_do_nothing(index_elements=["dedup_hash"])
            )
            result = conn.execute(stmt)
            if result.rowcount:
                inserted += 1
            else:
                skipped += 1
    log.info("normalize: inserted=%d skipped=%d", inserted, skipped)
    return inserted, skipped
