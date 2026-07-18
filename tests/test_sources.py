"""Source adapter tests — no network; all HTTP mocked via pytest-httpx."""

import json
from pathlib import Path

from pytest_httpx import HTTPXMock

from src.sources.ashby import AshbySource
from src.sources.greenhouse import GreenhouseSource
from src.sources.lever import LeverSource

FIXTURES = Path("tests/fixtures")


def test_greenhouse_fetch(httpx_mock: HTTPXMock) -> None:
    fixture = json.loads((FIXTURES / "greenhouse_apple.json").read_text())
    httpx_mock.add_response(
        url="https://boards-api.greenhouse.io/v1/boards/apple/jobs",
        json=fixture,
    )
    postings = GreenhouseSource("apple").fetch()
    assert len(postings) == 2
    assert postings[0].title == "Interdisciplinary Researcher"
    assert postings[0].source == "greenhouse"
    assert postings[0].company_slug == "apple"
    assert postings[0].remote is False
    assert postings[1].remote is True  # "Remote" in location


def test_lever_fetch(httpx_mock: HTTPXMock) -> None:
    fixture = json.loads((FIXTURES / "lever_waze.json").read_text())
    httpx_mock.add_response(
        url="https://api.lever.co/v0/postings/waze?mode=json",
        json=fixture,
    )
    postings = LeverSource("waze").fetch()
    assert len(postings) == 1
    assert postings[0].title == "Senior Data Scientist"
    assert postings[0].source == "lever"
    assert postings[0].location == "Tel Aviv, Israel"
    assert "predictive models" in postings[0].description


def test_ashby_fetch(httpx_mock: HTTPXMock) -> None:
    fixture = json.loads((FIXTURES / "ashby_aidoc.json").read_text())
    httpx_mock.add_response(
        url="https://api.ashbyhq.com/posting-api/job-board/aidoc",
        json=fixture,
    )
    postings = AshbySource("aidoc").fetch()
    assert len(postings) == 2
    assert postings[0].title == "Research Scientist"
    assert postings[0].source == "ashby"
    assert postings[0].remote is False
    assert postings[1].remote is True  # isRemote=true
