"""Join ranked postings to connections.csv by company."""

import csv
import json
import logging
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.db import Posting, get_engine

log = logging.getLogger(__name__)

CONNECTIONS_PATH = Path("data/Connections.csv")
_MATCH_THRESHOLD = 80  # rapidfuzz score 0–100

_SENIOR_KEYWORDS = {"vp", "director", "head", "chief", "principal", "staff", "senior", "lead"}
_STRIP_SUFFIXES = (
    " Inc.",
    " Inc",
    " Ltd.",
    " Ltd",
    " LLC",
    " Corp.",
    " Corp",
    " Platforms",
    " Technologies",
    " Technology",
    " Systems",
    " Software",
    " Solutions",
    " Group",
    " International",
)


def _load_connections(path: Path) -> list[dict[str, str]]:
    """Parse LinkedIn CSV export, skipping the 3-line notes preamble."""
    with path.open(newline="", encoding="utf-8") as f:
        lines = f.readlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("First Name"))
    reader = csv.DictReader(lines[start:])
    return [row for row in reader if row.get("Company")]


def _normalize(name: str) -> str:
    for suffix in _STRIP_SUFFIXES:
        name = name.replace(suffix, "")
    return name.strip().lower()


def _warmth(position: str) -> int:
    """Rough seniority proxy — higher is a warmer referral candidate."""
    low = position.lower()
    return sum(1 for kw in _SENIOR_KEYWORDS if kw in low)


def match_postings(
    engine: Any = None,
    connections_path: Path = CONNECTIONS_PATH,
) -> int:
    """Fuzzy-match ranked postings to LinkedIn connections by company name.

    Advances status: ranked → matched.
    Returns count of postings processed.
    """
    if engine is None:
        engine = get_engine()

    if not connections_path.exists():
        log.warning("match: %s not found — skipping network match", connections_path)
        return 0

    connections = _load_connections(connections_path)
    log.info("match: loaded %d connections with a company", len(connections))

    company_norms = [_normalize(c["Company"]) for c in connections]

    with Session(engine) as session:
        postings = list(session.scalars(select(Posting).where(Posting.status == "ranked")))
        if not postings:
            log.info("match: no ranked postings")
            return 0

        count = 0
        for p in postings:
            needle = _normalize(p.company)
            results: list[tuple[str, float, int]] = process.extract(
                needle, company_norms, scorer=fuzz.ratio, limit=None
            )
            hits = sorted(
                [connections[idx] for _, score, idx in results if score >= _MATCH_THRESHOLD],
                key=lambda c: _warmth(c.get("Position", "")),
                reverse=True,
            )
            conns_out = [
                {
                    "name": f"{c['First Name']} {c['Last Name']}".strip(),
                    "company": c["Company"],
                    "position": c.get("Position", ""),
                    "linkedin_url": c.get("URL", ""),
                    "connected_on": c.get("Connected On", ""),
                }
                for c in hits[:5]
            ]
            session.execute(
                update(Posting)
                .where(Posting.id == p.id)
                .values(connections_json=json.dumps(conns_out), status="matched")
            )
            log.info(
                "match: id=%d %r @ %s — %d connection(s) found",
                p.id,
                p.title,
                p.company,
                len(conns_out),
            )
            count += 1

        session.commit()

    return count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    n = match_postings()
    print(f"Matched {n} postings.")
