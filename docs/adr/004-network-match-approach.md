# ADR 004 — Network matching approach (Stage 3)

## Context

For each ranked posting, we want to surface LinkedIn connections who work at the same company, ranked by referral warmth. The connection data is a manual LinkedIn CSV export (`data/connections.csv`). Company names in the CSV and the posting DB differ in common ways ("Apple Inc." vs "Apple", "Meta Platforms" vs "Meta").

## Decision

- **Source:** LinkedIn CSV export only. No API, no scraping. User re-exports as needed.
- **Matching:** `rapidfuzz.fuzz.ratio` with a threshold of 80 (0–100 scale), applied to normalized company names. Normalization strips common legal suffixes (Inc., Ltd., LLC, Platforms, Technologies, etc.) and lowercases.
- **Warmth proxy:** count of seniority keywords (senior, staff, principal, director, VP, head, chief, lead) in the connection's position title. Higher count → ranked first among matches.
- **Top N:** cap at 5 connections per posting — enough for one outreach, not a wall of names.
- **No match is not a blocker:** postings with zero connections still advance to `matched` (with an empty list), taking the cold-application path in generation.
- **All ranked postings advance:** status `ranked → matched` unconditionally (after the CSV is present).

## Consequences

- Company name normalization catches the common variants but may miss unusual divergences (e.g., "Checkout.com" vs "Checkout"). Re-running after updating `_STRIP_SUFFIXES` is safe (idempotent — re-run only processes `ranked` rows).
- Warmth is a rough heuristic. A senior connection at a different team may be less useful than a junior one in the exact org. The review queue shows position title so the user can override.
- `rapidfuzz` is already in `pyproject.toml`; no new dep.
