"""WordPress REST + WPBakery helpers, shared across WordPress-powered providers.

Many ballet schools run WordPress with the WPBakery (Visual Composer) page
builder, so their page bodies arrive as `content.rendered` HTML peppered with
`[vc_row][vc_column_text]…` shortcodes. The structured fields we want
(headings, dates, fees tables, button links) are all in there once the
shortcode noise is stripped.

API-first: fetch the page record by slug from `/wp-json/wp/v2/pages`, then turn
its `content.rendered` into ordered, heading-keyed sections.
"""

from __future__ import annotations

import html
import re
import urllib.parse
from dataclasses import dataclass

import httpx
from selectolax.parser import HTMLParser, Node

_SHORTCODE = re.compile(r"\[/?[a-z][^\]]*\]")
# WPBakery attribute values are wrapped in either straight or curly quotes
# (the latter survive as the literal characters after entity-unescaping).
_BTN = re.compile(r"\[vc_btn\b([^\]]*)\]")
_BTN_LINK = re.compile(r'link=["“”]?url:([^|"“”\]]+)')
_BTN_TITLE = re.compile(r'title=["“”]?([^|"“”\]]+)')

_BLOCK_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "table"}
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def fetch_page(client: httpx.Client, slug: str, *, base: str) -> dict | None:
    """Return the WP page record for `slug`, or None if it doesn't exist."""
    resp = client.get(f"{base}/wp-json/wp/v2/pages", params={"slug": slug})
    resp.raise_for_status()
    records = resp.json()
    return records[0] if records else None


def fetch_children(client: httpx.Client, parent_id: int, *, base: str) -> list[dict]:
    """Return the published child pages of `parent_id` (id, slug, link, title, content)."""
    resp = client.get(
        f"{base}/wp-json/wp/v2/pages",
        params={"parent": parent_id, "per_page": 100, "_fields": "id,slug,link,title,content"},
    )
    resp.raise_for_status()
    return resp.json()


def button_links(rendered: str) -> dict[str, str]:
    """Map WPBakery `[vc_btn]` button titles to their (decoded) target URLs."""
    text = html.unescape(rendered)
    links: dict[str, str] = {}
    for match in _BTN.finditer(text):
        attrs = match.group(1)
        link = _BTN_LINK.search(attrs)
        if not link:
            continue
        title = _BTN_TITLE.search(attrs)
        key = title.group(1).strip() if title else ""
        links[key] = urllib.parse.unquote(link.group(1))
    return links


@dataclass
class Section:
    """A heading and the block nodes that follow it, until the next heading."""

    heading: str
    level: int  # 1-6, from the h1–h6 tag
    nodes: list[Node]

    def text(self) -> str:
        lines = [n.text(separator=" ", strip=True) for n in self.nodes]
        return "\n".join(line for line in lines if line)

    def table(self) -> Node | None:
        return next((n for n in self.nodes if n.tag == "table"), None)


class Content:
    """Parsed WPBakery page body as ordered, heading-keyed sections."""

    def __init__(self, sections: list[Section], links: dict[str, str]):
        self.sections = sections
        self.links = links

    def find(self, *needles: str) -> Section | None:
        """First section whose heading contains any needle (case-insensitive)."""
        wants = [n.lower() for n in needles]
        for section in self.sections:
            head = section.heading.lower()
            if any(w in head for w in wants):
                return section
        return None

    def find_block(self, *needles: str) -> tuple[Section, list[Section]] | None:
        """A matched section plus the deeper-level subsections nested under it.

        WPBakery pages routinely nest content under `<h6>` sub-headings (e.g. an
        "Application deadlines" `<h3>` with "Selective course" / "Non-selective"
        `<h6>` children), which `find` would otherwise split off into siblings.
        """
        wants = [n.lower() for n in needles]
        for i, section in enumerate(self.sections):
            if any(w in section.heading.lower() for w in wants):
                subs: list[Section] = []
                for nxt in self.sections[i + 1 :]:
                    if nxt.level <= section.level:
                        break
                    subs.append(nxt)
                return section, subs
        return None

    def text(self, *needles: str) -> str:
        section = self.find(*needles)
        return section.text() if section else ""

    def link(self, *needles: str) -> str | None:
        wants = [n.lower() for n in needles]
        for title, url in self.links.items():
            if any(w in title.lower() for w in wants):
                return url
        return None


def parse(rendered: str) -> Content:
    clean = _SHORTCODE.sub("", html.unescape(rendered))
    tree = HTMLParser(clean)
    body = tree.body
    blocks = [n for n in body.traverse(include_text=False) if n.tag in _BLOCK_TAGS] if body else []

    sections: list[Section] = []
    current: Section | None = None
    for node in blocks:
        if node.tag in _HEADING_TAGS:
            heading = node.text(strip=True)
            if not heading:
                continue
            current = Section(heading=heading, level=int(node.tag[1]), nodes=[])
            sections.append(current)
        elif current is not None:
            current.nodes.append(node)
    return Content(sections, button_links(rendered))


def table_rows(table: Node) -> list[list[str]]:
    """Return a table's rows as lists of trimmed cell text."""
    rows: list[list[str]] = []
    for tr in table.css("tr"):
        cells = [td.text(separator=" ", strip=True) for td in tr.css("td, th")]
        if any(cells):
            rows.append(cells)
    return rows
