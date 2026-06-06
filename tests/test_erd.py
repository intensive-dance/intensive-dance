"""The ERD generator is deterministic, covers the model tree, and stays in sync."""

from intensive_dance import erd


def test_diagram_has_root_and_union_entities():
    diagram = erd.build_diagram()
    assert diagram.startswith("erDiagram")
    for entity in ("Offering", "Schedule", "Session", "Application", "PhotosReq", "VideoReq"):
        assert f"    {entity} {{" in diagram


def test_relationship_cardinalities():
    diagram = erd.build_diagram()
    assert "Offering ||--|| Source : source" in diagram  # required single
    assert "Offering ||--o| Location : location" in diagram  # optional single
    assert "Offering ||--o{ Teacher : teachers" in diagram  # list
    # the discriminated union fans out to one edge per requirement variant
    assert "Application ||--o{ PhotosReq : requirements" in diagram


def test_named_enums_recovered_and_consts_inlined():
    diagram = erd.build_diagram()
    assert 'Genre[] genres "classical | contemporary' in diagram
    assert 'string type "photos"' in diagram  # single-value Literal → const comment


def test_committed_doc_is_in_sync():
    assert erd.DOC_PATH.read_text(encoding="utf-8") == erd.build_doc(), (
        "docs/erd.md is stale — run: uv run python -m intensive_dance.erd --write"
    )
