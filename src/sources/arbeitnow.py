"""Arbeitnow job board API adapter — free, no key, EU + remote focus."""

import logging
import re
from typing import Any

import httpx

from src.sources.base import RawPosting

log = logging.getLogger(__name__)
BASE_URL = "https://www.arbeitnow.com/api/job-board-api"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class ArbeitnowSource:
    SOURCE = "arbeitnow"

    def __init__(self, tags: list[str], max_pages: int = 5) -> None:
        self.tags = [t.lower() for t in tags]
        self.max_pages = max_pages

    def fetch(self) -> list[RawPosting]:
        seen: set[str] = set()
        postings: list[RawPosting] = []
        for page in range(1, self.max_pages + 1):
            resp = httpx.get(BASE_URL, params={"page": page}, timeout=30)
            if resp.status_code == 404:
                break
            resp.raise_for_status()
            jobs: list[dict[str, Any]] = resp.json().get("data", [])
            if not jobs:
                break
            for job in jobs:
                slug_id = str(job.get("slug", ""))
                if slug_id in seen:
                    continue
                # ponytail: client-side tag filter — Arbeitnow API has no server-side tag param
                if self.tags:
                    raw_tags: Any = job.get("tags") or []
                    job_tags = [str(t).lower() for t in raw_tags if isinstance(raw_tags, list)]
                    if not any(t in job_tags for t in self.tags):
                        continue
                seen.add(slug_id)
                company: str = str(job.get("company_name", ""))
                location: str = str(job.get("location", ""))
                remote = bool(job.get("remote")) or "remote" in location.lower()
                postings.append(
                    RawPosting(
                        source=self.SOURCE,
                        company=company,
                        company_slug=_slug(company) if company else "unknown",
                        title=str(job.get("title", "")),
                        location=location,
                        url=str(job.get("url", "")),
                        description=str(job.get("description", "") or ""),
                        remote=remote,
                        raw=job,
                    )
                )
        return postings
