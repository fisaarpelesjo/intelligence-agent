"""Schema-version upgrade path — T024 (FR-006).

The loader accepts every version in ``SUPPORTED_SCHEMA_VERSIONS`` so a schema change and a content
change never have to land in the same pull request (research §R-12). This module
holds the in-memory migrations that carry an older payload forward. The window was two
versions wide until `D-1303` widened it to three; the tuple states the width and this
sentence does not repeat the number.

Two properties the migrations must keep:

* **in-memory only** — the authored file on disk is never rewritten by a load.
  A read that mutates its input makes "what does this file say" ambiguous;
* **total** — every accepted version has a path to ``N``. A version inside the
  supported window with no migration is a bug, so it raises rather than passing
  the payload through unchanged.

**The first migration landed on 2026-08-30, and it is 1 -> 2.** The machinery was
built before it existed precisely so that the first migration would not also be the
moment the mechanism was designed — and that turned out to be worth it: 1 -> 2 adds
`kpi_name` and `value_column`, and the only correct migration is to add NEITHER.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ..contracts._base import SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS

__all__ = ["MigrationError", "migration_path", "upgrade_payload"]


class MigrationError(Exception):
    """No migration exists for a version inside the supported window."""


def _one_to_two(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Version 1 to 2 — and it adds nothing, which is the whole point.

    Version 2 lets a metric declare `kpi_name` and `value_column` (`FR-806`, `FR-808`).
    **A migration that filled either one in would be inventing a declaration nobody
    authored**, and `value_column` in particular has a tempting default — `value` — which
    is *exactly* the default that published MRR and Revenue as valueless.

    So a version-1 contract arrives at version 2 with both fields absent, the model leaves
    them `None`, and every reader that needs one refuses instead of guessing. The twelve
    contracts this applies to point at views the warehouse does not hold: they have no
    observable column, and having none is the honest answer.

    Returned as a new mapping; the input is never mutated.
    """
    return dict(payload)


def _two_to_three(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Version 2 to 3 — and it adds nothing either, for the same reason as its predecessor.

    Version 3 lets a metric declare ``lower_is_better``: which direction is good for it
    (`D-1303`, `OD-113`). **A migration that filled it in would be inventing a decision
    nobody made**, and the tempting source is right there — the view carries a column of the
    same name. Reading it here would defeat the point of the move: the whole reason the field
    exists in the contract is that a property of the METRIC should not be answered by another
    repository's table.

    So a version-2 contract arrives at version 3 with the field absent, the model leaves it
    ``None``, and the report prints no colour for that metric — which is exactly what it
    already did before any of this, and is a true statement rather than a guess.

    Returned as a new mapping; the input is never mutated.
    """
    return dict(payload)


#: ``version -> migrate to version + 1``. Each entry is pure: it returns a new
#: mapping and never mutates its argument.
_MIGRATIONS: Mapping[int, Callable[[Mapping[str, Any]], dict[str, Any]]] = {
    1: _one_to_two,
    2: _two_to_three,
}


def migration_path(from_version: int) -> tuple[int, ...]:
    """Versions traversed to reach :data:`SCHEMA_VERSION`, excluding the start."""
    return tuple(range(from_version + 1, SCHEMA_VERSION + 1))


def upgrade_payload(payload: Mapping[str, Any], *, from_version: int) -> dict[str, Any]:
    """Carry an authored payload forward to the current schema version.

    Returns a new mapping; the input is never mutated. Raises
    :class:`MigrationError` if a supported version has no migration — silently
    returning the payload unchanged would let an old file validate against a new
    model and fail with a confusing field error instead of a clear one.
    """
    if from_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise MigrationError(
            f"version {from_version} is outside the supported window "
            f"{sorted(SUPPORTED_SCHEMA_VERSIONS)}; the loader refuses it before migration"
        )

    upgraded = dict(payload)
    for target in migration_path(from_version):
        migrate = _MIGRATIONS.get(target - 1)
        if migrate is None:
            raise MigrationError(
                f"no migration from schema version {target - 1} to {target}; "
                "every supported version must have a path to the current one"
            )
        upgraded = migrate(upgraded)
        upgraded["catalog_schema_version"] = target
    return upgraded
