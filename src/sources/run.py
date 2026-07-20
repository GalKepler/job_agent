"""CLI entrypoint: fetch all configured sources and normalize into jobs.db."""

import logging
import os
import time
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from src.normalize import normalize
from src.sources.adzuna import AdzunaSource
from src.sources.arbeitnow import ArbeitnowSource
from src.sources.ashby import AshbySource
from src.sources.base import RawPosting
from src.sources.greenhouse import GreenhouseSource
from src.sources.hiremetech import HiremetechSource
from src.sources.lever import LeverSource
from src.sources.remotive import RemotiveSource

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SOURCES_CONFIG = Path("config/sources.yaml")


def _fetch(label: str, source: Any) -> list[RawPosting]:
    t0 = time.monotonic()
    posts: list[RawPosting] = source.fetch()
    log.info("%s: fetched %d postings in %.1fs", label, len(posts), time.monotonic() - t0)
    return posts


def run() -> None:
    load_dotenv()
    config: dict[str, Any] = yaml.safe_load(SOURCES_CONFIG.read_text())
    all_postings: list[RawPosting] = []

    for slug in config.get("greenhouse", []):
        all_postings.extend(_fetch(f"greenhouse/{slug}", GreenhouseSource(slug)))

    for slug in config.get("lever", []):
        all_postings.extend(_fetch(f"lever/{slug}", LeverSource(slug)))

    for slug in config.get("ashby", []):
        all_postings.extend(_fetch(f"ashby/{slug}", AshbySource(slug)))

    if remotive_cfg := config.get("remotive"):
        all_postings.extend(
            _fetch("remotive", RemotiveSource(remotive_cfg.get("search_terms", [])))
        )

    if adzuna_cfg := config.get("adzuna"):
        app_id = os.environ.get("ADZUNA_APP_ID", "")
        app_key = os.environ.get("ADZUNA_APP_KEY", "")
        if not app_id or not app_key:
            log.warning("adzuna: ADZUNA_APP_ID / ADZUNA_APP_KEY not set — skipping")
        else:
            all_postings.extend(
                _fetch(
                    "adzuna",
                    AdzunaSource(
                        countries=adzuna_cfg.get("countries", []),
                        search_terms=adzuna_cfg.get("search_terms", []),
                        app_id=app_id,
                        app_key=app_key,
                        results_per_page=adzuna_cfg.get("results_per_page", 50),
                        max_pages=adzuna_cfg.get("max_pages", 3),
                    ),
                )
            )

    if hiremetech_cfg := config.get("hiremetech"):
        all_postings.extend(
            _fetch(
                "hiremetech",
                HiremetechSource(
                    search_terms=hiremetech_cfg.get("search_terms", []),
                    max_pages=hiremetech_cfg.get("max_pages", 5),
                    page_size=hiremetech_cfg.get("page_size", 50),
                ),
            )
        )

    if arbeitnow_cfg := config.get("arbeitnow"):
        all_postings.extend(
            _fetch(
                "arbeitnow",
                ArbeitnowSource(
                    tags=arbeitnow_cfg.get("tags", []),
                    max_pages=arbeitnow_cfg.get("max_pages", 5),
                ),
            )
        )

    inserted, skipped = normalize(all_postings)
    log.info(
        "Done: total_fetched=%d inserted=%d skipped=%d",
        len(all_postings),
        inserted,
        skipped,
    )


if __name__ == "__main__":
    run()
