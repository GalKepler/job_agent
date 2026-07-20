"""Adzuna job search API adapter — requires ADZUNA_APP_ID and ADZUNA_APP_KEY env vars."""

import logging
import re
from typing import Any

import httpx

from src.sources.base import RawPosting

log = logging.getLogger(__name__)
BASE_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class AdzunaSource:
    SOURCE = "adzuna"

    def __init__(
        self,
        countries: list[str],
        search_terms: list[str],
        app_id: str,
        app_key: str,
        results_per_page: int = 50,
        max_pages: int = 3,
    ) -> None:
        self.countries = countries
        self.search_terms = search_terms
        self.app_id = app_id
        self.app_key = app_key
        self.results_per_page = results_per_page
        self.max_pages = max_pages

    def _fetch_page(self, country: str, term: str, page: int) -> list[dict[str, Any]]:
        url = BASE_URL.format(country=country, page=page)
        resp = httpx.get(
            url,
            params={
                "app_id": self.app_id,
                "app_key": self.app_key,
                "what": term,
                "results_per_page": self.results_per_page,
                "content-type": "application/json",
            },
            timeout=30,
        )
        if resp.status_code in (400, 404):
            log.warning("adzuna/%s: %d for %r — skipping (check country code)", country, resp.status_code, term)
            return []
        resp.raise_for_status()
        results: list[dict[str, Any]] = resp.json().get("results", [])
        return results

    def fetch(self) -> list[RawPosting]:
        seen: set[str] = set()
        postings: list[RawPosting] = []
        for country in self.countries:
            for term in self.search_terms:
                for page in range(1, self.max_pages + 1):
                    results = self._fetch_page(country, term, page)
                    if not results:
                        break
                    for job in results:
                        jid = str(job.get("id", ""))
                        if jid in seen:
                            continue
                        seen.add(jid)
                        company_obj: Any = job.get("company") or {}
                        location_obj: Any = job.get("location") or {}
                        company: str = company_obj.get("display_name", "") if isinstance(company_obj, dict) else ""
                        location: str = location_obj.get("display_name", "") if isinstance(location_obj, dict) else ""
                        title: str = str(job.get("title", ""))
                        remote = "remote" in (location + title).lower()
                        postings.append(
                            RawPosting(
                                source=self.SOURCE,
                                company=company,
                                company_slug=_slug(company) if company else "unknown",
                                title=title,
                                location=location,
                                url=str(job.get("redirect_url", "")),
                                description=str(job.get("description", "") or ""),
                                remote=remote,
                                raw=job,
                            )
                        )
        return postings
