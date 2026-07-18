# job-agent — Project Rules

Semi-autonomous job-search pipeline: pull postings from public job-board APIs, rank them against my profile, match them to my exported LinkedIn network, tailor my CV per role, and draft outreach. Everything lands in a human review queue. **Nothing is ever sent automatically.**

Full staged plan: `docs/job-agent-plan.md`. Read it before starting a new stage.

---

## Hard rules (non-negotiable)

1. **Never send anything.** No emails, no LinkedIn messages, no API calls that deliver a message to a human. The pipeline writes *drafts* to `review/`. Sending is a manual human action, always. If a task seems to require sending, stop and ask.
2. **No LinkedIn scraping.** No headless browsers, no `linkedin.com` HTTP calls, no unofficial LinkedIn API wrappers, ever. Job postings come from Greenhouse / Lever / Ashby public APIs, company careers pages, or a paid aggregator. Network data comes only from my manual LinkedIn CSV export at `data/connections.csv`.
3. **Personal data stays out of git.** `data/connections.csv`, `data/master_cv.md`, `data/jobs.db`, and `review/` are gitignored. Never commit them, never paste their contents into a commit message, issue, or log.
4. **No invented CV content.** CV tailoring is delegated to the `cv-tailoring` skill, which forbids fabricating achievements or metrics. Don't reimplement tailoring logic in Python — call the skill.
5. **No network calls in unit tests.** Use recorded fixtures in `tests/fixtures/`.

---

## Stack & conventions

- Python 3.12+, `uv` for env/deps.
- **ruff** for lint + format. **pytest** for tests. Type hints on all public functions; `mypy --strict` on `src/`.
- SQLite via SQLAlchemy 2.0, **WAL mode**, real transactions. State transitions are ACID — no mutable-file-as-state-store (learned that lesson on SNBB Scheduler).
- Config in YAML under `config/`, never hardcoded. Secrets via env vars, never in the repo.
- Pydantic models for anything crossing a module boundary (postings, scores, matches).

## Code style

- Small, testable modules. Each source is its own module implementing the `Source` protocol in `src/sources/base.py`.
- Prefer explicit over clever. Fail loudly with useful messages — a silent partial fetch that logs nothing is worse than a crash.
- Idempotency is a requirement, not a nice-to-have: re-running any stage must not duplicate rows or re-generate existing artifacts.
- Log every external fetch (source, count, duration). I need to be able to audit what the pipeline saw.

## Workflow

- **One stage per session.** Each stage in the plan has a checkpoint — don't advance until it passes.
- Before writing code for a stage, restate the plan for that stage and the checkpoint, and wait for my go-ahead.
- Append an entry to `docs/adr/` for any architectural decision (source selection, schema change, ranking approach, dedup strategy). Format: context / decision / consequences.
- Run `ruff check --fix && ruff format && pytest && mypy src/` before declaring a stage done.
- Commit per logical unit with conventional-commit messages (`feat(sources): add lever adapter`).

## Pipeline state machine

Postings in `jobs.db` move through: `new → ranked → matched → generated → reviewed → applied | skipped`.

Rules:
- Never skip a state. Never mutate backwards except via an explicit `--reset` flag.
- Rejected postings are retained with their rejection rationale — I want to audit what the ranker filtered out, not have it silently disappear.

## Ranking guardrails

The ranker reads `config/profile.yaml`. It must **hard-flag and down-rank**:
- Junior / entry-level / 0–2 years roles (I've been rejected for overqualification before; these waste time)
- People-management roles with direct reports (no direct-report experience — flag and check for a parallel IC track)

My anchor is **mid-to-senior IC**. If a role's inferred level is below that, it needs an explicit reason to survive the filter.

## What to ask me about

- Adding a new job source (I want to approve the source's legal status first)
- Anything that touches `connections.csv` semantics
- Any change to the "never send" boundary — the answer will be no, but ask rather than assume
