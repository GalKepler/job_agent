"""Lever public postings API adapter."""

import logging

import httpx

from src.sources.base import RawPosting

log = logging.getLogger(__name__)


class LeverSource:
    SOURCE = "lever"

    def __init__(self, company_slug: str) -> None:
        self.company_slug = company_slug

    def fetch(self) -> list[RawPosting]:
        url = f"https://api.lever.co/v0/postings/{self.company_slug}?mode=json"
        resp = httpx.get(url, timeout=30)
        resp.raise_for_status()
        postings = []
        for job in resp.json():
            categories: dict[str, str] = job.get("categories") or {}
            location = categories.get("location", "") or ""
            remote = "remote" in location.lower()
            description = job.get("descriptionPlain") or job.get("description") or ""
            postings.append(
                RawPosting(
                    source=self.SOURCE,
                    company=self.company_slug.replace("-", " ").title(),
                    company_slug=self.company_slug,
                    title=job["text"],
                    location=location,
                    url=job.get("hostedUrl", ""),
                    description=description,
                    remote=remote,
                    raw=job,
                )
            )
        return postings
