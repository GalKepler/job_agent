"""Remotive public API adapter — remote-only jobs, no key required."""

import logging
import re

import httpx

from src.sources.base import RawPosting

log = logging.getLogger(__name__)
BASE_URL = "https://remotive.com/api/remote-jobs"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class RemotiveSource:
    SOURCE = "remotive"

    def __init__(self, search_terms: list[str]) -> None:
        self.search_terms = search_terms

    def fetch(self) -> list[RawPosting]:
        seen: set[int] = set()
        postings: list[RawPosting] = []
        for term in self.search_terms:
            resp = httpx.get(BASE_URL, params={"search": term}, timeout=30)
            resp.raise_for_status()
            for job in resp.json().get("jobs", []):
                jid: int = job["id"]
                if jid in seen:
                    continue
                seen.add(jid)
                company: str = job.get("company_name", "")
                postings.append(
                    RawPosting(
                        source=self.SOURCE,
                        company=company,
                        company_slug=_slug(company),
                        title=job["title"],
                        location=job.get("candidate_required_location", "Remote"),
                        url=job["url"],
                        description=job.get("description", "") or "",
                        remote=True,
                        raw=job,
                    )
                )
        return postings
