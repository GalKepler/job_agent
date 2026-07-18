"""Greenhouse public board API adapter."""

import logging

import httpx

from src.sources.base import RawPosting

log = logging.getLogger(__name__)


class GreenhouseSource:
    SOURCE = "greenhouse"

    def __init__(self, company_slug: str) -> None:
        self.company_slug = company_slug

    def fetch(self) -> list[RawPosting]:
        url = f"https://boards-api.greenhouse.io/v1/boards/{self.company_slug}/jobs"
        resp = httpx.get(url, timeout=30)
        if resp.status_code == 404:
            log.warning("greenhouse/%s: board not found (404) — check slug", self.company_slug)
            return []
        resp.raise_for_status()
        data = resp.json()
        postings = []
        for job in data.get("jobs", []):
            location: str = (job.get("location") or {}).get("name", "") or ""
            remote = "remote" in location.lower()
            postings.append(
                RawPosting(
                    source=self.SOURCE,
                    company=self.company_slug.replace("-", " ").title(),
                    company_slug=self.company_slug,
                    title=job["title"],
                    location=location,
                    url=job.get("absolute_url", ""),
                    description=job.get("content", "") or "",
                    remote=remote,
                    raw=job,
                )
            )
        return postings
