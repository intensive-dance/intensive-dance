"""Weekly documentation-currency audit.

Hand-written prose drifts because — unlike the *derived* docs (`schema.py`,
`erd.py`, `overview.py`) which CI drift-checks — nothing fails when a narrative
doc falls out of step with reality. This audit is the missing alarm: it scans
the committed docs for a handful of **deterministic drift smells** and, only when
it finds any, opens a single reusable `doc-audit` issue (see
`intensive_dance.report_doc_audit`). It is a tracker for a human, not a Copilot
job — most doc fixes need editorial judgement and several span sibling repos the
agent can't touch.

Smells (all low-false-positive, offline, deterministic):

- **stale-repo-ref** — a `boredland/intensive-dance` reference left over from the
  org transfer; the canonical remote is `intensive-dance/intensive-dance`.
- **count-drift** — a prose count ("N live", "N offerings") that disagrees with
  `providers.json` / the committed store by more than a tolerance. Lines marked
  "snapshot"/"as of" are exempt (intentionally historical); generated docs like
  `buildable.md` carry the live number and stay current via their own CI check.
- **dead-doc-link** — a relative Markdown link whose target file no longer
  exists (the `concept/index.html` class of rot).

Deliberately **not** audited: per-provider *status* in `docs/candidates.md`. That
file is, by design (see its banner), a historical discovery record — the source
of truth for status is `providers.json`, so nagging that an old "promoted to
seed" line is now `live` would just re-litigate that decision and churn.

Mirrors `intensive_dance.audit`: stdlib-only (run with
`PYTHONPATH=src python3 -m intensive_dance.doc_audit`, no `uv sync`), reads only
committed files, and writes `findings=<n>` to `$GITHUB_OUTPUT`, the report to
`$GITHUB_STEP_SUMMARY`, and a copy to `$DOC_AUDIT_REPORT_PATH` for the report
step. Runs in the *public* repo, so it audits the public docs only (the private
doc-set has its own keep-current discipline).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

STALE_REPO_REF = "boredland/intensive-dance"
# Extensions worth scanning for a stale repo reference (text we author + config).
SCAN_SUFFIXES = (".md", ".py", ".yml", ".yaml", ".html", ".toml", ".txt")
# Dirs never worth scanning: vcs / vendored / generated / the data store / agent
# worktrees + tooling under .claude (transient copies of the repo).
SKIP_DIRS = {
    ".git",
    ".claude",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "data",
    "__pycache__",
}
# The audit's own machinery necessarily contains the stale-ref literal (the
# needle constant + its test fixtures); exclude it from stale-repo-ref so the
# detector doesn't flag itself.
SELF_FILES = {"doc_audit.py", "report_doc_audit.py", "test_doc_audit.py"}
# Generated audit reports quote the findings verbatim (incl. the stale-ref
# literal); skip them entirely so a local run never flags its own output.
SKIP_FILES = {"doc-audit-report.md", "scraper-audit-report.md"}
# A prose count this far off the real number is drift, not a stale-by-a-day snapshot.
COUNT_TOLERANCE = 0.15

_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_COUNT_RE = re.compile(
    r"(\d[\d,]*)\s+(live(?:\s+(?:providers|scrapers))?|offerings)\b", re.IGNORECASE
)
# A line that intentionally records a historical figure — exempt from count-drift.
_DATED_RE = re.compile(r"\bas of\b|\bsnapshot\b", re.IGNORECASE)


@dataclass(frozen=True)
class Finding:
    kind: str  # short category, e.g. "stale-repo-ref"
    location: str  # "path:line" or "path"
    detail: str


def _rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root)) if path.is_relative_to(root) else str(path)


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def iter_files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    """Text files under `root`, skipping vcs/vendored/generated/worktree dirs."""
    out: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in suffixes or path.name in SKIP_FILES:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        out.append(path)
    return out


def stale_repo_refs(files: list[Path], root: Path, needle: str = STALE_REPO_REF) -> list[Finding]:
    out: list[Finding] = []
    for path in files:
        if path.name in SELF_FILES:  # the detector + its fixtures legitimately hold the literal
            continue
        text = _read(path)
        if text is None:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if needle in line:
                out.append(
                    Finding(
                        "stale-repo-ref",
                        f"{_rel(path, root)}:{n}",
                        f"references `{needle}` — the repo moved to the `intensive-dance` org",
                    )
                )
    return out


def count_drift(
    docs: list[Path], root: Path, live: int, offerings: int, tol: float = COUNT_TOLERANCE
) -> list[Finding]:
    out: list[Finding] = []
    for path in docs:
        text = _read(path)
        if text is None:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if _DATED_RE.search(line):  # an intentional historical snapshot
                continue
            for m in _COUNT_RE.finditer(line):
                claimed = int(m.group(1).replace(",", ""))
                kind = m.group(2).lower()
                actual = offerings if kind.startswith("offerings") else live
                if actual and abs(claimed - actual) / actual > tol:
                    out.append(
                        Finding(
                            "count-drift",
                            f"{_rel(path, root)}:{n}",
                            f"says {claimed} {kind}, but the store has {actual} — "
                            "link/generate the number or mark it 'as of <date>'",
                        )
                    )
    return out


def dead_doc_links(md_files: list[Path], root: Path) -> list[Finding]:
    out: list[Finding] = []
    for path in md_files:
        text = _read(path)
        if text is None:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for m in _LINK_RE.finditer(line):
                target = m.group(1).strip()
                if target.startswith(("http://", "https://", "#", "mailto:", "tel:", "<")):
                    continue
                rel_part = target.split("#", 1)[0].split("?", 1)[0].strip()
                if not rel_part:
                    continue
                base = root if rel_part.startswith("/") else path.parent
                resolved = (base / rel_part.lstrip("/")).resolve()
                if not resolved.exists():
                    out.append(
                        Finding(
                            "dead-doc-link",
                            f"{_rel(path, root)}:{n}",
                            f"links to missing `{rel_part}`",
                        )
                    )
    return out


def _store_counts(providers: list[dict[str, object]], data_dir: Path) -> tuple[int, int]:
    """(live provider count, total committed offerings)."""
    live = sum(1 for p in providers if p.get("status") == "live")
    offerings = 0
    for path in data_dir.glob("*.json"):
        if path.name == "gazetteer.json":
            continue
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(records, list):
            offerings += len(records)
    return live, offerings


def collect_findings(root: Path = ROOT) -> list[Finding]:
    providers = json.loads((root / "providers.json").read_text(encoding="utf-8"))["providers"]
    live, offerings = _store_counts(providers, root / "data")
    files = iter_files(root, SCAN_SUFFIXES)
    md_files = [f for f in files if f.suffix == ".md"]
    return [
        *stale_repo_refs(files, root),
        *count_drift(md_files, root, live, offerings),
        *dead_doc_links(md_files, root),
    ]


def render_report(findings: list[Finding]) -> str:
    lines = ["## Documentation-currency audit", ""]
    if not findings:
        lines.append("✅ No documentation drift smells found.")
        return "\n".join(lines)

    lines.append(
        f"⚠️ {len(findings)} documentation drift smell(s) found. Each is a deterministic mismatch "
        "between the committed prose and reality — fix the doc, or (better) link/generate the fact so "
        "it can't drift again."
    )
    lines += ["", "| Kind | Where | Finding |", "| --- | --- | --- |"]
    for f in sorted(findings, key=lambda x: (x.kind, x.location)):
        lines.append(f"| `{f.kind}` | `{f.location}` | {f.detail} |")
    lines += [
        "",
        "### Why this keeps happening",
        "Derived docs (`schema`/`erd`/`buildable.md`) are CI-drift-checked and never rot; only "
        "honour-system prose does. Prefer pointing at the source of truth (`providers.json`, "
        "`buildable.md`) over restating it.",
    ]
    return "\n".join(lines)


def main() -> int:
    findings = collect_findings()
    report = render_report(findings)
    print(report)

    if out := os.environ.get("GITHUB_OUTPUT"):
        Path(out).open("a", encoding="utf-8").write(f"findings={len(findings)}\n")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        Path(summary).open("a", encoding="utf-8").write(f"{report}\n")
    Path(os.environ.get("DOC_AUDIT_REPORT_PATH", "doc-audit-report.md")).write_text(
        report, encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
