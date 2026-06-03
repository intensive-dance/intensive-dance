"""Run scrapers and write the committed JSON store.

    uv run python -m intensive_dance.run                  # all providers
    uv run python -m intensive_dance.run royal-ballet-school   # one provider

Each provider's validated offerings are written to data/<slug>.json. The store
is deterministic (sorted keys, stable hashes) so a re-scrape of unchanged
content produces no git diff — same ethos as museumsufer's committed data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from intensive_dance.fetch import make_client
from intensive_dance.scrapers import SCRAPERS

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def write_provider(slug: str, offerings: list) -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / f"{slug}.json"
    payload = [o.model_dump(by_alias=True, mode="json", exclude_none=True) for o in offerings]
    out.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return out


def main(argv: list[str]) -> int:
    slugs = argv or list(SCRAPERS)
    unknown = [s for s in slugs if s not in SCRAPERS]
    if unknown:
        print(f"unknown provider(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    client = make_client()
    failures = 0
    try:
        for slug in slugs:
            try:
                offerings = SCRAPERS[slug](client)
            except NotImplementedError as exc:
                print(f"skip {slug}: {exc}", file=sys.stderr)
                continue
            except Exception as exc:  # noqa: BLE001 — one provider must not abort the rest
                print(f"FAIL {slug}: {exc}", file=sys.stderr)
                failures += 1
                continue
            for offering in offerings:
                offering.source.hash = offering.content_hash()
            path = write_provider(slug, offerings)
            print(f"ok {slug}: {len(offerings)} offering(s) -> {path}")
    finally:
        client.close()

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
