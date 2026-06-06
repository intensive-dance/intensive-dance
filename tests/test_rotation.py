"""Unit tests for the hourly-rotation selection.

`select_stale` orders providers by `source.attemptedAt`: never-attempted first
(missing file or missing field), then oldest attempt, slug as the tie-break. No
network, no real data/ — every fixture is written into a tmp dir.
"""

from __future__ import annotations

import json
from pathlib import Path

from intensive_dance.rotation import select_stale


def _write(data_dir: Path, slug: str, attempted_at: str | None) -> None:
    source = {"provider": slug, "url": "https://x", "scrapedAt": "2026-01-01T00:00:00Z"}
    if attempted_at is not None:
        source["attemptedAt"] = attempted_at
    record = {"id": f"{slug}/x", "title": "x", "source": source}
    (data_dir / f"{slug}.json").write_text(json.dumps([record]))


def test_orders_never_attempted_then_oldest(tmp_path: Path) -> None:
    _write(tmp_path, "recent", "2026-06-06T10:00:00Z")
    _write(tmp_path, "older", "2026-06-01T10:00:00Z")
    _write(tmp_path, "no-field", None)  # has a file but no attemptedAt → never attempted
    # "missing" has no file at all → also never attempted.

    slugs = ["recent", "older", "no-field", "missing"]
    picked = select_stale(4, slugs=slugs, data_dir=tmp_path)

    # never-attempted (slug tie-break) come first, then oldest-attempt, then recent.
    assert picked == ["missing", "no-field", "older", "recent"]


def test_n_truncates(tmp_path: Path) -> None:
    for slug, stamp in [("a", "2026-06-06T00:00:00Z"), ("b", "2026-06-05T00:00:00Z")]:
        _write(tmp_path, slug, stamp)
    assert select_stale(1, slugs=["a", "b"], data_dir=tmp_path) == ["b"]


def test_uses_most_recent_attempt_per_provider(tmp_path: Path) -> None:
    """A provider's last attempt is the max attemptedAt across its offerings."""
    records = [
        {
            "id": "multi/old",
            "title": "x",
            "source": {
                "provider": "multi",
                "url": "u",
                "scrapedAt": "2026-01-01T00:00:00Z",
                "attemptedAt": "2026-01-01T00:00:00Z",
            },
        },
        {
            "id": "multi/new",
            "title": "x",
            "source": {
                "provider": "multi",
                "url": "u",
                "scrapedAt": "2026-01-01T00:00:00Z",
                "attemptedAt": "2026-06-06T00:00:00Z",
            },
        },
    ]
    (tmp_path / "multi.json").write_text(json.dumps(records))
    _write(tmp_path, "single", "2026-03-01T00:00:00Z")

    # multi's max attempt (June) is newer than single (March), so single is staler.
    assert select_stale(2, slugs=["multi", "single"], data_dir=tmp_path) == ["single", "multi"]
