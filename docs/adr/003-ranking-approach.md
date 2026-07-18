# ADR 003 — Stage 2 ranking approach

## Context

Need to score `new` postings for fit before they flood the review queue.
The profile already encodes level anchor, target role families, positive/negative signals,
and dealbreakers (junior roles, people-management, relocation-required).

## Decision

**LLM tool_use per posting** — Claude Haiku via `client.messages.create` with a
`score_posting` tool that forces structured output:
`relevance_score (0-10)`, `level_match (junior|match|stretch)`, `one_line_rationale`,
`dealbreakers_hit (list[id])`.

Penalty per dealbreaker (`hard_flag_penalty = -4`) applied in Python after the LLM call,
so the LLM only detects and the pipeline decides.

Postings below `threshold_advance (6)` → `skipped` with score and rationale retained.
All scored postings stay in DB (no deletes); skipped ones are auditable.

Model: Haiku. Cheap enough for per-posting calls (~50 roles/run). Swap to Sonnet
if score quality is poor in practice.

## Consequences

- Any posting that fails the LLM call is logged and left as `new` (retried next run).
- Dealbreaker detection is done by the LLM reading the posting text, not keyword matching
  in Python — more robust but could miss subtle wording. Audit the first few runs.
- Idempotent: re-running `rank_postings` on an already-ranked DB is a no-op (only
  `status == 'new'` rows are processed).
