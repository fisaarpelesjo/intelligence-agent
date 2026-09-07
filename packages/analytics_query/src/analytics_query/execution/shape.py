"""Exact result-shape verification — T076 (FR-030; SC-034).

The executed schema is compared against the dry-run schema as an **ordered tuple
of (column identifier, type, declared unit)**, exact equality. Any difference at
all withholds the result with ``RESULT_SHAPE_MISMATCH``.

There is no tolerance, and that is not strictness for its own sake. A shape
change means the query that ran was not the query that was validated — a column
appeared, vanished, was renamed, retyped or re-united between planning and
execution. Whatever produced that difference also invalidates the reasoning that
allowed the query: the ceilings were checked against a different projection, and
the units the caller will read were declared for different columns.

Order is part of the comparison. Two schemas with the same columns in a
different order produce rows whose positions mean something else, and a
positional read of those rows is silently wrong rather than loudly broken.

**Byte variance is not compared here** (`FR-031`). It is bounded by the enforced
ceiling and reported in provenance; comparing it exactly would withhold correct
results, and comparing it approximately would need a tolerance nobody has a basis
to set.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from ..contracts._base import ContractViolation
from ..contracts.reason_codes import AnalyticsReasonCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .adapter import ResultSchema

__all__ = ["ShapeDrift", "assert_shapes_agree", "describe_drift"]


class ShapeDrift(StrEnum):
    """The five ways a schema can differ. Every one withholds."""

    COLUMN_ADDED = "column_added"
    COLUMN_REMOVED = "column_removed"
    COLUMN_RENAMED = "column_renamed"
    COLUMN_RETYPED = "column_retyped"
    COLUMN_REUNITED = "column_reunited"


def _signature(schema: ResultSchema) -> tuple[tuple[str, str, str | None], ...]:
    """The ordered tuple the comparison is defined over."""
    return tuple((c.identifier, c.type_name, c.unit) for c in schema.columns)


def describe_drift(validated: ResultSchema, executed: ResultSchema) -> ShapeDrift | None:
    """Classify the difference, for the audit record.

    Classification is for reporting only — every class withholds identically, so
    no decision depends on getting the label right.
    """
    before, after = _signature(validated), _signature(executed)
    if before == after:
        return None
    if len(after) > len(before):
        return ShapeDrift.COLUMN_ADDED
    if len(after) < len(before):
        return ShapeDrift.COLUMN_REMOVED

    for (identifier, type_name, unit), (other_id, other_type, other_unit) in zip(
        before, after, strict=True
    ):
        if identifier != other_id:
            return ShapeDrift.COLUMN_RENAMED
        if type_name != other_type:
            return ShapeDrift.COLUMN_RETYPED
        if unit != other_unit:
            return ShapeDrift.COLUMN_REUNITED
    return ShapeDrift.COLUMN_RENAMED  # pragma: no cover - unreachable while equality holds


def assert_shapes_agree(validated: ResultSchema, executed: ResultSchema) -> None:
    """Withhold the result unless the two schemas are identical.

    The message names the drift class but **not** the column identifiers. A
    shape mismatch can occur on a refusal path where the caller was never shown
    the metric's shape, and the failure itself must not become the disclosure.
    """
    drift = describe_drift(validated, executed)
    if drift is None:
        return
    raise ContractViolation(
        AnalyticsReasonCode.RESULT_SHAPE_MISMATCH,
        f"the executed result shape differs from the validated one ({drift.value})",
    )
