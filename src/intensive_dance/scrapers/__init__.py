"""Scraper registry.

Each scraper is a pure function `scrape(client) -> list[Offering]` keyed by its
provider slug (see providers.json). The runner walks this map.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx

from intensive_dance.models import Offering

from . import royal_ballet_school

Scraper = Callable[[httpx.Client], list[Offering]]

SCRAPERS: dict[str, Scraper] = {
    "royal-ballet-school": royal_ballet_school.scrape,
}
