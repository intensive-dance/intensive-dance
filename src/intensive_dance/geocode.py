"""Hand-run enrichment: fill the gazetteer's missing cities via Nominatim (OSM).

NOT part of `scrape()` or the CI gate — geocoding is network-bound and
non-deterministic, so it runs by hand, its output (`data/gazetteer.json`) is
reviewed, and only that committed file is consumed downstream. This is the same
rule AGENTS.md states for LLM enrichment: fine as a reviewed dev helper, never in
the deterministic path.

Idempotent: only `(country, city)` keys missing from the gazetteer are looked up;
existing entries are kept untouched, so a re-run after new scrapes only tops up.

    uv run python -m intensive_dance.geocode             # fill missing → gazetteer.json
    uv run python -m intensive_dance.geocode --dry-run   # list what would be looked up

We use a plain httpx client with a *descriptive* User-Agent (Nominatim's usage
policy requires identifying the caller) and throttle to ≤1 request/second — so we
deliberately do NOT route through `make_client`/the fetch proxy, which would mask
the UA with a generic Chrome string.
"""

from __future__ import annotations

import sys
import time

import httpx

from intensive_dance.geo import (
    GAZETTEER_PATH,
    Place,
    load_gazetteer,
    missing_places,
    save_gazetteer,
)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "intensive.dance gazetteer builder (https://intensive.dance)"
RATE_LIMIT_SECONDS = 1.0


def geocode_city(client: httpx.Client, country: str, city: str) -> Place | None:
    """Resolve one `(country, city)` to a `Place`. Tries the structured
    city+countrycode query first (most precise), then a free-form fallback."""
    for params in (
        {"city": city, "countrycodes": country.lower(), "format": "jsonv2", "limit": 1},
        {"q": f"{city}, {country}", "format": "jsonv2", "limit": 1},
    ):
        resp = client.get(NOMINATIM_URL, params=params, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        rows = resp.json()
        if rows:
            row = rows[0]
            return Place(
                lat=round(float(row["lat"]), 4),  # 4 dp ≈ 11 m — ample for "is it reachable?"
                lon=round(float(row["lon"]), 4),
                precision="city",
                source="nominatim",
                name=row.get("display_name"),
            )
    return None


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    missing = missing_places()
    if not missing:
        print("gazetteer already complete — nothing to geocode")
        return 0

    print(f"{len(missing)} city(ies) to geocode")
    if dry_run:
        for _, (country, city) in sorted(missing.items(), key=lambda kv: kv[1]):
            print(f"  {city}, {country}")
        return 0

    gazetteer = load_gazetteer()
    failures = 0
    with httpx.Client(timeout=30.0) as client:
        for key, (country, city) in sorted(missing.items(), key=lambda kv: kv[1]):
            try:
                place = geocode_city(client, country, city)
            except Exception as exc:  # noqa: BLE001 — one bad lookup must not abort the rest
                print(f"FAIL {city}, {country}: {exc}", file=sys.stderr)
                failures += 1
                continue
            if place is None:
                print(f"MISS {city}, {country}: no result", file=sys.stderr)
                failures += 1
                continue
            gazetteer[key] = place
            print(f"  {city}, {country} -> {place.lat},{place.lon}  ({place.name})")
            time.sleep(RATE_LIMIT_SECONDS)

    save_gazetteer(gazetteer)
    print(f"wrote {GAZETTEER_PATH} ({len(gazetteer)} entries; {failures} unresolved)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
