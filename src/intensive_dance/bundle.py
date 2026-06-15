"""Build the consumer bundle the static register page reads: `concept/data.json`.

Joins every **live** provider's offerings (projected to the handful of fields the
UI needs) with coordinates from `data/gazetteer.json`, so the page can compute
"intensives near me" entirely client-side. Deterministic (sorted, no timestamp)
so a rebuild on unchanged data yields no git diff — same ethos as the store.

This is a *derived* artifact, regenerated on demand (it is intentionally **not**
a CI drift-gate: it depends on all of `data/`, which changes hourly, so gating on
it would block unrelated PRs). Re-run after a data refresh before viewing/shipping.

    uv run python -m intensive_dance.bundle           # write concept/data.json
    uv run python -m intensive_dance.bundle --check    # exit 1 if it would change
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from intensive_dance.geo import load_gazetteer, place_key

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
PROVIDERS = ROOT / "providers.json"
BUNDLE_PATH = ROOT / "concept" / "data.json"


def _project(offering: dict, coords: dict[str, tuple[float, float]]) -> dict:
    """One store offering → the flat record the page renders (+ joined coords)."""
    location = offering.get("location") or {}
    schedule = offering.get("schedule") or {}
    application = offering.get("application") or {}
    organization = offering.get("organization") or {}
    city = location.get("city")
    country = location.get("country")

    record: dict[str, object] = {
        "id": offering["id"],
        "title": offering.get("title"),
        "org": organization.get("name"),
        "orgSlug": organization.get("slug"),
        "genres": offering.get("genres", []),
        "level": offering.get("level", []),
        "age": offering.get("ageRange"),
        "city": city,
        "country": country,
        "venue": location.get("venue"),
        "online": location.get("online"),
        "lifecycle": offering.get("lifecycle"),
        "season": schedule.get("season"),
        "start": schedule.get("start"),
        "end": schedule.get("end"),
        "sessions": [
            {
                "label": s.get("label"),
                "start": s.get("start"),
                "end": s.get("end"),
                "gender": s.get("gender"),
            }
            for s in schedule.get("sessions", [])
        ],
        "status": application.get("status"),
        "deadline": application.get("deadline"),
        "appUrl": application.get("url"),
        "reqs": [r.get("type") for r in application.get("requirements", [])],
        "prices": [
            {"amount": p.get("amount"), "currency": p.get("currency"), "label": p.get("label")}
            for p in offering.get("prices", [])
        ],
        "url": (offering.get("source") or {}).get("url"),
    }
    # Coordinates are the only enrichment — null when the city isn't in the gazetteer
    # (or the offering is online / city-less); the page groups those separately.
    point = coords.get(place_key(country, city)) if (city and country) else None
    record["lat"] = point[0] if point else None
    record["lon"] = point[1] if point else None
    return record


def build_bundle() -> list[dict]:
    providers = json.loads(PROVIDERS.read_text(encoding="utf-8"))["providers"]
    live = [p["slug"] for p in providers if p.get("status") == "live"]
    gazetteer = load_gazetteer()
    coords = {key: (place.lat, place.lon) for key, place in gazetteer.items()}

    records: list[dict] = []
    for slug in live:
        path = DATA_DIR / f"{slug}.json"
        if not path.exists():
            continue
        for offering in json.loads(path.read_text(encoding="utf-8")):
            records.append(_project(offering, coords))
    records.sort(key=lambda r: r["id"])
    return records


def _serialize(records: list[dict]) -> str:
    return json.dumps(records, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    text = _serialize(build_bundle())
    if "--check" in argv:
        current = BUNDLE_PATH.read_text(encoding="utf-8") if BUNDLE_PATH.exists() else ""
        if current != text:
            print(f"{BUNDLE_PATH.name} is stale — run `python -m intensive_dance.bundle`")
            return 1
        print(f"ok: {BUNDLE_PATH.name} is up to date")
        return 0
    BUNDLE_PATH.parent.mkdir(exist_ok=True)
    BUNDLE_PATH.write_text(text, encoding="utf-8")
    count = text.count('"id":')
    print(f"wrote {BUNDLE_PATH} ({count} offerings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
