"""Offline tests for the Nordsee Akademie — Sommertanztage scraper.

Inline HTML mirrors the TYPO3 event detail (span.teaser__date header + prose
body) and the /programm index. No network.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from intensive_dance.scrapers import nordsee_akademie_sommertanztage as nsa

INDEX = """
<html><body><main>
<a href="/programm/sommertanztage-i-2026">Sommertanztage I 2026 - Anmeldung</a>
<a href="/programm/momentum-young-dancers-intensive">Momentum - Young Dancers Intensive</a>
<a href="/programm/sommertanztage-ii-2026">Sommertanztage II 2026 - Anmeldung</a>
<a href="/programm/lecker-musiktage">Lecker Musiktage</a>
<!-- slider repeats the same links -->
<a href="/programm/sommertanztage-i-2026#slider">Sommertanztage I 2026</a>
</main></body></html>
"""

DETAIL_I = """
<html><body><main>
<strong class="headline">
  <span><span class="teaser__date">05.07.2026 <span aria-hidden="true">–</span>
  <span class="visually-hidden">bis</span> 11.07.2026</span></span>
</strong>
<h1>Sommertanztage I 2026 - Anmeldung weiterhin geöffnet</h1>
<p>Für Kinder und Jugendliche zwischen 11 und 19 Jahren bieten wir täglichen
Unterricht in alters- und leistungsangepassten Klassen an. Neben klassischem
Ballett (für die Älteren ggf. auch mit Spitzentanz) stehen Contemporary und
Musical Jazz auf dem Stundenplan. Die jüngeren Teilnehmenden haben außerdem
Charaktertanz. In den älteren Klassen steht die Erarbeitung eines
Repertoirestücks aus den berühmten Ballettwerken auf dem Programm.</p>
<p>Lehrkräfte: Maike Jürgensen (Künstlerische Leitung). Inhaberin der
Tanzakademie Hannover-Neustadt.</p>
<p>Preise. Preis pro Person: 740,00 €. Geschwisterrabatt: 50 € pro Familie.
Der Seminarpreis umfasst Unterbringung, drei Mahlzeiten pro Tag und den
kompletten Unterricht. Anmeldung weiterhin geöffnet.</p>
<p>Veranstaltungsort: Nordsee Akademie, Flensburger Straße 18, 25917 Leck</p>
</main>
<aside><span class="teaser__date">12.07.2026 – 18.07.2026</span></aside>
</body></html>
"""


def test_index_discovers_only_sommertanztage_dedup():
    urls = nsa._edition_urls(INDEX)
    assert urls == [
        "https://www.nordsee-akademie.de/programm/sommertanztage-i-2026",
        "https://www.nordsee-akademie.de/programm/sommertanztage-ii-2026",
    ]


def test_detail_core_fields():
    o = nsa._build_offering(
        DETAIL_I, "https://www.nordsee-akademie.de/programm/sommertanztage-i-2026"
    )
    assert o.id == "nordsee-akademie-sommertanztage/sommertanztage-i-2026"
    assert o.title == "Sommertanztage I 2026"
    # the header date is used, NOT the slider's 12–18 Jul date in the aside
    assert o.schedule.start == date(2026, 7, 5)
    assert o.schedule.end == date(2026, 7, 11)
    assert o.schedule.season == "2026"
    assert o.age_range == {"min": 11, "max": 19}
    assert o.location is not None
    assert o.location.city == "Leck"


def test_genres_drop_jazz_keep_ballet_family():
    o = nsa._build_offering(
        DETAIL_I, "https://www.nordsee-akademie.de/programm/sommertanztage-i-2026"
    )
    assert o.genres == ["classical", "pointe", "contemporary", "character", "repertoire"]


def test_price_bundles_residential():
    o = nsa._build_offering(
        DETAIL_I, "https://www.nordsee-akademie.de/programm/sommertanztage-i-2026"
    )
    assert len(o.prices) == 1
    p = o.prices[0]
    assert p.amount == 740.0
    assert p.currency == "EUR"
    assert p.type == "tuition"
    assert set(p.includes) == {"tuition", "accommodation", "meals"}
    assert "Geschwisterrabatt" in (p.notes or "")


def test_teacher_and_application():
    o = nsa._build_offering(
        DETAIL_I, "https://www.nordsee-akademie.de/programm/sommertanztage-i-2026"
    )
    assert [t.name for t in o.teachers] == ["Maike Jürgensen"]
    assert o.teachers[0].affiliations[0].organization == "Tanzakademie Hannover-Neustadt"
    assert o.application.status == "open"


def test_empty_index_raises():
    # An index with no Sommertanztage links is a degraded fetch → raise, not [].
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, html="<html><body><main><a href='/programm/x'>x</a></main></body></html>"
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError):
            nsa.scrape(client)
