# ADR 001 — Job source strategy

**Context:** Need to pull job postings at scale without scraping LinkedIn (ToS risk, ban risk mid-interview-process) and without paying for an aggregator in v1.

**Decision:** Use Greenhouse, Lever, and Ashby public JSON board APIs as primary sources. These cover the majority of tech companies and expose machine-readable endpoints with no authentication required. Company careers pages (HTML fetch + parse) are a fallback for companies not on those ATSes. No LinkedIn job scraping, ever.

**Consequences:**
- Positive: legal by construction, stable endpoints, JSON output needs minimal parsing.
- Positive: adding a new company is one line in `config/sources.yaml`.
- Negative: companies that self-host or use other ATSes (Workday, Greenhouse Enterprise) require bespoke modules.
- Negative: company name canonicalisation needed — Greenhouse slug "checkout-com" ≠ CSV company "Checkout.com".
