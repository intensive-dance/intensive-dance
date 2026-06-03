# intensive.dance

A worldwide register of **intensive courses and master classes** for **classical** and **contemporary ballet**, scraped from the schools and companies that run them.

> Working name. First milestone: scrape intensives into our DB. Nothing user-facing yet.

## What we collect

For every intensive / master class we care about:

- **Time range** — when it runs (start/end, plus the year's "season")
- **Organization** — the school or company hosting it
- **Teachers** — who teaches, and *where they actually teach and dance* (their affiliations)
- **Prices** — tuition and what's included, in the local currency
- **Application deadlines**
- **Application requirements** — none · photos in defined poses · video (specific or open brief) · CV · headshots/portraits

## Provider register

We maintain a register of providers to scrape, weighted toward the marquee names in the genre — e.g. The Royal Ballet School, John Cranko School, ABT (JKO School), Joffrey Ballet School, l'École de Danse de l'Opéra de Paris, English National Ballet School, Bolshoi Ballet Academy.

See [`providers.json`](./providers.json) for the seed list and [`docs/data-model.md`](./docs/data-model.md) for the record shape.

## Status

Phase 1 — define the data model and land the first scraper (The Royal Ballet School). See the open issues.
