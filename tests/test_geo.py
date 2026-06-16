"""Offline tests for the gazetteer plumbing (no network).

The network half (`intensive_dance.geocode`, which calls Nominatim) is a hand-run
enrichment helper and is deliberately not exercised here — these tests pin the
pure logic the consumer and CI depend on: the store↔gazetteer set diff, the
deterministic round-trip, and the distance formula.
"""

from __future__ import annotations

import json
from pathlib import Path

from intensive_dance.geo import (
    Place,
    distinct_places,
    haversine_km,
    load_gazetteer,
    missing_places,
    place_key,
    save_gazetteer,
)


def _write(path: Path, records: object) -> None:
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")


def test_place_key_uses_raw_strings():
    assert place_key("AT", "Vienna") == "AT|Vienna"
    assert place_key("US", "New York") == "US|New York"


def test_distinct_places_only_located_rows(tmp_path: Path):
    _write(
        tmp_path / "a.json",
        [
            {"id": "a/1", "location": {"city": "Vienna", "country": "AT"}},
            {"id": "a/2", "location": {"city": "Vienna", "country": "AT"}},  # dup → one key
            {"id": "a/3", "location": {"country": "AT"}},  # no city → skipped
            {"id": "a/4", "location": {"online": True}},  # online → skipped
            {"id": "a/5"},  # no location → skipped
        ],
    )
    _write(tmp_path / "b.json", [{"id": "b/1", "location": {"city": "Tokyo", "country": "JP"}}])
    # a file literally named like the gazetteer must be ignored, not parsed as offerings
    _write(tmp_path / "gazetteer.json", {"AT|Vienna": {"lat": 1, "lon": 2, "source": "x"}})

    found = distinct_places(tmp_path)
    assert found == {"AT|Vienna": ("AT", "Vienna"), "JP|Tokyo": ("JP", "Tokyo")}


def test_distinct_places_skips_malformed_file(tmp_path: Path):
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    _write(tmp_path / "ok.json", [{"id": "ok/1", "location": {"city": "Paris", "country": "FR"}}])
    assert distinct_places(tmp_path) == {"FR|Paris": ("FR", "Paris")}


def test_missing_places(tmp_path: Path):
    _write(
        tmp_path / "a.json",
        [
            {"id": "a/1", "location": {"city": "Vienna", "country": "AT"}},
            {"id": "a/2", "location": {"city": "Tokyo", "country": "JP"}},
        ],
    )
    gz_path = tmp_path / "gazetteer.json"
    save_gazetteer({"AT|Vienna": Place(lat=48.2, lon=16.4, source="test")}, gz_path)

    missing = missing_places(tmp_path, gz_path)
    assert missing == {"JP|Tokyo": ("JP", "Tokyo")}


def test_missing_places_empty_when_no_gazetteer(tmp_path: Path):
    _write(tmp_path / "a.json", [{"id": "a/1", "location": {"city": "Vienna", "country": "AT"}}])
    # absent gazetteer → everything is missing
    assert missing_places(tmp_path, tmp_path / "absent.json") == {"AT|Vienna": ("AT", "Vienna")}


def test_gazetteer_roundtrip_and_deterministic(tmp_path: Path):
    path = tmp_path / "gazetteer.json"
    places = {
        "JP|Tokyo": Place(lat=35.6769, lon=139.7639, source="nominatim", name="東京都"),
        "AT|Vienna": Place(lat=48.2084, lon=16.3725, source="nominatim", name="Wien"),
    }
    save_gazetteer(places, path)
    loaded = load_gazetteer(path)
    assert loaded == places

    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    # sorted keys → AT before JP regardless of insertion order
    assert text.index('"AT|Vienna"') < text.index('"JP|Tokyo"')


def test_place_optional_name_omitted_when_none(tmp_path: Path):
    path = tmp_path / "gazetteer.json"
    save_gazetteer({"SG|Singapore": Place(lat=1.35, lon=103.82, source="nominatim")}, path)
    assert '"name"' not in path.read_text(encoding="utf-8")


def test_haversine_known_distances():
    assert haversine_km(0.0, 0.0, 0.0, 0.0) == 0.0
    # one degree of longitude at the equator ≈ 111.32 km
    assert abs(haversine_km(0.0, 0.0, 0.0, 1.0) - 111.32) < 0.5
    # London ↔ Paris ≈ 344 km (great circle)
    london = (51.5074, -0.1278)
    paris = (48.8566, 2.3522)
    assert 335.0 < haversine_km(*london, *paris) < 350.0
