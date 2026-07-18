"""Write review/YYYY-MM-DD.md from generated postings."""

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db import Posting, get_engine

log = logging.getLogger(__name__)

REVIEW_DIR = Path("review")


def _render_posting(p: Posting) -> str:
    connections: list[dict[str, str]] = json.loads(p.connections_json or "[]")
    conn_lines = (
        "\n".join(f"  - [{c['name']}]({c['linkedin_url']}) — {c['position']}" for c in connections)
        if connections
        else "  *(no connections at this company)*"
    )
    score = p.relevance_score if p.relevance_score is not None else "—"
    level = p.level_match or "—"
    rationale = p.rationale or "—"
    content = p.generated_content or "*generation not available*"

    return f"""---

## {p.company} — {p.title}

**Score:** {score}/10 | **Level match:** {level} | **Status:** {p.status}
**URL:** {p.url}
**Location:** {p.location}

**Ranker rationale:** {rationale}

### Network connections
{conn_lines}

### CV tailoring output
{content}

- [ ] Apply
- [ ] Skip
- [ ] Send outreach

"""


def render_queue(
    engine: Any = None,
    review_dir: Path = REVIEW_DIR,
    today: date | None = None,
) -> Path | None:
    """Render all generated postings to review/YYYY-MM-DD.md.

    Returns the path written, or None if nothing to render.
    """
    if engine is None:
        engine = get_engine()
    if today is None:
        today = date.today()

    with Session(engine) as session:
        postings = list(
            session.scalars(
                select(Posting)
                .where(Posting.status == "generated")
                .order_by(Posting.relevance_score.desc())
            )
        )

    if not postings:
        log.info("queue: no generated postings")
        return None

    review_dir.mkdir(exist_ok=True)
    out_path = review_dir / f"{today}.md"

    header = f"# Job Queue — {today}\n\n{len(postings)} role(s) ready for review.\n"
    body = "".join(_render_posting(p) for p in postings)
    out_path.write_text(header + body)
    log.info("queue: wrote %d posting(s) to %s", len(postings), out_path)
    return out_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    path = render_queue()
    if path:
        print(f"Queue written to {path}")
    else:
        print("Nothing to render.")
