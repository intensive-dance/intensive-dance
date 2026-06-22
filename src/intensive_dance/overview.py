"""Buildable-seeds overview, derived from providers.json (the single source of truth).

`status:"seed"` providers are build candidates. Competitions (icebox epic #80) and
full-time vocational schools (defer to IDR-9, #12) are *not* buildable — they're listed
here as excluded, so the buildable set stays honest without a second store to sync.

Mirrors `schema.py`/`erd.py`: the committed `docs/buildable.md` is a *derived* artifact,
drift-checked in CI, so it can never silently go stale — point a builder at that one file.

    uv run python -m intensive_dance.overview            # check drift (CI)
    uv run python -m intensive_dance.overview --write     # regenerate docs/buildable.md
    uv run python -m intensive_dance.overview --print     # print to stdout
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROVIDERS = ROOT / "providers.json"
DOC = ROOT / "docs" / "buildable.md"

# Seeds that are NOT build targets, kept out of the buildable list with a reason.
# The register (providers.json) only carries seed/live; the scope call lives here,
# in one place — add a line when a competition / full-time school gets seeded.
NOT_BUILDABLE: dict[str, str] = {
    # Competitions (the *event*) — icebox epic #80 (IDR-40): no implementation.
    # A competition's dated *intensive* is a SEPARATE, in-scope provider with its own
    # slug (e.g. `prix-de-lausanne-summer-intensive`, live) — don't list that one here.
    "prix-de-lausanne": "competition — icebox #80",
    "helsinki-international-ballet-competition": "competition — icebox #80",
    "tanzolymp": "competition — icebox #80",
    "youth-america-grand-prix": "competition — icebox #80",
    # Full-time / long-term vocational only — defer to IDR-9 (#12) unless a public short course exists.
    "universal-ballet-academy": "full-time school — defer IDR-9",
    "teatro-opera-roma-scuola-danza": "full-time state school — defer IDR-9",
    "royal-swedish-ballet-school": "full-time school — defer IDR-9",
    "singapore-ballet": "company / full-time — defer IDR-9",
    # No current online edition.
    "neoclassica": "site offline — parked",
    # Pre-launch base44 template: every "edition" is dateless ("TBC", "applications
    # opening soon") with no fees/faculty — nothing bookable to scrape yet.
    "wiener-ballettakademie": "pre-launch — no dated edition yet (all TBC)",
    # In-scope summer intensive dormant — only a recreational kids camp runs now.
    "first-international-ballet-school-prague": (
        "only a recreational children's camp in 2026 (FIBS Summer Intensive dormant since 2022)"
    ),
    # Bournonville Summer Seminar dormant (last public editions ~2012/2019); today only a
    # year-round neighborhood school (3歳～大人) + company, no current dated public intensive.
    "inoue-ballet": "summer seminar dormant since ~2019 — no current dated edition",
    # Year-round schools / closed / drop-in only — no current public dated intensive
    # (Phase-1 verify-or-defer sweep, grounded search + site probe).
    "homura-tomoi-ballet-school": "pro open-classes + company auditions only — no public intensive",
    "star-dancers-ballet-school": "children's school closed 2024-03 — only Saturday open classes",
    "international-ballet-academia": "year-round school + Komaki Ballet company — no intensive",
    "tani-momoko-ballet-academy": "recurring drop-in special classes (same-day signup) — not a dated edition",
    "ballet-studio-felicia-serbanescu": "children's ballet studio — no summer-course page",
    "international-ballet-school-stockholm": "year-round school + adult ballet — no summer/intensive page",
    # German seeds — festival / internal / dormant / no current dated edition
    # (Phase-1 verify-or-defer sweep, grounded search + site probe).
    "palucca-tanzwoche-sylt": "amateur VHS dance week — no current dated edition findable (Hochschule = IDR-10 #13)",
    "tanzwerkstatt-europa": "professional contemporary-dance festival — not a student intensive",
    "summer-intensive-gymnasium-essen": "internal Gymnasium program for own pupils — not public",
    "tanzschule-anastasia-frankfurt": "local recreational school — Sommer Intensive one-off 2022, no current edition",
    "hamburger-ballett-tanztage": "teacher-training organizer — student Ballett-Tanztage last ran Jun 2024",
}

_CLAIM = (
    "**To claim one (so nobody double-builds):** check `gh issue list` / `gh pr list` for the "
    "slug; if free, open a `build:<slug>` issue and **self-assign first**, then build; close it "
    "when the PR merges (provider → `live`). An open claim issue *or* PR = locked. "
    "See `AGENTS.md` → Scope & coordination."
)


def _load() -> list[dict]:
    return json.loads(PROVIDERS.read_text(encoding="utf-8"))["providers"]


def render() -> str:
    providers = _load()
    seeds = [p for p in providers if p["status"] == "seed"]
    buildable = [p for p in seeds if p["slug"] not in NOT_BUILDABLE]
    excluded = [p for p in seeds if p["slug"] in NOT_BUILDABLE]
    live = sum(1 for p in providers if p["status"] == "live")

    by_country: dict[str, list[dict]] = {}
    for p in buildable:
        by_country.setdefault(p.get("country") or "??", []).append(p)

    out: list[str] = [
        "# Buildable seeds",
        "",
        "> **Generated — do not edit.** Refresh with "
        "`uv run python -m intensive_dance.overview --write`; CI drift-checks it. "
        "Source of truth: `providers.json`.",
        "",
        f"{len(buildable)} buildable · {len(excluded)} excluded · {live} live "
        f"({len(providers)} providers total).",
        "",
        _CLAIM,
        "",
        "## Buildable (status: seed)",
        "",
        "_Some still need Phase-1 verification (a public dated edition / not full-time) before building._",
    ]
    for country in sorted(by_country):
        out.append("")
        out.append(f"### {country}")
        for p in sorted(by_country[country], key=lambda x: x["slug"]):
            out.append(f"- `{p['slug']}` — {p['name']} ({p.get('city') or '?'}) — {p['url']}")
    out += ["", "## Excluded — do NOT build", ""]
    for p in sorted(excluded, key=lambda x: x["slug"]):
        out.append(f"- `{p['slug']}` — {p['name']} — _{NOT_BUILDABLE[p['slug']]}_")
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    content = render()
    if "--write" in argv:
        DOC.write_text(content, encoding="utf-8")
        print(f"wrote {DOC}")
        return 0
    if "--print" in argv:
        sys.stdout.write(content)
        return 0
    current = DOC.read_text(encoding="utf-8") if DOC.exists() else ""
    if current != content:
        print(
            "docs/buildable.md is stale — run `uv run python -m intensive_dance.overview --write`",
            file=sys.stderr,
        )
        return 1
    print("ok: docs/buildable.md matches providers.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
