"""Scraper registry.

Each scraper is a pure function `scrape(client) -> list[Offering]` keyed by its
provider slug (see providers.json). The runner walks this map.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx

from intensive_dance.models import Offering

from . import (
    frankfurt_ballet_masterclasses,
    john_cranko_school,
    joffrey_ballet_school,
    mosa_ballet_school,
    royal_ballet_school,
    russian_masters_ballet,
)

Scraper = Callable[[httpx.Client], list[Offering]]

SCRAPERS: dict[str, Scraper] = {
    "royal-ballet-school": royal_ballet_school.scrape,
    "joffrey-ballet-school": joffrey_ballet_school.scrape,
    "russian-masters-ballet": russian_masters_ballet.scrape,
    "mosa-ballet-school": mosa_ballet_school.scrape,
    "john-cranko-schule": john_cranko_school.scrape,
    "frankfurt-ballet-masterclasses": frankfurt_ballet_masterclasses.scrape,
}
