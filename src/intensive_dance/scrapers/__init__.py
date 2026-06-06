"""Scraper registry.

Each scraper is a pure function `scrape(client) -> list[Offering]` keyed by its
provider slug (see providers.json). The runner walks this map.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx

from intensive_dance.models import Offering

from . import (
    abt_jko_school,
    academie_princesse_grace,
    accademia_teatro_alla_scala,
    art_of_ballet_summer_course,
    ballet_ruso_barcelona,
    brussels_international_ballet,
    central_school_of_ballet,
    dutch_national_ballet_academy,
    ecole_danse_opera_paris,
    english_national_ballet_school,
    finnish_national_ballet,
    fondazione_monreart,
    frankfurt_ballet_masterclasses,
    hong_kong_academy_of_ballet,
    idc_berlin,
    international_ballet_masterclasses_prague,
    japan_ballet_association,
    john_cranko_school,
    joffrey_ballet_school,
    k_ballet_school,
    m_i_ballet_school,
    masters_of_ballet_academy,
    mosa_ballet_school,
    new_national_theatre_ballet_school,
    northern_ballet_academy,
    norwegian_national_ballet,
    pnsd_rosella_hightower,
    royal_ballet_school,
    royal_danish_ballet_summer_school,
    russian_masters_ballet,
    school_of_american_ballet,
    summer_sensation_intensive,
    tokyo_ballet_school,
    young_stars_ballet,
)

Scraper = Callable[[httpx.Client], list[Offering]]

SCRAPERS: dict[str, Scraper] = {
    "royal-ballet-school": royal_ballet_school.scrape,
    "abt-jko-school": abt_jko_school.scrape,
    "joffrey-ballet-school": joffrey_ballet_school.scrape,
    "russian-masters-ballet": russian_masters_ballet.scrape,
    "mosa-ballet-school": mosa_ballet_school.scrape,
    "john-cranko-schule": john_cranko_school.scrape,
    "frankfurt-ballet-masterclasses": frankfurt_ballet_masterclasses.scrape,
    "dutch-national-ballet-academy": dutch_national_ballet_academy.scrape,
    "ecole-danse-opera-paris": ecole_danse_opera_paris.scrape,
    "english-national-ballet-school": english_national_ballet_school.scrape,
    "finnish-national-ballet": finnish_national_ballet.scrape,
    "brussels-international-ballet": brussels_international_ballet.scrape,
    "fondazione-monreart": fondazione_monreart.scrape,
    "academie-princesse-grace": academie_princesse_grace.scrape,
    "school-of-american-ballet": school_of_american_ballet.scrape,
    "young-stars-ballet": young_stars_ballet.scrape,
    "idc-berlin": idc_berlin.scrape,
    "international-ballet-masterclasses-prague": international_ballet_masterclasses_prague.scrape,
    "central-school-of-ballet": central_school_of_ballet.scrape,
    "northern-ballet-academy": northern_ballet_academy.scrape,
    "norwegian-national-ballet": norwegian_national_ballet.scrape,
    "accademia-teatro-alla-scala": accademia_teatro_alla_scala.scrape,
    "hong-kong-academy-of-ballet": hong_kong_academy_of_ballet.scrape,
    "royal-danish-ballet-summer-school": royal_danish_ballet_summer_school.scrape,
    "pnsd-rosella-hightower": pnsd_rosella_hightower.scrape,
    "masters-of-ballet-academy": masters_of_ballet_academy.scrape,
    "m-i-ballet-school": m_i_ballet_school.scrape,
    "new-national-theatre-ballet-school": new_national_theatre_ballet_school.scrape,
    "summer-sensation-intensive": summer_sensation_intensive.scrape,
    "art-of-zurich": art_of_ballet_summer_course.scrape,
    "ballet-ruso-barcelona": ballet_ruso_barcelona.scrape,
    "tokyo-ballet-school": tokyo_ballet_school.scrape,
    "k-ballet-school": k_ballet_school.scrape,
    "japan-ballet-association": japan_ballet_association.scrape,
}
