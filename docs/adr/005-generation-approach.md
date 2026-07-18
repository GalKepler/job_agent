# ADR 005 — Generation approach (Stage 4)

## Context

For each matched posting we need a structured package: a level verdict, gap analysis, CV edit list, and optionally an outreach draft. This logic must not live in `generate.py` — CLAUDE.md delegates all tailoring to the `cv-tailoring` skill to avoid reimplementing it in Python and to keep the "no invented CV content" rule in one place.

## Decision

- **Skill invocation:** `generate.py` reads `SKILL.md` and `references/positioning.md` from `skills/cv-tailoring.skill` (a zip) at runtime via `zipfile`, uses `SKILL.md` as the system prompt, and sends a single user message with posting text + master CV + positioning reference + connections list.
- **Model:** `claude-sonnet-4-6`. This is the document-generation step (highest user value per call); haiku is reserved for the cheap, high-volume ranking step.
- **Master CV path:** `data/master_cv.md` (gitignored). If absent, `generate_postings()` warns and returns 0 — the user must place the file before running Stage 4.
- **Output storage:** raw markdown text from the LLM stored in `postings.generated_content`. Not parsed or structured further — the queue renderer renders it as-is.
- **Outreach draft:** requested in the user message when connections are present. The skill includes outreach templates in `references/outreach.md` and the output is a draft only — never sent.
- **Status transition:** `matched → generated` on success. Failures log a warning and continue; the posting stays at `matched` for retry.

## Consequences

- Skill prompt updates automatically flow through without code changes.
- `generated_content` is freeform markdown; the queue renderer treats it as an opaque block. If structured output is needed later (e.g., to auto-apply edits to the master CV), a tool-use call with a structured schema would be the upgrade path.
- Without `master_cv.md`, Stage 4 is a no-op. This is intentional — the skill explicitly forbids fabricating CV content.
