"""Daily scraper health audit.

A `live` provider whose committed store holds **zero** offerings is almost
never a genuinely empty source — past cycles are kept (IDR-24), so a real live
provider has at least one. Zero means stale markup, a moved endpoint, or a
filter dropping every row: exactly the failure mode the self-healing loop
exists to catch. Each such provider becomes a "suspect" the audit hands to the
Copilot coding agent.

Mirrors museumsufer's `audit-scrapers.ts`: reads only the **committed** store
(`data/<slug>.json`) plus `providers.json`, so it runs offline and
deterministically. Providers verified to be legitimately empty are exempted via
`audit_allowlist.json`.

    uv run python -m intensive_dance.audit          # print the report

In CI it also writes `suspects=<n>` to `$GITHUB_OUTPUT`, the report to
`$GITHUB_STEP_SUMMARY`, and a copy to `$AUDIT_REPORT_PATH` for the assign step.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
PROVIDERS = ROOT / "providers.json"
ALLOWLIST = Path(__file__).resolve().parent / "audit_allowlist.json"


@dataclass(frozen=True)
class Suspect:
    slug: str
    name: str
    url: str
    detail: str


def _offering_count(slug: str, data_dir: Path) -> int | None:
    """Number of committed offerings for a provider, or None if no/unreadable file."""
    path = data_dir / f"{slug}.json"
    if not path.exists():
        return None
    try:
        records = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return len(records) if isinstance(records, list) else None


def find_suspects(
    providers: list[dict[str, object]],
    exempt: set[str],
    data_dir: Path = DATA_DIR,
) -> list[Suspect]:
    """Live providers whose committed store is empty or missing (excluding exempt)."""
    suspects: list[Suspect] = []
    for provider in providers:
        if provider.get("status") != "live":
            continue
        slug = str(provider.get("slug", ""))
        if not slug or slug in exempt:
            continue
        count = _offering_count(slug, data_dir)
        if count is None:
            detail = "no data/<slug>.json committed — the scraper has never produced a store"
        elif count == 0:
            detail = (
                "0 offerings in the committed store (past cycles are kept, so a real source has ≥1)"
            )
        else:
            continue
        suspects.append(
            Suspect(
                slug=slug,
                name=str(provider.get("name", slug)),
                url=str(provider.get("url", "")),
                detail=detail,
            )
        )
    return suspects


def render_report(suspects: list[Suspect], live_count: int) -> str:
    lines = ["## Scraper health audit", ""]
    if not suspects:
        lines.append(f"✅ All {live_count} live providers are delivering at least one offering.")
        return "\n".join(lines)

    lines.append(
        f"⚠️ {len(suspects)} live provider(s) deliver **zero** offerings. Each likely points at stale "
        "markup, a moved endpoint, or a filter dropping valid rows — verify against the live source "
        "before assuming the provider is simply empty."
    )
    lines += ["", "| Provider | Slug | Finding |", "| --- | --- | --- |"]
    for s in suspects:
        link = f"[{s.name}]({s.url})" if s.url else s.name
        lines.append(f"| {link} | `{s.slug}` | {s.detail} |")
    lines += [
        "",
        "### What to do",
        "For each provider above: read its scraper "
        "(`src/intensive_dance/scrapers/<slug_with_underscores>.py`), fetch the live source, and "
        "determine whether it actually lists offerings the scraper fails to extract. If the parser is "
        "broken, fix it and update the module docstring; if the source is genuinely/seasonally empty, add "
        "the slug to `src/intensive_dance/audit_allowlist.json` with a one-line reason instead of changing "
        "code. Verify a fix with `uv run python -m intensive_dance.run <slug>` and the full gate "
        "(`ruff` · `ty check` · `pytest` · `schema` · `validate`).",
    ]
    return "\n".join(lines)


def load_exempt(path: Path = ALLOWLIST) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text())
    return {k for k in data if not k.startswith("_")}


def main() -> int:
    providers = json.loads(PROVIDERS.read_text())["providers"]
    exempt = load_exempt()
    suspects = find_suspects(providers, exempt)
    live_count = sum(1 for p in providers if p.get("status") == "live")
    report = render_report(suspects, live_count)
    print(report)

    if out := os.environ.get("GITHUB_OUTPUT"):
        Path(out).open("a", encoding="utf-8").write(f"suspects={len(suspects)}\n")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        Path(summary).open("a", encoding="utf-8").write(f"{report}\n")
    Path(os.environ.get("AUDIT_REPORT_PATH", "scraper-audit-report.md")).write_text(
        report, encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
