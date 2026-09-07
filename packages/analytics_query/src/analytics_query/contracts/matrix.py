"""Operator x dimension-type matrix — T020 (FR-005; SC-001).

All 15 pairings are stated explicitly. Nothing is implied by omission, because a
pairing that is merely unlisted is a pairing nobody decided: the matrix is the
decision record, and reading it should answer "may this operator be used on this
kind of dimension?" without inference.

``temporal_date`` denies every operator. ``date_range`` is mandatory and
authoritative (`FR-007`), and a second temporal constraint on the same period
offers three bad options — intersecting silently changes the period the caller
asked for, overriding makes ``date_range`` advisory, and duplicating admits
contradictory bounds whose empty result is indistinguishable from genuinely
absent data. This feature takes none of them: the `date` dimension remains a
valid breakdown, and is simply not filterable.
"""

from __future__ import annotations

from typing import Final

from .operators import DIMENSION_TYPE_ASSIGNMENTS, DimensionType, GovernedOperator
from .reason_codes import AnalyticsReasonCode

__all__ = [
    "OPERATOR_MATRIX",
    "MatrixVerdict",
    "dimension_type_for",
    "is_permitted",
    "refusal_for",
]

#: Every pairing, explicitly. 5 operators x 3 types = 15 entries, no defaults.
OPERATOR_MATRIX: Final[dict[tuple[GovernedOperator, DimensionType], bool]] = {
    # enumerated_text — closed value list, unordered
    (GovernedOperator.EQ, DimensionType.ENUMERATED_TEXT): True,
    (GovernedOperator.NE, DimensionType.ENUMERATED_TEXT): True,
    (GovernedOperator.IN, DimensionType.ENUMERATED_TEXT): True,
    (GovernedOperator.NOT_IN, DimensionType.ENUMERATED_TEXT): True,
    (GovernedOperator.BETWEEN, DimensionType.ENUMERATED_TEXT): False,
    # open_text — open value space, unordered
    (GovernedOperator.EQ, DimensionType.OPEN_TEXT): True,
    (GovernedOperator.NE, DimensionType.OPEN_TEXT): True,
    (GovernedOperator.IN, DimensionType.OPEN_TEXT): True,
    (GovernedOperator.NOT_IN, DimensionType.OPEN_TEXT): True,
    (GovernedOperator.BETWEEN, DimensionType.OPEN_TEXT): False,
    # temporal_date — not filterable at all; date_range is the sole bound
    (GovernedOperator.EQ, DimensionType.TEMPORAL_DATE): False,
    (GovernedOperator.NE, DimensionType.TEMPORAL_DATE): False,
    (GovernedOperator.IN, DimensionType.TEMPORAL_DATE): False,
    (GovernedOperator.NOT_IN, DimensionType.TEMPORAL_DATE): False,
    (GovernedOperator.BETWEEN, DimensionType.TEMPORAL_DATE): False,
}


class MatrixVerdict:
    """Whether a pairing is permitted, and the code to refuse with when it is not."""

    __slots__ = ("code", "permitted")

    def __init__(self, permitted: bool, code: AnalyticsReasonCode | None) -> None:
        self.permitted = permitted
        self.code = code

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"MatrixVerdict(permitted={self.permitted!r}, code={self.code!r})"


def dimension_type_for(dimension: str) -> DimensionType | None:
    """The declared type of ``dimension``, or ``None`` when it has none.

    ``None`` is the fail-closed answer, not a permissive one: the caller refuses
    with ``DIMENSION_TYPE_UNDECLARED`` rather than assuming a type.
    """
    return DIMENSION_TYPE_ASSIGNMENTS.get(dimension)


def is_permitted(operator: GovernedOperator, dimension_type: DimensionType) -> bool:
    """Whether the pairing is listed as permitted. Absence is never permission."""
    return OPERATOR_MATRIX.get((operator, dimension_type), False)


def refusal_for(operator: GovernedOperator, dimension: str) -> MatrixVerdict:
    """Decide a pairing for a named dimension, fail-closed at every step."""
    declared = dimension_type_for(dimension)
    if declared is None:
        return MatrixVerdict(False, AnalyticsReasonCode.DIMENSION_TYPE_UNDECLARED)
    if declared is DimensionType.TEMPORAL_DATE:
        # Specific beats generic: a caller filtering on `date` learns *why* the
        # dimension is closed to filters, not merely that this operator is wrong.
        return MatrixVerdict(False, AnalyticsReasonCode.DATE_DIMENSION_NOT_FILTERABLE)
    if not is_permitted(operator, declared):
        return MatrixVerdict(False, AnalyticsReasonCode.OPERATOR_NOT_APPLICABLE)
    return MatrixVerdict(True, None)
