"""Governed operator and dimension-type vocabulary — T019 (FR-005; SC-001).

The enums are declared here and **checked against** the governed YAML rather than
built from it at import time. Generating the members dynamically would make the
type opaque to Pyright and untypable at call sites; declaring them and asserting
agreement keeps both properties — static types, and a single governed source that
CI proves the code still matches.

Deny-by-default throughout: an operator absent from the allowlist is refused at
parse, and a dimension with no declared type is refused rather than defaulted to
the most permissive one.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Final, cast

import yaml

__all__ = [
    "DIMENSION_TYPE_ASSIGNMENTS",
    "OPERATOR_ARITY",
    "Arity",
    "DimensionType",
    "GovernedOperator",
    "governed_content_root",
    "load_dimension_types",
    "load_operators",
]


class GovernedOperator(StrEnum):
    """The closed operator allowlist. Anything else is ``OPERATOR_NOT_GOVERNED``."""

    EQ = "eq"
    NE = "ne"
    IN = "in"
    NOT_IN = "not_in"
    BETWEEN = "between"


class DimensionType(StrEnum):
    """The closed dimension-type vocabulary this feature authors (`BO-6`).

    ``temporal_date`` is a valid **result and breakdown** type but is not
    filterable: ``date_range`` is the sole temporal bound.
    """

    ENUMERATED_TEXT = "enumerated_text"
    OPEN_TEXT = "open_text"
    TEMPORAL_DATE = "temporal_date"


class Arity(StrEnum):
    """How many values an operator takes. Violations are ``REQUEST_MALFORMED``."""

    EXACTLY_ONE = "exactly_one"
    ONE_OR_MORE = "one_or_more"
    EXACTLY_TWO = "exactly_two"


OPERATOR_ARITY: Final[dict[GovernedOperator, Arity]] = {
    GovernedOperator.EQ: Arity.EXACTLY_ONE,
    GovernedOperator.NE: Arity.EXACTLY_ONE,
    GovernedOperator.IN: Arity.ONE_OR_MORE,
    GovernedOperator.NOT_IN: Arity.ONE_OR_MORE,
    GovernedOperator.BETWEEN: Arity.EXACTLY_TWO,
}

#: Every dimension `001` exposes, mapped to exactly one type. A dimension absent
#: from this mapping is refused with ``DIMENSION_TYPE_UNDECLARED``.
DIMENSION_TYPE_ASSIGNMENTS: Final[dict[str, DimensionType]] = {
    "platform": DimensionType.ENUMERATED_TEXT,
    "product": DimensionType.ENUMERATED_TEXT,
    "store": DimensionType.ENUMERATED_TEXT,
    "country": DimensionType.OPEN_TEXT,
    "app_version": DimensionType.OPEN_TEXT,
    "date": DimensionType.TEMPORAL_DATE,
}


def governed_content_root() -> Path:
    """``query_governance/`` at the repository root.

    Located by walking up from this module rather than by configuration: a
    settable path would be a runtime switch over governed content, which is
    exactly what must not exist.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "query_governance"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("query_governance/ not found above " + str(here))


def _load(name: str) -> dict[str, object]:
    raw: object = yaml.safe_load((governed_content_root() / name).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{name}: expected a mapping at the document root")
    return cast(dict[str, object], raw)


def load_operators() -> dict[str, str]:
    """``{operator id: arity}`` as authored in ``query_governance/operators.yaml``."""
    document = _load("operators.yaml")
    entries: object = document.get("operators", [])
    if not isinstance(entries, list):
        raise ValueError("operators.yaml: `operators` must be a list")
    loaded: dict[str, str] = {}
    for raw_entry in cast(list[object], entries):
        if not isinstance(raw_entry, dict):
            raise ValueError("operators.yaml: each operator must be a mapping")
        entry = cast(dict[str, object], raw_entry)
        identifier = entry.get("id")
        arity = entry.get("arity")
        if not isinstance(identifier, str) or not isinstance(arity, str):
            raise ValueError("operators.yaml: each operator needs a string `id` and `arity`")
        loaded[identifier] = arity
    return loaded


def load_dimension_types() -> tuple[dict[str, bool], dict[str, str]]:
    """``({type id: ordered}, {dimension: type id})`` from the governed vocabulary."""
    document = _load("dimension-types.yaml")
    raw_types: object = document.get("types", [])
    raw_assignments: object = document.get("assignments", [])
    if not isinstance(raw_types, list) or not isinstance(raw_assignments, list):
        raise ValueError("dimension-types.yaml: `types` and `assignments` must be lists")

    types: dict[str, bool] = {}
    for raw_entry in cast(list[object], raw_types):
        if not isinstance(raw_entry, dict):
            raise ValueError("dimension-types.yaml: each type must be a mapping")
        entry = cast(dict[str, object], raw_entry)
        identifier = entry.get("id")
        ordered = entry.get("ordered")
        if not isinstance(identifier, str) or not isinstance(ordered, bool):
            raise ValueError("dimension-types.yaml: each type needs `id` and boolean `ordered`")
        types[identifier] = ordered

    assignments: dict[str, str] = {}
    for raw_entry in cast(list[object], raw_assignments):
        if not isinstance(raw_entry, dict):
            raise ValueError("dimension-types.yaml: each assignment must be a mapping")
        entry = cast(dict[str, object], raw_entry)
        dimension = entry.get("dimension")
        type_id = entry.get("type")
        if not isinstance(dimension, str) or not isinstance(type_id, str):
            raise ValueError("dimension-types.yaml: each assignment needs `dimension` and `type`")
        assignments[dimension] = type_id

    return types, assignments
