"""Unit tests for the attempt-stamping that drives the hourly rotation.

`--touch` bumps `source.attemptedAt` on every attempt; without it, a plain run
carries the prior `attemptedAt` so the store stays no-diff. `stamp_attempt`
advances a *failed* provider without disturbing its content or hash. No network.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import intensive_dance.run as run
from intensive_dance.models import Offering

_NOW = datetime(2026, 6, 6, 12, 0, 0, tzinfo=timezone.utc)


def _offering(slug: str, attempted_at: str | None = None) -> Offering:
    source = {"provider": slug, "url": "https://x", "scrapedAt": "2026-01-01T00:00:00Z"}
    if attempted_at is not None:
        source["attemptedAt"] = attempted_at
    return Offering.model_validate(
        {
            "id": f"{slug}/x",
            "title": "X",
            "organization": {"name": "P", "slug": slug, "country": "GB"},
            "schedule": {"season": "unknown"},
            "source": source,
        }
    )


def test_carry_attempted_at_records_when_touched() -> None:
    offerings = [_offering("p")]
    run.carry_attempted_at("p", offerings, _NOW, record=True)
    assert offerings[0].source.attempted_at == _NOW


def test_carry_attempted_at_preserves_prior_without_touch(tmp_path: Path, monkeypatch) -> None:
    prior = _offering("p", attempted_at="2026-05-01T00:00:00Z")
    (tmp_path / "p.json").write_text(json.dumps([prior.model_dump(by_alias=True, mode="json")]))
    monkeypatch.setattr(run, "DATA_DIR", tmp_path)

    fresh = [_offering("p")]  # scraper produced no attemptedAt
    run.carry_attempted_at("p", fresh, _NOW, record=False)
    assert fresh[0].source.attempted_at == datetime(2026, 5, 1, tzinfo=timezone.utc)


def test_stamp_attempt_bumps_without_touching_content(tmp_path: Path) -> None:
    original = _offering("p", attempted_at="2026-05-01T00:00:00Z")
    original.source.hash = original.content_hash()
    (tmp_path / "p.json").write_text(json.dumps([original.model_dump(by_alias=True, mode="json")]))

    run.stamp_attempt("p", _NOW, data_dir=tmp_path)

    written = json.loads((tmp_path / "p.json").read_text())[0]
    assert written["source"]["attemptedAt"] == "2026-06-06T12:00:00Z"
    assert written["source"]["scrapedAt"] == "2026-01-01T00:00:00Z"
    assert written["source"]["hash"] == original.source.hash  # content untouched


def test_stamp_attempt_noop_when_file_missing(tmp_path: Path) -> None:
    run.stamp_attempt("absent", _NOW, data_dir=tmp_path)  # must not raise
    assert not (tmp_path / "absent.json").exists()
