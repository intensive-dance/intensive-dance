"""Provider-agnostic text, date and money parsing, shared across scrapers.

Each scraper in `scrapers/` is a self-contained `scrape(client) -> list[Offering]`,
but the low-level chores are identical from provider to provider: collapsing
scraped whitespace, naming English months for a date regex, reading a fee written
in European or Anglo notation, matching genre keywords. They live here so a fix
(or its test) lands in one place — the same role `wp.py` plays for WordPress.

What stays in the scrapers is what is genuinely provider-specific: the German
month names of `john_cranko_school`, each provider's genre keyword table, and the
surrounding date-range regexes (whose shapes diverge too much to share cleanly).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import TypeVar

# English month name → number. `MONTHALT` is the names as a regex alternation,
# ready to embed in a date pattern; `months_alt` rebuilds it for a non-English
# map (e.g. the German names `john_cranko_school` keeps local).
MONTHS: dict[str, int] = {
    m: i
    for i, m in enumerate(
        ["january", "february", "march", "april", "may", "june", "july",
         "august", "september", "october", "november", "december"],
        start=1,
    )
}


def months_alt(months: Iterable[str] = MONTHS) -> str:
    """`a|b|c` alternation of month names, for embedding in a date regex."""
    return "|".join(months)


MONTHALT = months_alt()


def clean(text: str) -> str:
    """Collapse whitespace runs and non-breaking spaces into single spaces."""
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def parse_amount(raw: str) -> float | None:
    """Parse a fee in European (1.400 / 1.299,00) or Anglo (1,400 / 1,299.00)
    notation, plus the bare 1400 and decimal 12,50 forms.

    With both separators present the rightmost is the decimal point; with one, a
    separator immediately followed by exactly three digits is a thousands
    grouping, otherwise a decimal point.
    """
    s = raw.strip().rstrip(".,").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", "") if re.search(r",\d{3}\b", s) else s.replace(",", ".")
    elif "." in s:
        s = s.replace(".", "") if re.search(r"\.\d{3}\b", s) else s
    try:
        return round(float(s), 2)
    except ValueError:
        return None


G = TypeVar("G")


def match_genres(text: str, table: Sequence[tuple[G, Sequence[str]]], *, default: Sequence[G] = ()) -> list[G]:
    """Genres whose keyword set appears in `text` (case-insensitive).

    `table` is the scraper's local `(genre, keywords)` list. `default` is returned
    when nothing matches — `["classical"]` for most ballet providers, left empty
    where the scraper deliberately emits no fallback genre.
    """
    low = text.lower()
    found = [genre for genre, keys in table if any(k in low for k in keys)]
    return found or list(default)
