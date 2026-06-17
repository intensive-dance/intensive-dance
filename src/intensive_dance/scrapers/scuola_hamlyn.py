"""Scuola di Danza Hamlyn — Florence, IT — its summer course.

API FIRST: **WordPress**. `GET /wp-json/` is live and each edition of the summer
course is a normal post with clean `content.rendered`, so we discover editions
via the REST search (`posts?search=Summer Course`) — no hardcoded year URL.

Hamlyn is a classical (Cecchetti / ISTD) ballet school. The course logistics
(prices, ages, daily programme) are published only inside a **poster image** on
each post, not as text, so we emit the faithful minimum from the post itself —
dates (in the title), the named faculty (`<strong>` headings in the body), genre,
and location — and don't invent fees/ages from the image.

DISCOVERY: the site keeps every edition as its own post ("Summer Course dal 24 al
29 Agosto 2026", "… 2025", …). We emit **one Offering per edition**, year-stamped
(IDR-24 keep-ended-cycles: past editions persist as long as the posts do). We
match only the summer-course posts — the audition/stage posts that merely mention
"summer course" (e.g. "AUDIZIONE-STAGE JOFFREY … SUMMER COURSE", auditions for
*other* schools) don't start with the course title and carry no August span.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-17):
  - DATES: post title "… dal 24 al 29 Agosto 2026" (also "22/27 AGOSTO 2022" /
    "Dal 21 al 26" forms) → a flexible "D (al|/|-) D agosto YYYY" regex; always August.
  - TEACHERS: the faculty named in `<strong>` in the body (only the current
    editions carry them; older posts yield none — left empty, not invented).
  - GENRE: classical (the school's Cecchetti core; the curriculum text is in the
    poster image, so contemporary/repertoire are not asserted).
  - Multiple editions → one Offering each, year-stamped.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
    Location,
    Offering,
    Organization,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://www.scuolahamlyn.com"
POSTS_URL = (
    f"{BASE}/wp-json/wp/v2/posts?search=Summer%20Course&per_page=30&_fields=title,content,link"
)

ORG = Organization(
    name="Scuola di Danza Hamlyn", slug="scuola-hamlyn", country="IT", city="Florence"
)

# "dal 24 al 29 Agosto 2026" / "22/27 AGOSTO 2022" / "Dal 21 al 26 Agosto 2023"
_DATES_RE = re.compile(r"(\d{1,2})\s*(?:al|/|-)\s*(\d{1,2})\s+agosto\s+(\d{4})", re.I)


def scrape(client: httpx.Client) -> list[Offering]:
    posts = client.get(POSTS_URL).json()
    return _build_offerings(posts)


def _strip_tags(html: str) -> str:
    return parse.clean(HTMLParser(html).text()) if html else ""


def _build_offerings(posts: list[dict]) -> list[Offering]:
    offerings: list[Offering] = []
    for post in posts:
        title = _strip_tags(post.get("title", {}).get("rendered", ""))
        if not title.lower().lstrip().startswith("summer course"):
            continue
        match = _DATES_RE.search(title)
        if not match:
            continue
        year = int(match.group(3))
        start = date(year, 8, int(match.group(1)))
        end = date(year, 8, int(match.group(2)))
        content = post.get("content", {}).get("rendered", "")
        offerings.append(
            Offering(
                id=f"scuola-hamlyn/{year}",
                source=Source(
                    provider="scuola-hamlyn", url=post.get("link") or BASE, scrapedAt=now_utc()
                ),
                title=f"Scuola Hamlyn Summer Course {year}",
                genres=["classical"],
                organization=ORG,
                location=Location(city="Florence", country="IT"),
                schedule=Schedule(season="summer", start=start, end=end, notes=title),
                teachers=_teachers(content),
            )
        )
    return offerings


def _teachers(content_html: str) -> list[Teacher]:
    teachers: list[Teacher] = []
    seen: set[str] = set()
    for node in HTMLParser(content_html).css("strong") if content_html else []:
        name = parse.clean(node.text())
        if _is_name(name) and name not in seen:
            seen.add(name)
            teachers.append(Teacher(name=name))
    return teachers


def _is_name(text: str) -> bool:
    if not text or len(text) > 40 or any(c.isdigit() for c in text):
        return False
    words = text.split()
    if not 2 <= len(words) <= 4:
        return False
    return words[0][:1].isupper() and words[-1][:1].isupper()
