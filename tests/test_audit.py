"""Offline tests for the scraper-health audit (no network, no gh)."""

from __future__ import annotations

import json
from pathlib import Path

from intensive_dance.audit import Suspect, find_suspects, render_report

PROVIDERS: list[dict[str, object]] = [
    {"slug": "good", "name": "Good School", "url": "https://good.test/", "status": "live"},
    {"slug": "empty", "name": "Empty School", "url": "https://empty.test/", "status": "live"},
    {"slug": "missing", "name": "Missing School", "url": "https://missing.test/", "status": "live"},
    {"slug": "exempt", "name": "Exempt School", "url": "https://exempt.test/", "status": "live"},
    {"slug": "seedy", "name": "Seed School", "url": "https://seed.test/", "status": "seed"},
]


def _write(data_dir: Path, slug: str, records: list[dict[str, object]]) -> None:
    (data_dir / f"{slug}.json").write_text(json.dumps(records), encoding="utf-8")


def test_flags_empty_and_missing_skips_good_seed_and_exempt(tmp_path: Path) -> None:
    _write(tmp_path, "good", [{"id": "good/2026"}])
    _write(tmp_path, "empty", [])
    _write(tmp_path, "exempt", [])
    # "missing" has no file at all; "seedy" is not live.

    suspects = find_suspects(PROVIDERS, exempt={"exempt"}, data_dir=tmp_path)
    slugs = {s.slug for s in suspects}

    assert slugs == {"empty", "missing"}
    by_slug = {s.slug: s for s in suspects}
    assert "0 offerings" in by_slug["empty"].detail
    assert "never produced" in by_slug["missing"].detail


def test_render_report_clean_when_no_suspects() -> None:
    report = render_report([], live_count=87)
    assert "✅" in report
    assert "87 live providers" in report


def test_render_report_tables_suspects() -> None:
    report = render_report(
        [
            Suspect(
                slug="empty",
                name="Empty School",
                url="https://empty.test/",
                detail="0 offerings ...",
            )
        ],
        live_count=87,
    )
    assert "| `empty` |" in report
    assert "[Empty School](https://empty.test/)" in report
    assert "audit_allowlist.json" in report
