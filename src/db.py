"""SQLAlchemy engine + Posting ORM model. WAL mode, ACID state transitions."""

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, String, Text, create_engine, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DB_PATH = Path("data/jobs.db")


class Base(DeclarativeBase):
    pass


class Posting(Base):
    __tablename__ = "postings"

    id: Mapped[int] = mapped_column(primary_key=True)
    dedup_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(32))
    company: Mapped[str] = mapped_column(String(256))
    company_slug: Mapped[str] = mapped_column(String(256))
    title: Mapped[str] = mapped_column(String(512))
    location: Mapped[str] = mapped_column(String(256))
    url: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    remote: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(32), default="new")
    raw_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def get_engine(db_path: Path = DB_PATH) -> Any:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.commit()
    Base.metadata.create_all(engine)
    return engine


def make_dedup_hash(company_slug: str, title: str, location: str) -> str:
    key = f"{company_slug}|{title.lower().strip()}|{location.lower().strip()}"
    return hashlib.sha256(key.encode()).hexdigest()
