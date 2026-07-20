"""Hiremetech job board scraper — Israeli tech jobs, no key required."""

import logging
import re
from typing import Any

import httpx

from src.sources.base import RawPosting

log = logging.getLogger(__name__)
BASE_URL = "https://hiremetech.com/api/jobs/search"
_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": _UA,
    "Accept": "application/json",
    "Referer": "https://hiremetech.com/he-il/jobs",
}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _location_str(loc: Any) -> str:
    if not isinstance(loc, dict):
        return str(loc or "")
    basic = loc.get("basic") or {}
    return str(basic.get("display_name") or basic.get("city") or "")


def _is_remote(loc: Any) -> bool:
    if not isinstance(loc, dict):
        return False
    work_model = loc.get("work_model") or {}
    return bool(work_model.get("is_remote"))


class HiremetechSource:
    SOURCE = "hiremetech"

    def __init__(self, search_terms: list[str], max_pages: int = 5, page_size: int = 50) -> None:
        self.search_terms = search_terms
        self.max_pages = max_pages
        self.page_size = page_size

    def fetch(self) -> list[RawPosting]:
        seen: set[int] = set()
        postings: list[RawPosting] = []
        for term in self.search_terms:
            for page in range(1, self.max_pages + 1):
                resp = httpx.get(
                    BASE_URL,
                    params={"q": term, "page": page, "limit": self.page_size},
                    headers=HEADERS,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                jobs: list[dict[str, Any]] = data.get("jobs", [])
                if not jobs:
                    break
                for job in jobs:
                    jid: int = job["id"]
                    if jid in seen:
                        continue
                    seen.add(jid)
                    company: str = str(job.get("company_name") or "")
                    loc = job.get("location")
                    desc = (job.get("description") or "") + "\n" + (job.get("requirements") or "")
                    postings.append(
                        RawPosting(
                            source=self.SOURCE,
                            company=company,
                            company_slug=_slug(company) if company else "unknown",
                            title=str(job.get("title") or ""),
                            location=_location_str(loc),
                            url=str(job.get("job_url") or ""),
                            description=desc.strip(),
                            remote=_is_remote(loc),
                            raw=job,
                        )
                    )
                pagination = data.get("pagination") or {}
                if not pagination.get("has_more"):
                    break
        log.info("hiremetech: fetched %d unique postings", len(postings))
        return postings
