"""Build the consumer feed the UI renders.

Joins every **live** provider's offerings (projected to the handful of fields the
UI needs) with coordinates from `data/gazetteer.json`, so the page can compute
"intensives near me" entirely client-side. Deterministic (sorted, no timestamp).

The customer UI lives in a **separate** repo (`ha1des/intensive-dance-ui`); this
backend only *produces* the feed (it owns the data). Materialise it into the UI
checkout, or print it to stdout:

    uv run python -m intensive_dance.bundle --out ../intensive-dance-ui/data.json
    uv run python -m intensive_dance.bundle            # print to stdout

Not part of the scrape path or the CI gate (it depends on all of `data/`, which
changes hourly — gating on it would block unrelated PRs).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from intensive_dance.geo import load_gazetteer, place_key

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
PROVIDERS = ROOT / "providers.json"


def _price_type(p: dict) -> str:
    """A price's category, preferring the stored `type`; falls back to the legacy
    tuition `includes` tag for any pre-migration record in the feed."""
    return p.get("type") or ("tuition" if "tuition" in (p.get("includes") or []) else "other")


def _headline_price(prices: list[dict]) -> dict | None:
    """The single price worth showing. Prefer the `tuition` charge (the actual
    course price); else fall back to the first price but flag it as a `fee`, so
    the page can say "application fee: X" instead of mislabelling a
    registration/deposit charge as the course price. `None` if none is published.
    """
    if not prices:
        return None
    tuition = next((p for p in prices if _price_type(p) == "tuition"), None)
    chosen = tuition or prices[0]
    return {
        "amount": chosen.get("amount"),
        "currency": chosen.get("currency"),
        "label": chosen.get("label"),
        "fee": tuition is None,
    }


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
            {
                "amount": p.get("amount"),
                "currency": p.get("currency"),
                "label": p.get("label"),
                "fee": _price_type(p) != "tuition",
            }
            for p in offering.get("prices", [])
        ],
        "price": _headline_price(offering.get("prices") or []),
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
    count = text.count('"id":')
    if "--out" in argv:
        idx = argv.index("--out")
        if idx + 1 >= len(argv):
            print("--out needs a path", file=sys.stderr)
            return 2
        out = Path(argv[idx + 1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out} ({count} offerings)", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
