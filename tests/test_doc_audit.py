"""Offline tests for the documentation-currency audit (no network, no git)."""

from __future__ import annotations

from pathlib import Path

from intensive_dance.doc_audit import (
    count_drift,
    dead_doc_links,
    iter_files,
    render_report,
    stale_repo_refs,
)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_stale_repo_ref_flags_old_org_and_reports_line(tmp_path: Path) -> None:
    f = _write(
        tmp_path / "README.md",
        "intro\nsee https://github.com/boredland/intensive-dance/issues/1\ndone\n",
    )
    findings = stale_repo_refs([f], tmp_path)
    assert len(findings) == 1
    assert findings[0].kind == "stale-repo-ref"
    assert findings[0].location == "README.md:2"


def test_stale_repo_ref_clean_file_is_silent(tmp_path: Path) -> None:
    f = _write(tmp_path / "x.md", "the org is intensive-dance/intensive-dance now\n")
    assert stale_repo_refs([f], tmp_path) == []


def test_count_drift_flags_far_off_but_exempts_dated_snapshot(tmp_path: Path) -> None:
    f = _write(
        tmp_path / "a.md",
        # off by >15% → flagged
        "We run 87 live providers today.\n"
        # within tolerance → ignored
        "Roughly 360 offerings.\n"
        # dated snapshot → exempt even though far off
        "Snapshot 2026-06-10: 87 live scrapers, 285 offerings.\n",
    )
    findings = count_drift([f], tmp_path, live=124, offerings=360)
    locs = {x.location for x in findings}
    assert locs == {"a.md:1"}
    assert all(x.kind == "count-drift" for x in findings)


def test_dead_doc_link_flags_missing_relative_target(tmp_path: Path) -> None:
    _write(tmp_path / "docs" / "real.md", "ok\n")
    f = _write(
        tmp_path / "docs" / "index.md",
        "[real](./real.md) [gone](./concept/index.html) "
        "[ext](https://example.com) [anchor](#top)\n",
    )
    findings = dead_doc_links([f], tmp_path)
    assert len(findings) == 1
    assert findings[0].kind == "dead-doc-link"
    assert "concept/index.html" in findings[0].detail


def test_iter_files_skips_vendored_and_data_dirs(tmp_path: Path) -> None:
    _write(tmp_path / "keep.md", "x")
    _write(tmp_path / "data" / "prov.json", "[]")  # skipped dir (and wrong suffix)
    _write(tmp_path / ".git" / "config.md", "x")  # skipped dir
    _write(tmp_path / "src" / "mod.py", "x")
    found = {p.name for p in iter_files(tmp_path, (".md", ".py"))}
    assert found == {"keep.md", "mod.py"}


def test_render_report_empty_vs_findings(tmp_path: Path) -> None:
    assert "✅" in render_report([])
    f = _write(tmp_path / "r.md", "boredland/intensive-dance\n")
    report = render_report(stale_repo_refs([f], tmp_path))
    assert "⚠️" in report
    assert "stale-repo-ref" in report
