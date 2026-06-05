"""Validate the committed data store — CI's network-free check.

Every file under data/ must parse as a list of `Offering`, and each offering's
stored `source.hash` must equal a freshly recomputed `content_hash()`. A
mismatch means the committed data drifted from the models (e.g. a model change
without a re-scrape).

    uv run python -m intensive_dance.validate
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from intensive_dance.models import Offering

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def main() -> int:
    files = sorted(DATA_DIR.glob("*.json"))
    if not files:
        print("no data files under data/", file=sys.stderr)
        return 1

    errors: list[str] = []
    total = 0
    for path in files:
        try:
            records = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}: invalid JSON — {exc}")
            continue
        for record in records:
            total += 1
            try:
                offering = Offering.model_validate(record)
            except Exception as exc:  # noqa: BLE001 — report, don't abort the file
                errors.append(f"{path.name}: {record.get('id', '?')} failed validation — {exc}")
                continue
            expected = offering.content_hash()
            if offering.source.hash != expected:
                errors.append(
                    f"{path.name}: {offering.id} stale hash "
                    f"(stored {offering.source.hash}, expected {expected}) — re-scrape needed"
                )

    for error in errors:
        print(f"FAIL {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"ok: {total} offering(s) across {len(files)} file(s) valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
