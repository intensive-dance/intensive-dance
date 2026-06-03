"""The published JSON Schema stays a faithful, committed projection of the models."""

from __future__ import annotations

from intensive_dance import schema


def test_committed_schema_is_in_sync_with_models():
    assert schema.main([]) == 0


def test_schema_carries_id_and_dialect():
    built = schema.build_schema()
    assert built["$schema"] == schema.DIALECT
    assert built["$id"] == schema.SCHEMA_ID


def test_requirements_union_preserved():
    built = schema.build_schema()
    requirements = built["$defs"]["Application"]["properties"]["requirements"]["items"]
    assert requirements["discriminator"]["propertyName"] == "type"
    assert set(requirements["discriminator"]["mapping"]) == {
        "none",
        "photos",
        "video",
        "cv",
        "headshot",
    }
