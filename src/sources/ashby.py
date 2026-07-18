"""Ashby public board API adapter."""

import logging

import httpx

from src.sources.base import RawPosting

log = logging.getLogger(__name__)


class AshbySource:
    SOURCE = "ashby"

    def __init__(self, company_slug: str) -> None:
        self.company_slug = company_slug

    def fetch(self) -> list[RawPosting]:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{self.company_slug}"
        resp = httpx.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        postings = []
        for job in data.get("jobPostings", []):
            location = job.get("locationName", "") or ""
            remote = bool(job.get("isRemote")) or "remote" in location.lower()
            postings.append(
                RawPosting(
                    source=self.SOURCE,
                    company=self.company_slug.replace("-", " ").title(),
                    company_slug=self.company_slug,
                    title=job["title"],
                    location=location,
                    url=job.get("jobUrl", ""),
                    description=job.get("descriptionHtml", "") or "",
                    remote=remote,
                    raw=job,
                )
            )
        return postings
