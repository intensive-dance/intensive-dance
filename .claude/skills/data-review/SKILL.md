---
name: data-review
description: Review scraped offerings in the committed data store for quality issues — wrong/invented fields, mis-attributed auditions, leaked genres, folded sessions, stale dates — grounding each suspect field against the live web via Gemini search. Use when triaging a "data review:" GitHub issue, auditing a provider's data/<slug>.json, or asked to check whether scraped data matches the source. Self-extends its pattern catalog when it finds a new class of issue.
---

# Data review

Find and fix data-quality issues in the committed store (`data/<slug>.json`) —
the kind a human flags with the review UI (`review/index.html`) and files as a
`data review: …` issue (e.g. #258). A scraper can run green and still ship
*wrong* data: a field that parsed cleanly but means the wrong thing. This skill
is the cross-check that fetches reality and compares.

This is **review/enrichment work, never the scrape path** — it is allowed to use
the network and an LLM. Any fix lands in the scraper + regenerated data behind
the normal gate; the LLM never enters `scrape()`/CI (AGENTS.md, "LLM access").

## When to use

- A `data review: <provider> — N offering(s) flagged` issue needs working.
- Auditing one provider's `data/<slug>.json` (or a batch) for correctness.
- "Does the scraped data actually match the source?" / "is this field right?"

This is correctness review of *already-scraped* data. For "a live provider has
**zero** offerings", that's the structural audit (`intensive_dance.audit`) —
different failure mode, handled by the self-healing loop.

## Search grounding (Gemini via the AI proxy)

Verify a suspect field against the live web instead of trusting the store.
Grounding works **only** on the proxy's native Gemini endpoint, wrapped by the
helper here:

```bash
export AI_PROXY_URL=$(gh variable get AI_PROXY_URL)   # token is baked into the path
python3 .claude/skills/data-review/ground.py "Does <provider> require a video audition for its <year> summer intensive, and what poses/exercises?"
```

It prints the answer, the searches Gemini ran, and the **real source URLs** —
use those to confirm a claim is sourced, not hallucinated. Ground for facts
("what are the dates/fees/requirements"); treat the model's prose as a lead to
verify against the cited page, not as truth. For the exact page the scraper
reads, also fetch it directly (the fetch proxy / `client.get`) and compare.
`--json` emits `{text, queries, sources}` for programmatic use.

## Review workflow

1. **Scope.** From the issue (or a chosen slug), list the offerings and the
   flagged fields. Load `data/<slug>.json` and read the scraper module +
   docstring (`src/intensive_dance/scrapers/<slug_with_underscores>.py`) so you
   know *how* each field was derived — the bug is usually in that derivation.
2. **Walk the catalog.** Run each offering's fields against `PATTERNS.md`. For
   every suspect field, form the specific question it raises.
3. **Ground / fetch.** Confirm each suspect against the live source — `ground.py`
   for "what does the web say", a direct fetch for "what does the exact scraped
   page say". A field is only wrong once a source contradicts it; "looks odd" is
   a lead, not a finding. Respect the data ethos: `null`/`[]` = "not stated" is
   *correct*, not a gap — don't invent to fill it (faithful, fail open).
4. **Decide per field:** confirmed-correct · genuinely-not-stated (leave unset) ·
   wrong (fix). Keep ended/cancelled cycles (IDR-24) — out of scope.
5. **Fix at the source — the scraper, not the JSON.** Adjust the parsing helper,
   add a test pinning the corrected behaviour, regenerate
   (`uv run python -m intensive_dance.run <slug>`), and run the full gate
   (`ruff check .` · `ruff format .` · `ty check` · `pytest -q` · `schema` ·
   `validate`). Update the module docstring if the source shape was
   misunderstood. Never hand-edit `data/<slug>.json` (the hash check fails, and
   the next scrape reverts it).
6. **Report.** Summarise per offering: field → verdict → evidence (cite the
   grounded/fetched source URL) → fix. If working an issue, comment the findings
   and close it when the fix PR merges.
7. **Extend the catalog** if you found a new issue class (below).

## Extending this catalog (self-improvement — do this)

Whenever a review surfaces a scraping/data issue whose **shape** isn't already
in `PATTERNS.md`, append a new `## P<n> — <short name>` entry in the same
format: **Wrong** (what the bad data looks like) · **Spot it** (the store-side
tell, ideally something greppable across `data/*.json`) · **Confirm** (the
grounding/fetch question that settles it) · **Fix** · `(Origin: <issue/provider>)`.
Refine an existing entry rather than duplicating it. This is a required part of
closing out a review that found something new — the catalog is the asset.

If the learning is also a *scraper-building* trap (not just a review tell),
mirror a one-liner into `AGENTS.md`'s "Conventions & traps" in the same PR, per
its keep-current rule.
