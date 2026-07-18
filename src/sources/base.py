"""Source protocol and shared posting schema."""

from typing import Any, Protocol

from pydantic import BaseModel


class RawPosting(BaseModel):
    source: str  # "greenhouse" | "lever" | "ashby" | ...
    company: str
    company_slug: str
    title: str
    location: str
    url: str
    description: str
    remote: bool = False
    raw: dict[str, Any]  # full original payload


class Source(Protocol):
    def fetch(self) -> list[RawPosting]: ...
