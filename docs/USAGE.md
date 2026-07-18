# Job Agent — Usage Guide

A practical walkthrough: first-time setup, daily use, and automation.

---

## How the pipeline works

```
sources.run  →  rank  →  match  →  generate  →  queue
     ↓             ↓         ↓          ↓            ↓
  jobs.db      ranked/    matched/   generated/   review/
              skipped    (+ conns)   (skill out)  YYYY-MM-DD.md
```

Each stage reads the previous stage's output from `jobs.db` and advances
postings through a state machine: `new → ranked → matched → generated → reviewed`.
Re-running any stage is safe — it only touches postings in the state it expects.

---

## First-time setup

### 1. Prerequisites

```bash
# Python 3.12+
python --version

# uv (package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Ollama (if using local models — skip if using Anthropic)
curl -fsSL https://ollama.ai/install.sh | sh
```

### 2. Install dependencies

```bash
cd job-agent
uv sync
```

### 3. Configure your LLM provider

**Option A — Anthropic (cloud, costs money, higher quality):**

In `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
LLM_PROVIDER=anthropic
```

Ranking uses `claude-haiku-4-5` (~$0.25/1M tokens). With 2000 postings per
run and ~1000 token prompts, a full rank pass costs roughly **$0.50**.
Generation uses `claude-sonnet-4-6` and only runs on postings that pass the
threshold — typically 50–150 postings per run.

**Option B — Ollama (local, free, slightly lower quality):**

```bash
ollama pull qwen2.5:7b    # ranking — reliable tool-use, fast
ollama pull llama3.1:8b   # generation — good long-form output
```

In `.env`:
```
LLM_PROVIDER=ollama
OLLAMA_RANK_MODEL=qwen2.5:7b
OLLAMA_GEN_MODEL=llama3.1:8b
```

> **Tip:** run a few real postings through Ollama before committing to it.
> `qwen2.5:7b` handles the structured scoring schema well; smaller models
> sometimes drop fields. If scores look off, switch to `qwen2.5:14b`.

### 4. Place your master CV

The generation step needs your CV to tailor against. Copy it to:

```bash
cp /path/to/your/cv.md data/master_cv.md
```

Format: plain Markdown. The `cv-tailoring` skill reads it directly.
The file is gitignored — it will never be committed.

### 5. Export your LinkedIn connections

In LinkedIn: **Settings → Data Privacy → Get a copy of your data → Connections**.
LinkedIn emails you a zip; extract `Connections.csv` and copy it:

```bash
cp ~/Downloads/Basic_LinkedInDataExport_.../Connections.csv data/Connections.csv
```

Also gitignored. Refresh every few weeks as your network grows.

### 6. Configure which companies to watch

Edit `config/sources.yaml`. Add company slugs under the right ATS:

```yaml
greenhouse:
  - deepmind
  - databricks
  - stripe          # add new companies here

ashby:
  - openai
  - cohere
  - your-new-company

lever:
  - atlassian
```

**Finding the slug:** it's the subdomain in the public board URL.
- Greenhouse: `https://boards.greenhouse.io/{slug}/jobs`
- Lever: `https://jobs.lever.co/{slug}`
- Ashby: `https://jobs.ashbyhq.com/{slug}`

If a company isn't on any of these three, it's not yet supported (a custom
scraper is needed — see `docs/adr/001-source-strategy.md`).

### 7. Tune your profile

`config/profile.yaml` is what the ranker scores every posting against.
Key fields to review:

- `level.anchor` — your seniority anchor (`senior_ic` by default)
- `target_roles` — role families and their weights
- `signals_positive` / `signals_negative` — domain keywords
- `dealbreakers` — hard-flag conditions (junior, people-management, relocation)
- `ranking.threshold_advance` — minimum final score to pass (default 6/10)
- `active_processes` — companies where you're already mid-process

### 8. Verify the setup

```bash
uv run pytest          # all tests green
uv run ruff check src/ # no lint errors
```

---

## Running the pipeline

### Stage by stage (recommended the first time)

**Stage 1 — Fetch postings:**
```bash
uv run python -m src.sources.run
```
Fetches all configured sources into `data/jobs.db`. Idempotent — re-running
only inserts new postings not already in the DB.

Expected output:
```
greenhouse/deepmind: fetched 10 postings in 0.3s
ashby/openai: fetched 724 postings in 6.1s
Done: total_fetched=2003 inserted=47 skipped=1956
```

**Stage 2 — Rank:**
```bash
uv run python -m src.rank
```
Scores every `new` posting with the LLM. Posts scoring ≥ 6 become `ranked`;
below-threshold posts become `skipped` (kept in DB with rationale for auditing).

Expected output (one line per posting):
```
rank: id=123 'Research Scientist' @ Cohere — score=9 level=match dealbreakers=none → ranked
rank: id=456 'Junior ML Engineer' @ Startup — score=4 level=junior dealbreakers=['junior_level'] → skipped
Ranked 47 postings.
```

**Stage 3 — Match to your network:**
```bash
uv run python -m src.match
```
Fuzzy-matches company names against `data/Connections.csv`. All `ranked`
postings advance to `matched` — even with zero connections (they'll get the
cold-application path in the queue).

```
match: loaded 1531 connections with a company
match: id=123 'Research Scientist' @ Cohere — 2 connection(s) found
Matched 8 postings.
```

**Stage 4 — Generate tailoring packages:**
```bash
uv run python -m src.generate
```
Calls the cv-tailoring skill for each `matched` posting. Produces: level
verdict, gap analysis table, CV edit list, and (if connections exist) a
referral outreach draft. This is the slowest and most expensive step —
budget ~30 seconds and ~$0.05 per posting with Sonnet.

```
generate: id=123 'Research Scientist' @ Cohere — done
Generated 8 postings.
```

**Stage 5 — Write the review queue:**
```bash
uv run python -m src.queue
```
Renders all `generated` postings to `review/YYYY-MM-DD.md`, sorted by
relevance score descending.

```
queue: wrote 8 posting(s) to review/2026-07-18.md
```

### One-shot (after the first run)

Once you trust the output, run all five in sequence:
```bash
uv run python -m src.sources.run && \
uv run python -m src.rank && \
uv run python -m src.match && \
uv run python -m src.generate && \
uv run python -m src.queue
```

---

## Reading the review queue

Open `review/YYYY-MM-DD.md`. Each posting looks like this:

```markdown
## Cohere — Research Scientist

**Score:** 9/10 | **Level match:** match | **Status:** generated
**URL:** https://jobs.ashbyhq.com/cohere/...
**Location:** Remote

**Ranker rationale:** Strong NLP/LLM domain fit; end-to-end research-to-prod signal.

### Network connections
  - [Jane Doe](https://linkedin.com/in/janedoe) — Senior Researcher

### CV tailoring output
## Verdict
Strong fit. Role is Senior IC in NLP/LLM — squarely in your target band.
Apply after tailoring.

## Gap analysis
| Requirement | Evidence from CV | Strength |
|---|---|---|
| Transformer fine-tuning | BrainLink encoder, TAU course | strong |
| Production serving | Shipped SNBB platform (~4500 participants) | strong |
| RLHF / eval | Six-check eval harness | partial |
...

## CV edits
...

- [ ] Apply
- [ ] Skip
- [ ] Send outreach
```

**Your workflow:**
1. Read the verdict and score — quick yes/no on whether to spend time on it
2. Check the gap table — anything you'd need to address in a cover letter
3. Review the CV edits — copy the ones you agree with into your actual CV
4. If a connection is listed and you want a referral, copy the outreach draft
   into LinkedIn → message. **Nothing is sent automatically.**
5. Tick the checkbox and update the DB manually if you want to track it:
   ```bash
   uv run python -c "
   from src.db import get_engine, Posting
   from sqlalchemy.orm import Session
   engine = get_engine()
   with Session(engine) as s:
       p = s.get(Posting, 123)   # use the posting id
       p.status = 'reviewed'
       s.commit()
   "
   ```

---

## Daily automation

### Option A — local cron

Run daily at 8am:
```bash
crontab -e
```

Add:
```cron
0 8 * * * cd /home/groot/Projects/job-agent && \
  /home/groot/.local/bin/uv run python -m src.sources.run && \
  /home/groot/.local/bin/uv run python -m src.rank && \
  /home/groot/.local/bin/uv run python -m src.match && \
  /home/groot/.local/bin/uv run python -m src.generate && \
  /home/groot/.local/bin/uv run python -m src.queue \
  >> /tmp/job-agent.log 2>&1
```

Check the log with `tail -f /tmp/job-agent.log`.

> **Ollama note:** Ollama must be running before the cron fires.
> Add `ollama serve &` to your startup, or run it as a systemd service:
> ```bash
> sudo systemctl enable ollama
> sudo systemctl start ollama
> ```

### Option B — shell alias for manual daily run

Add to `~/.zshrc`:
```bash
alias job-run='cd /home/groot/Projects/job-agent && \
  uv run python -m src.sources.run && \
  uv run python -m src.rank && \
  uv run python -m src.match && \
  uv run python -m src.generate && \
  uv run python -m src.queue && \
  echo "Done — check review/$(date +%Y-%m-%d).md"'
```

Then just type `job-run` over morning coffee.

### Option C — GitHub Actions (requires private repo)

Create `.github/workflows/daily.yml`:
```yaml
name: Daily job scan
on:
  schedule:
    - cron: '0 6 * * *'   # 6am UTC = 8am Israel time
  workflow_dispatch:        # allow manual trigger

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3

      - name: Install deps
        run: uv sync

      - name: Run pipeline
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          # Note: Ollama won't work on GitHub runners — use Anthropic here
        run: |
          uv run python -m src.sources.run
          uv run python -m src.rank
          uv run python -m src.match
          # Skip generate/queue on CI unless you commit master_cv.md
          # (which you should NOT do — it's gitignored for good reason)

      - name: Commit updated DB
        run: |
          git config user.email "bot@job-agent"
          git config user.name "job-agent-bot"
          # DB is gitignored — push only a summary artifact if needed
```

> **Limitation:** `data/master_cv.md` and `data/Connections.csv` are
> gitignored, so stages 4 and 5 (generate + queue) can't run on CI
> without those files. For full automation on CI, you'd need to store
> them as encrypted secrets and restore them at runtime — more complexity
> than it's worth for a personal tool. Easier: run stages 4–5 locally
> after CI runs 1–3.

---

## Maintenance

### Adding a new company

1. Find its ATS and slug (check the URL on their careers page)
2. Add to `config/sources.yaml` under the right section
3. Run `uv run python -m src.sources.run` — only new postings insert

### Updating your network

Re-export from LinkedIn every 2–4 weeks (your network grows, people change
companies). Replace `data/Connections.csv` and re-run `src.match` — it
only processes `ranked` postings, so only new ones get re-matched.

If you want to re-match already-matched postings after a fresh CSV:
```bash
uv run python -c "
from src.db import get_engine, Posting
from sqlalchemy.orm import Session
engine = get_engine()
with Session(engine) as s:
    s.query(Posting).filter(Posting.status == 'matched').update({'status': 'ranked'})
    s.commit()
print('Reset matched → ranked')
"
uv run python -m src.match
```

### Updating your profile

Edit `config/profile.yaml` freely — it's re-read on every rank run.
To re-rank already-skipped postings after tightening/loosening criteria:
```bash
uv run python -c "
from src.db import get_engine, Posting
from sqlalchemy.orm import Session
engine = get_engine()
with Session(engine) as s:
    s.query(Posting).filter(Posting.status == 'skipped').update({'status': 'new'})
    s.commit()
print('Reset skipped → new for re-ranking')
"
uv run python -m src.rank
```

### Auditing what the ranker filtered

```bash
uv run python -c "
from src.db import get_engine, Posting
from sqlalchemy.orm import Session
from sqlalchemy import select
import json
engine = get_engine()
with Session(engine) as s:
    skipped = s.scalars(select(Posting).where(Posting.status == 'skipped')).all()
    for p in skipped:
        hits = json.loads(p.dealbreakers_hit or '[]')
        print(f'{p.score:2d} | {p.company:20s} | {p.title:40s} | {hits or p.rationale}')
" 2>/dev/null
```

---

## Troubleshooting

**`ModuleNotFoundError`** — run with `uv run`, not plain `python`.

**Ollama tool-call failures** (`No score_posting block`) — the model
produced malformed JSON. Switch to `qwen2.5:14b` or `llama3.1:70b` if
you have enough RAM, or fall back to Anthropic for ranking.

**Source returns 0 postings** — the company slug is wrong or the company
moved to a different ATS. Check their current careers page URL.

**Score 0 on obviously relevant postings** — the description is truncated
(capped at 3000 chars). The posting's full text might be loaded client-side;
the API only returned a stub. Nothing to do — check the posting URL manually.

**`data/master_cv.md not found`** — stage 4 (generate) exits early without
this file. Place your CV there and re-run.

**DB locked** — another run is in progress, or a previous run crashed mid-
write. WAL mode handles concurrent readers fine, but only one writer at a
time. Kill the other process and retry.
