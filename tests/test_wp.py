"""Unit tests for the WPBakery/wp helpers."""

from __future__ import annotations

from intensive_dance import wp


# --- wp helpers ---------------------------------------------------------------


def test_parse_sections_by_heading():
    content = wp.parse("<h2>Dates</h2><p>21 July 2026</p><h3>Fees</h3><p>£48</p>")
    assert content.text("Dates") == "21 July 2026"
    assert content.text("Fees") == "£48"


def test_parse_strips_wpbakery_shortcodes():
    content = wp.parse(
        "[vc_row][vc_column_text]<h2>Location</h2><p>London</p>[/vc_column_text][/vc_row]"
    )
    assert content.text("Location") == "London"


def test_node_lines_recovers_br_separated_lines():
    content = wp.parse("<h2>Venue</h2><p>White Lodge<br>Richmond Park</p>")
    section = content.find("Venue")
    assert section is not None
    (node,) = section.nodes
    assert wp.node_lines(node) == ["White Lodge", "Richmond Park"]


def test_table_rows():
    section = wp.parse(
        "<h2>Fees</h2><table><tr><th>Course</th><th>Fee</th></tr>"
        "<tr><td>Summer</td><td>£485</td></tr></table>"
    ).find("Fees")
    assert section is not None
    table = section.table()
    assert table is not None
    assert wp.table_rows(table) == [["Course", "Fee"], ["Summer", "£485"]]
