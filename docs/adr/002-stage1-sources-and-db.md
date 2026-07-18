# ADR 002 — Stage 1: Source adapters and database schema

## Context

Need to fetch job postings from Greenhouse, Lever, and Ashby without scraping and persist them idempotently for ranking in Stage 2.

## Decision

**Source adapters** each implement the `Source` protocol (`fetch() -> list[RawPosting]`). One file per ATS platform. HTTP via `httpx` (synchronous; async not needed at this scale).

**Dedup key** is `SHA-256(company_slug | title.lower | location.lower)`. Covers the common case of a re-run pulling the same posting. Stored as `dedup_hash` with a UNIQUE index; inserts use `ON CONFLICT DO NOTHING`.

**DB** is SQLite in WAL mode via SQLAlchemy 2.0 ORM. Status column drives the pipeline state machine (`new → ranked → matched → generated → reviewed → applied | skipped`). `raw_json` stores the full original payload for auditability.

**`normalize()`** accepts an optional `engine` argument so tests can pass a tmp-path DB without monkeypatching globals.

## Consequences

- Re-running any stage is idempotent — no duplicate rows.
- Rejected postings are retained with status; nothing is silently dropped.
- Descriptions arrive as raw HTML from Greenhouse/Ashby. Stage 2 ranker receives HTML in the prompt; strip at that layer if token cost is a concern.
- Adding a new ATS source is one new file implementing the protocol + a key in `config/sources.yaml`.
