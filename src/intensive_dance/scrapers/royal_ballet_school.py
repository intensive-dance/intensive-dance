"""The Royal Ballet School — first scraper.

STUB. The live scrape is tracked in issue #1.

API FIRST: RBS runs on WordPress and exposes a public REST API — no HTML
parsing needed for the core fields. Fetch the page record by slug:

    https://www.royalballetschool.org.uk/wp-json/wp/v2/pages?slug=uk-summer-intensive

`content.rendered` is WPBakery shortcode markup ([vc_row][vc_column_text]…), so
the body still needs light cleaning, but dates/title/links come straight from
JSON. Fees may live in the WooCommerce store API (the `wc/v3` namespace is
enabled); the application-fee figure (£48 for 2026) and full course fees are on
a separate fees page. Photo pose guidelines are on the Intensive Courses FAQs /
"photograph requirements" pages, not this one.

RBS intensives are assessed on PHOTO submissions only — no video, no in-person
audition. So this provider exercises the `photos` (+ likely `headshot`) branch
of the requirements union, NOT `video`. Pick a video-requiring provider (e.g.
Joffrey / ABT summer intensives) to exercise that branch.

Reference pattern (delete once implemented):

    page = client.get(API_URL, params={"slug": "uk-summer-intensive"}).json()[0]
    offering = Offering(
        id="royal-ballet-school/uk-summer-intensive-2026",
        source=Source(provider="royal-ballet-school", url=page["link"], scrapedAt=now_utc()),
        title="UK Summer Intensive 2026",
        genres=["classical"],
        kind="intensive",
        organization=Organization(
            name="The Royal Ballet School", slug="royal-ballet-school", country="GB", city="London"
        ),
        schedule=Schedule(season="2026", timezone="Europe/London"),
        application=Application(
            requirements=[PhotosReq(specificity="defined-poses", poses=[...])],
        ),
    )
    offering.source.hash = offering.content_hash()
    return [offering]
"""

from __future__ import annotations

import httpx

from intensive_dance.models import Offering

API_URL = "https://www.royalballetschool.org.uk/wp-json/wp/v2/pages"
PROGRAM_URL = "https://www.royalballetschool.org.uk/train/dancer-training/intensive-courses/uk-summer-intensive/"


def scrape(client: httpx.Client) -> list[Offering]:
    raise NotImplementedError("Live RBS scrape — see https://github.com/boredland/intensive-dance/issues/1")
