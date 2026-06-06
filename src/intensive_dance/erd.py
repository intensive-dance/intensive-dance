"""Generate (and drift-check) the Mermaid entity-relationship diagram for an Offering.

The Pydantic models in `models.py` are the single source of truth; this module
introspects the `Offering` tree and renders a Mermaid `erDiagram` into
`docs/erd.md`. GitHub renders Mermaid in any markdown file view, so that file
*is* the published diagram — no rendering step or docs site needed.

    uv run python -m intensive_dance.erd            # check committed diagram is in sync
    uv run python -m intensive_dance.erd --write    # regenerate after a model change

CI runs the check; a drift means the diagram was not regenerated after a model
change (same gate as `schema.py`). Output is deterministic (declaration order,
trailing newline) so the file is reviewable in a git diff.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Annotated, Literal, Union, get_args, get_origin

from pydantic import BaseModel

from intensive_dance import models
from intensive_dance.models import Offering

DOC_PATH = Path(__file__).resolve().parents[2] / "docs" / "erd.md"

_SCALARS: dict[type, str] = {
    str: "string",
    int: "int",
    float: "float",
    bool: "boolean",
}
_SCALAR_NAMES = {"date": "date", "datetime": "datetime", "dict": "object"}

_UNION_ORIGINS = (Union, types.UnionType)


def _unwrap_annotated(ann: object) -> object:
    return get_args(ann)[0] if get_origin(ann) is Annotated else ann


def _strip_optional(ann: object) -> object:
    """Drop `Annotated` wrappers and a trailing `| None`, leaving the core type."""
    ann = _unwrap_annotated(ann)
    if get_origin(ann) in _UNION_ORIGINS:
        non_none = [a for a in get_args(ann) if a is not type(None)]
        if len(non_none) == 1:
            return _strip_optional(non_none[0])
    return ann


def _referenced_models(ann: object) -> list[type[BaseModel]]:
    """Every `BaseModel` subclass anywhere in an annotation, in stable order."""
    ann = _unwrap_annotated(ann)
    if isinstance(ann, type) and issubclass(ann, BaseModel):
        return [ann]
    out: list[type[BaseModel]] = []
    for arg in get_args(ann):
        for model in _referenced_models(arg):
            if model not in out:
                out.append(model)
    return out


def _is_list(ann: object) -> bool:
    ann = _unwrap_annotated(ann)
    origin = get_origin(ann)
    if origin in (list, set, tuple):
        return True
    return any(_is_list(a) for a in get_args(ann)) if origin is not None else False


def _is_optional(ann: object) -> bool:
    ann = _unwrap_annotated(ann)
    if get_origin(ann) in _UNION_ORIGINS:
        return any(a is type(None) for a in get_args(ann))
    return False


def _named_enums() -> dict[frozenset, str]:
    """Module-level `Literal` aliases keyed by their value set, for type-name recovery."""
    out: dict[frozenset, str] = {}
    for name, value in vars(models).items():
        if get_origin(value) is Literal:
            out[frozenset(get_args(value))] = name
    return out


_NAMED_ENUMS = _named_enums()


def _scalar_attr(ann: object) -> tuple[str, str | None]:
    """A non-relationship field rendered as `(type_token, enum_values_comment)`."""
    ann = _strip_optional(ann)
    origin = get_origin(ann)

    if origin in (list, set, tuple):
        token, comment = _scalar_attr(get_args(ann)[0])
        return f"{token}[]", comment

    if origin is Literal:
        values = list(get_args(ann))
        if len(values) == 1:  # a discriminator const, not an enum
            return "string", str(values[0])
        token = _NAMED_ENUMS.get(frozenset(values), "enum")
        return token, " | ".join(map(str, values))

    if isinstance(ann, type) and ann in _SCALARS:
        return _SCALARS[ann], None
    return _SCALAR_NAMES.get(getattr(ann, "__name__", ""), "string"), None


def _alias(model: type[BaseModel], field_name: str) -> str:
    return model.model_fields[field_name].alias or field_name


def _cardinality(ann: object) -> str:
    if _is_list(ann):
        return "||--o{"
    return "||--o|" if _is_optional(ann) else "||--||"


def _entity_order() -> list[type[BaseModel]]:
    """Models reachable from `Offering`, breadth-first in field-declaration order."""
    order: list[type[BaseModel]] = [Offering]
    seen: set[type[BaseModel]] = {Offering}
    queue: list[type[BaseModel]] = [Offering]
    while queue:
        for field in queue.pop(0).model_fields.values():
            for model in _referenced_models(field.annotation):
                if model not in seen:
                    seen.add(model)
                    order.append(model)
                    queue.append(model)
    return order


def build_diagram() -> str:
    """The Mermaid `erDiagram` source (no fences)."""
    entities = _entity_order()
    lines = ["erDiagram"]
    relationships: list[str] = []

    for entity in entities:
        attrs: list[str] = []
        for name, field in entity.model_fields.items():
            ann = field.annotation
            targets = _referenced_models(ann)
            if targets:
                label = _alias(entity, name)
                card = _cardinality(ann)
                relationships += [
                    f"    {entity.__name__} {card} {t.__name__} : {label}" for t in targets
                ]
                continue
            token, comment = _scalar_attr(ann)
            line = f"        {token} {_alias(entity, name)}"
            attrs.append(f'{line} "{comment}"' if comment else line)
        lines.append(f"    {entity.__name__} {{")
        lines += attrs
        lines.append("    }")

    lines += relationships
    return "\n".join(lines)


def build_doc() -> str:
    return (
        "# Entity-relationship diagram\n\n"
        "Generated from the Pydantic models in `src/intensive_dance/models.py` — "
        "**do not edit by hand**. Regenerate after a model change with "
        "`uv run python -m intensive_dance.erd --write` (CI fails on drift). "
        "Companion to [`data-model.md`](./data-model.md), which is the prose source of truth.\n\n"
        "```mermaid\n" + build_diagram() + "\n```\n"
    )


def main(argv: list[str]) -> int:
    doc = build_doc()
    if "--write" in argv:
        DOC_PATH.parent.mkdir(exist_ok=True)
        DOC_PATH.write_text(doc, encoding="utf-8")
        print(f"wrote {DOC_PATH}")
        return 0

    if not DOC_PATH.exists():
        print(
            f"missing {DOC_PATH} — run: uv run python -m intensive_dance.erd --write",
            file=sys.stderr,
        )
        return 1
    if DOC_PATH.read_text(encoding="utf-8") != doc:
        print(
            f"{DOC_PATH.name} is out of sync with the models — "
            "run: uv run python -m intensive_dance.erd --write",
            file=sys.stderr,
        )
        return 1
    print(f"ok: {DOC_PATH.name} matches the models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
