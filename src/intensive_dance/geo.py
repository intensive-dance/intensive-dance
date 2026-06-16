"""Gazetteer: `(country, city)` → coordinates, for the consumer's proximity search.

WHY THIS IS SEPARATE FROM `models.py` AND THE SCRAPE PATH
Geocoding is network-bound and non-deterministic — exactly what must stay out of
`scrape()` (the same rule that keeps LLM calls out of it). So the canonical store
(`data/<slug>.json`) stays coordinate-free; coordinates live here in a committed
gazetteer, filled by the hand-run `intensive_dance.geocode` helper and reviewed
before commit. The consumer joins offerings to this file by `(country, city)`.

This module is the *pure* half (model, load/save, the store↔gazetteer set diff,
haversine) — importable by tests, validate, and the consumer-prep step with no
network. `intensive_dance.geocode` is the *network* half.

    uv run python -m intensive_dance.geo            # coverage report (store vs gazetteer)
    uv run python -m intensive_dance.geo --check     # same, but exit 1 if any city is missing
"""

from __future__ import annotations

import json
import sys
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
GAZETTEER_PATH = DATA_DIR / "gazetteer.json"


class Place(BaseModel):
    """One geocoded location. `name` is the geocoder's display name, kept purely
    so a human can eyeball the gazetteer diff and catch a wrong hit (a second
    "Vienna" in the US, say) before it ships."""

    lat: float
    lon: float
    precision: str = "city"  # "city" today; "venue" once venue-level lookups land (phase 2)
    source: str  # e.g. "nominatim"
    name: str | None = None  # geocoder display name, for human review of the diff


def place_key(country: str, city: str) -> str:
    """Stable gazetteer key. Uses the *raw* store strings so the consumer join is
    exact — no normalization, which could silently de-sync a key from its row."""
    return f"{country}|{city}"


def load_gazetteer(path: Path = GAZETTEER_PATH) -> dict[str, Place]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {key: Place.model_validate(value) for key, value in raw.items()}


def save_gazetteer(places: dict[str, Place], path: Path = GAZETTEER_PATH) -> None:
    """Write deterministically (sorted keys, trailing newline) — same shape as the
    rest of the store, so the file is a clean, reviewable git diff."""
    payload = {key: places[key].model_dump(exclude_none=True) for key in sorted(places)}
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def distinct_places(data_dir: Path = DATA_DIR) -> dict[str, tuple[str, str]]:
    """Every `(country, city)` that appears on a located offering, keyed by
    `place_key`. Skips the gazetteer file itself and any location without both a
    city and a country (online-only / city-less rows can't be placed on a map)."""
    out: dict[str, tuple[str, str]] = {}
    for path in sorted(data_dir.glob("*.json")):
        if path.name == GAZETTEER_PATH.name:
            continue
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(records, list):
            continue
        for record in records:
            location = record.get("location") or {}
            city = location.get("city")
            country = location.get("country")
            if city and country:
                out[place_key(country, city)] = (country, city)
    return out


def missing_places(
    data_dir: Path = DATA_DIR, gazetteer_path: Path = GAZETTEER_PATH
) -> dict[str, tuple[str, str]]:
    """`(country, city)` pairs present in the store but absent from the gazetteer."""
    gazetteer = load_gazetteer(gazetteer_path)
    return {key: value for key, value in distinct_places(data_dir).items() if key not in gazetteer}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km — the same formula the consumer runs client-side."""
    earth_radius_km = 6371.0088
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return 2 * earth_radius_km * asin(sqrt(a))


def main(argv: list[str]) -> int:
    """Coverage report. Informational by default (exit 0); `--check` makes a gap a
    non-zero exit, for opt-in use by the geocode flow — deliberately NOT wired into
    the main CI gate, so adding a scraper in a new city never blocks an unrelated PR."""
    missing = missing_places()
    total = len(distinct_places())
    covered = total - len(missing)
    if missing:
        print(f"gazetteer: {covered}/{total} cities covered; missing {len(missing)}:")
        for _, (country, city) in sorted(missing.items(), key=lambda kv: kv[1]):
            print(f"  - {city}, {country}")
        return 1 if "--check" in argv else 0
    print(f"gazetteer: all {total} located cities covered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
