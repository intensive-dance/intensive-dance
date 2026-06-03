"""Generate (and drift-check) the published JSON Schema for an Offering.

The Pydantic models in `models.py` are the single source of truth; this module
derives a JSON Schema from them so external consumers and editors have a stable
contract without us hand-maintaining a second copy. A committed
`schema/offering.schema.json` describes one record — a data file under `data/`
is an array of these.

    uv run python -m intensive_dance.schema            # check committed schema is in sync
    uv run python -m intensive_dance.schema --write    # regenerate after a model change

CI runs the check; a drift means the schema was not regenerated after a model
change. The schema is serialized exactly like the data store (sorted keys,
trailing newline) so the file is deterministic and reviewable in a git diff.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from intensive_dance.models import Offering

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "offering.schema.json"
SCHEMA_ID = "https://intensive.dance/schema/offering.schema.json"
DIALECT = "https://json-schema.org/draft/2020-12/schema"


def build_schema() -> dict:
    """The Offering JSON Schema, in serialization shape (matching the data files)."""
    schema = Offering.model_json_schema(by_alias=True, mode="serialization")
    return {"$schema": DIALECT, "$id": SCHEMA_ID, **schema}


def _serialize(schema: dict) -> str:
    return json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    schema = build_schema()
    if "--write" in argv:
        SCHEMA_PATH.parent.mkdir(exist_ok=True)
        SCHEMA_PATH.write_text(_serialize(schema), encoding="utf-8")
        print(f"wrote {SCHEMA_PATH}")
        return 0

    if not SCHEMA_PATH.exists():
        print(f"missing {SCHEMA_PATH} — run: uv run python -m intensive_dance.schema --write", file=sys.stderr)
        return 1
    if json.loads(SCHEMA_PATH.read_text()) != schema:
        print(
            f"{SCHEMA_PATH.name} is out of sync with the models — "
            "run: uv run python -m intensive_dance.schema --write",
            file=sys.stderr,
        )
        return 1
    print(f"ok: {SCHEMA_PATH.name} matches the models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
