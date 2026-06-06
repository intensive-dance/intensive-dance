"""Pick the N least-recently-*attempted* scrapers for the hourly CI rotation.

Rotation orders by `source.attemptedAt` (last fetch attempt), not `scrapedAt`
(last content change) — the latter is reused on no-op scrapes, so a static-
content provider would otherwise be re-picked forever and starve the rotation.
A never-attempted provider sorts first; ties break on slug for determinism.

    uv run python -m intensive_dance.rotation 10   # JSON array for the Actions matrix
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from intensive_dance.scrapers import SCRAPERS

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _last_attempt(slug: str, data_dir: Path) -> datetime | None:
    path = data_dir / f"{slug}.json"
    if not path.exists():
        return None
    try:
        records = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    stamps = [
        record["source"]["attemptedAt"]
        for record in records
        if record.get("source", {}).get("attemptedAt")
    ]
    if not stamps:
        return None
    return max(datetime.fromisoformat(stamp) for stamp in stamps)


def select_stale(n: int, *, slugs: list[str] | None = None, data_dir: Path = DATA_DIR) -> list[str]:
    candidates = list(SCRAPERS) if slugs is None else slugs
    return sorted(candidates, key=lambda slug: (_last_attempt(slug, data_dir) or EPOCH, slug))[:n]


def main(argv: list[str]) -> int:
    n = int(argv[0]) if argv else 10
    print(json.dumps(select_stale(n)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
