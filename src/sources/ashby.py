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
        if resp.status_code == 404:
            log.warning("ashby/%s: board not found (404) — check slug", self.company_slug)
            return []
        resp.raise_for_status()
        data = resp.json()
        # API returns either "jobs" (current) or "jobPostings" (legacy)
        jobs = data.get("jobs") or data.get("jobPostings") or []
        postings = []
        for job in jobs:
            # "jobs" shape uses "location" (str); "jobPostings" shape uses "locationName"
            location = job.get("location") or job.get("locationName") or ""
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
