"""CLI entrypoint: fetch all configured sources and normalize into jobs.db."""

import logging
import time
from pathlib import Path
from typing import Any

import yaml

from src.normalize import normalize
from src.sources.ashby import AshbySource
from src.sources.base import RawPosting
from src.sources.greenhouse import GreenhouseSource
from src.sources.lever import LeverSource

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SOURCES_CONFIG = Path("config/sources.yaml")


def _fetch(label: str, source: Any) -> list[RawPosting]:
    t0 = time.monotonic()
    posts: list[RawPosting] = source.fetch()
    log.info("%s: fetched %d postings in %.1fs", label, len(posts), time.monotonic() - t0)
    return posts


def run() -> None:
    config: dict[str, list[str]] = yaml.safe_load(SOURCES_CONFIG.read_text())
    all_postings: list[RawPosting] = []

    for slug in config.get("greenhouse", []):
        all_postings.extend(_fetch(f"greenhouse/{slug}", GreenhouseSource(slug)))

    for slug in config.get("lever", []):
        all_postings.extend(_fetch(f"lever/{slug}", LeverSource(slug)))

    for slug in config.get("ashby", []):
        all_postings.extend(_fetch(f"ashby/{slug}", AshbySource(slug)))

    inserted, skipped = normalize(all_postings)
    log.info(
        "Done: total_fetched=%d inserted=%d skipped=%d",
        len(all_postings),
        inserted,
        skipped,
    )


if __name__ == "__main__":
    run()
