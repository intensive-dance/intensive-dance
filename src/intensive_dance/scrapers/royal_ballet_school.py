"""The Royal Ballet School — first scraper.

STUB. The live scrape is tracked in issue #1. The function shape is the
contract every scraper follows; fill in fetch + parse to return one validated
`Offering` per intensive cycle.

Reference pattern (delete once implemented):

    html = client.get(PROGRAM_URL).text
    tree = HTMLParser(html)
    offering = Offering(
        id="royal-ballet-school/summer-intensive-2026",
        source=Source(provider="royal-ballet-school", url=PROGRAM_URL, scrapedAt=now_utc()),
        title="Summer Intensive 2026",
        genres=["classical", "contemporary"],
        kind="intensive",
        organization=Organization(
            name="The Royal Ballet School", slug="royal-ballet-school", country="GB", city="London"
        ),
        schedule=Schedule(season="2026", timezone="Europe/London"),
        application=Application(
            requirements=[
                PhotosReq(specificity="defined-poses", poses=[...]),
                VideoReq(specificity="specific", description="..."),
            ]
        ),
    )
    offering.source.hash = offering.content_hash()
    return [offering]
"""

from __future__ import annotations

import httpx

from intensive_dance.models import Offering

PROGRAM_URL = "https://www.royalballetschool.org.uk/training/short-courses-intensives/"


def scrape(client: httpx.Client) -> list[Offering]:
    raise NotImplementedError("Live RBS scrape — see https://github.com/boredland/intensive-dance/issues/1")
