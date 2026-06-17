"""Accademia Iacopini — "IN DANZA" summer stage, Chianciano Terme IT.

API FIRST: WordPress with `/wp-json/`, but the fetch proxy renders this host's
JSON through Chromium's JSON viewer on **every** tier (the body comes back inside
`<pre>`, HTML-escaped), so `wp.fetch_*` (which call `resp.json()`) can't parse it
— we fetch the raw text and `wp.unwrap_json_viewer` it. The page body is raw,
un-rendered Jupiter/WPBakery shortcodes (`[mk_fancy_title]`, `[vc_column_text]`),
so there are no `<h*>` headings for `wp.parse`; we slice the flat shortcode-block
run instead (cf. `accademia_internazionale_coreutica`). The fee table is a
base64-encoded `[vc_raw_html]` card grid — we decode and read `.quote-card`s.

DISCOVERY: the org runs one dated stage, "IN DANZA", once a year (each edition is
its own post `in_danza_<n>_edizione`); we pick the **latest edition number** (the
current one). Older editions use an entirely different page layout (no fee table,
free-text dates) so parsing them would invent data — this is a discovery scope,
not a date cut (cf. `benedict_manniegel`'s latest-revision rule). The current
edition offers **three enrollment variants** with distinct ages and fees, so we
emit **one Offering per variant**:
  - Stage (ages 11–22, two classes Intermedio/Avanzato), €750 (€650 early-bird).
  - Percorso di Perfezionamento (ages 16–22, selected), €450 alone / €250 add-on.
  - Kids (ages 8–10), €300.
All run the same week in Chianciano Terme. Year-stamped slugs; kept per IDR-24.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-17):
  - The JSON-viewer unwrap + base64 `[vc_raw_html]` fee-table decode.
  - DATES: "26 Luglio – 1 Agosto 2026" — Italian month map, optional ° ordinal.
  - GENRES: a masterclass stage's disciplines are its named faculty's specialties
    — classical (Wiener Staatsballett ballet master, Vaganova teacher, étoile,
    maître de ballet) + contemporary (Joffrey contemporary trainee director);
    modern/jazz/musical are out of our enum. Matched on the faculty roles, not the
    generic blurb.
  - AGES per variant, anchored on each variant's name (11–22 / 16–22 / 8–10).
  - TEACHERS: clean Name / role block pairs in the "Docenti" run; attributed to
    the Stage + Perfezionamento (the Kids track names no teachers of its own).
  - LEVELS: only the Stage states them ("Intermedio e Avanzato"); the others are
    left unstated rather than guessed.
"""

from __future__ import annotations

import base64
import html
import re
import urllib.parse
from datetime import date
from typing import Any

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse, wp
from intensive_dance.models import (
    Application,
    Genre,
    Level,
    Location,
    Offering,
    Organization,
    Price,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://accademiaiacopini.it"
PROVIDER = "accademia-iacopini"

ORG = Organization(name="Accademia Iacopini", slug=PROVIDER, country="IT", city="Chianciano Terme")

_MONTHS_IT = {
    "gennaio": 1,
    "febbraio": 2,
    "marzo": 3,
    "aprile": 4,
    "maggio": 5,
    "giugno": 6,
    "luglio": 7,
    "agosto": 8,
    "settembre": 9,
    "ottobre": 10,
    "novembre": 11,
    "dicembre": 12,
}
_MONTHALT = parse.months_alt(_MONTHS_IT)
_DATES = re.compile(
    r"(\d{1,2})°?\s+(" + _MONTHALT + r")\s*[–-]\s*(\d{1,2})°?\s+(" + _MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)
_EDITION_SLUG = re.compile(r"in_danza_(\d+)_edizione")
_EURO = re.compile(r"€\s*([\d.,]+)")

_GENRES: list[tuple[Genre, list[str]]] = [
    (
        "classical",
        ["classic", "ballet master", "maitre de ballet", "etoile", "vaganova", "ballerino"],
    ),
    ("contemporary", ["contemporary", "contemporanea"]),
]
_LEVELS: list[tuple[Level, str]] = [
    ("intermediate", "intermedio"),
    ("advanced", "avanzato"),
]


def scrape(client: httpx.Client) -> list[Offering]:
    post = _latest_edition(client)
    return _build_offerings([post], date.today()) if post else []


def _get(client: httpx.Client, path: str, params: dict) -> Any:
    resp = client.get(f"{BASE}{path}", params=params)
    resp.raise_for_status()
    return wp.unwrap_json_viewer(resp.text)


def _latest_edition(client: httpx.Client) -> dict | None:
    listing = _get(
        client, "/wp-json/wp/v2/posts", {"search": "edizione", "per_page": 50, "_fields": "id,slug"}
    )
    editions = [
        (int(m.group(1)), record["id"])
        for record in listing
        if isinstance(record, dict) and (m := _EDITION_SLUG.fullmatch(record.get("slug", "")))
    ]
    if not editions:
        return None
    _, post_id = max(editions)
    post = _get(
        client, f"/wp-json/wp/v2/posts/{post_id}", {"_fields": "id,slug,title,link,content"}
    )
    return post if isinstance(post, dict) else None


def _blocks(rendered: str) -> list[str]:
    """Ordered text of each `[vc_column_text]` / `[mk_fancy_title]` block."""
    out: list[str] = []
    for raw in re.findall(
        r"\[(?:vc_column_text|mk_fancy_title)[^\]]*\](.*?)\[/(?:vc_column_text|mk_fancy_title)\]",
        rendered,
        re.DOTALL,
    ):
        text = parse.clean(re.sub(r"<[^>]+>", " ", html.unescape(raw)))
        if text:
            out.append(text)
    return out


def _dates(text: str) -> tuple[date, date] | None:
    m = _DATES.search(text)
    if not m:
        return None
    d1, m1, d2, m2, year = m.groups()
    y = int(year)
    return (
        date(y, _MONTHS_IT[m1.lower()], int(d1)),
        date(y, _MONTHS_IT[m2.lower()], int(d2)),
    )


def _age_for(text: str, anchor: str) -> dict | None:
    m = re.search(
        re.escape(anchor) + r"[^.]{0,80}?tra\s+(?:gli|i)\s+(\d+)\s+e\s+i\s+(\d+)\s+anni",
        text,
        re.IGNORECASE,
    )
    return {"min": int(m.group(1)), "max": int(m.group(2))} if m else None


def _teachers(blocks: list[str]) -> list[Teacher]:
    """The Name / role pairs in the run between the faculty intro and the next heading."""
    try:
        start = next(i for i, b in enumerate(blocks) if "guidato da" in b.lower())
        end = next(
            i
            for i, b in enumerate(blocks)
            if i > start and "danza" in b.lower() and "edizione" in b.lower()
        )
    except StopIteration:
        return []
    region = blocks[start + 1 : end]
    out: list[Teacher] = []
    for i in range(0, len(region) - 1, 2):
        name, role = region[i].strip(), region[i + 1].strip()
        if name and len(name.split()) <= 4:
            out.append(Teacher(name=name, role=role or None))
    return out


def _fees(rendered: str) -> dict[str, list[str]]:
    """Map each card head (lowercased) to its euro amounts, from the `[vc_raw_html]` table."""
    raws = re.findall(r"\[vc_raw_html[^\]]*\](.*?)\[/vc_raw_html\]", rendered, re.DOTALL)
    if not raws:
        return {}
    encoded = html.unescape(raws[0]).strip().strip('"').strip("”“")
    try:
        decoded = urllib.parse.unquote(base64.b64decode(encoded).decode("utf-8", "replace"))
    except ValueError:  # binascii.Error (bad base64) subclasses ValueError
        return {}
    decoded = re.sub(r"<style.*?</style>", " ", decoded, flags=re.DOTALL)
    fees: dict[str, list[str]] = {}
    for card in HTMLParser(decoded).css(".quote-card"):
        head = card.css_first(".quote-head")
        if not head:
            continue
        key = parse.clean(head.text(separator=" ")).lower()
        fees[key] = _EURO.findall(card.text(separator=" "))
    return fees


def _price(raw_amount: str | None, *, label: str, notes: str | None = None) -> Price | None:
    amount = parse.parse_amount(raw_amount) if raw_amount else None
    if amount is None:
        return None
    return Price(amount=amount, currency="EUR", label=label, includes=["tuition"], notes=notes)


def _fee_for(fees: dict[str, list[str]], *needles: str) -> list[str]:
    for key, amounts in fees.items():
        if all(n in key for n in needles):
            return amounts
    return []


def _build_offerings(posts: list[dict], today: date) -> list[Offering]:
    offerings: list[Offering] = []
    for post in posts:
        rendered = post["content"]["rendered"]
        blocks = _blocks(rendered)
        text = "\n".join(blocks)
        span = _dates(text)
        if span is None:
            continue
        start, end = span
        title = _title(html.unescape(post["title"]["rendered"]))
        faculty = _teachers(blocks)
        genres = parse.match_genres(" ".join(t.role or "" for t in faculty), _GENRES)
        fees = _fees(rendered)

        stage_fees = _fee_for(fees, "stage")
        offerings.append(
            _offering(
                post=post,
                org_title=title,
                start=start,
                end=end,
                genres=genres,
                variant="stage",
                label="Stage",
                age=_age_for(text, "accedere a INdanza"),
                levels=[lvl for lvl, key in _LEVELS if key in text.lower()],
                teachers=faculty,
                prices=[
                    p
                    for p in [
                        _price(
                            stage_fees[0] if stage_fees else None,
                            label="Quota totale",
                            notes="€350 acconto + €400 saldo. "
                            "Early booking €650 entro il 30 aprile 2026.",
                        )
                    ]
                    if p
                ],
                notes="Masterclass | Private Coaching | Mentoring | Selection | Gala",
            )
        )

        perf_fees = _fee_for(fees, "perfezionamento")
        offerings.append(
            _offering(
                post=post,
                org_title=title,
                start=start,
                end=end,
                genres=genres,
                variant="perfezionamento",
                label="Percorso di Perfezionamento",
                age=_age_for(text, "percorso unico"),
                levels=[],
                teachers=faculty,
                prices=[
                    p
                    for p in [
                        _price(
                            perf_fees[0] if perf_fees else None,
                            label="Percorso unico",
                            notes="Pagamento dovuto solo a seguito di ammissione.",
                        ),
                        _price(
                            perf_fees[1] if len(perf_fees) > 1 else None,
                            label="Quota integrativa (in aggiunta a INdanza)",
                        ),
                    ]
                    if p
                ],
                notes="Percorso intensivo per allievi selezionati, con ore di studio "
                "aggiuntive, affiancato allo Stage.",
            )
        )

        kids_fees = _fee_for(fees, "kids")
        offerings.append(
            _offering(
                post=post,
                org_title=title,
                start=start,
                end=end,
                genres=genres,
                variant="kids",
                label="Kids",
                age=_age_for(text, "INdanza Kids"),
                levels=[],
                teachers=[],
                prices=[
                    p
                    for p in [
                        _price(
                            kids_fees[0] if kids_fees else None,
                            label="Quota totale",
                            notes="€150 acconto + €150 saldo.",
                        )
                    ]
                    if p
                ],
                notes=None,
            )
        )
    offerings.sort(key=lambda o: o.id)
    return offerings


def _title(raw: str) -> str:
    return parse.clean(raw.replace('"', "").replace("”", "").replace("“", "")).strip()


def _offering(
    *,
    post: dict,
    org_title: str,
    variant: str,
    label: str,
    start: date,
    end: date,
    genres: list[Genre],
    age: dict | None,
    levels: list[Level],
    teachers: list[Teacher],
    prices: list[Price],
    notes: str | None,
) -> Offering:
    return Offering(
        id=f"{PROVIDER}/{start.year}-{variant}",
        source=Source(provider=PROVIDER, url=post["link"], scrapedAt=now_utc()),
        title=f"{org_title} — {label}",
        genres=genres,
        level=levels,
        ageRange=age,
        organization=ORG,
        location=Location(city="Chianciano Terme", country="IT"),
        schedule=Schedule(
            season="summer", start=start, end=end, timezone="Europe/Rome", notes=notes
        ),
        teachers=teachers,
        prices=prices,
        application=Application(
            url=post["link"],
            notes="Iscrizione tramite modulo di iscrizione e certificato medico sportivo; "
            "le iscrizioni chiudono al raggiungimento della capienza.",
        ),
    )
