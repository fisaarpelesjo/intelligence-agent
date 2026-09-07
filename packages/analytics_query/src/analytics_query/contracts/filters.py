"""Type-dependent filter rules — T022 (FR-006; SC-001).

`request.py` enforces what needs no catalog knowledge: nulls, empty sets,
duplicates, arity and range order. This module enforces what does — whether the
operator is permitted for the dimension's declared type, and how a value is
validated once that type is known.

**A refinement of `FR-006`, not a narrowing.** `FR-006` requires every filter
value to be validated against its dimension's governed values. Three of `001`'s
six dimensions declare ``permitted_values: open`` and so have no value set to
compare against. Both paths are still validation, and neither is skipped:

* ``enumerated_text`` — **membership**: the value must appear in the closed list,
  else ``FILTER_VALUE_NOT_GOVERNED``;
* ``open_text`` — **type and shape**: a non-null, non-empty string within the
  governed length. Membership is not asserted because there is no set to assert
  it against, and pretending otherwise would be a check that always passes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .matrix import dimension_type_for, refusal_for
from .operators import DimensionType
from .reason_codes import AnalyticsReasonCode
from .request import GovernedFilter

__all__ = ["FilterVerdict", "validate_filter", "validate_filters"]

_MAX_VALUE_LENGTH = 512


class FilterVerdict:
    """The outcome of validating one filter against catalog knowledge."""

    __slots__ = ("code", "detail", "permitted")

    def __init__(
        self, permitted: bool, code: AnalyticsReasonCode | None = None, detail: str = ""
    ) -> None:
        self.permitted = permitted
        self.code = code
        self.detail = detail

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"FilterVerdict(permitted={self.permitted!r}, code={self.code!r})"


def validate_filter(
    governed_filter: GovernedFilter,
    permitted_values: Mapping[str, Sequence[str]] | None = None,
) -> FilterVerdict:
    """Validate one filter against the matrix and the dimension's governed values.

    ``permitted_values`` maps a dimension to its closed value list, for those that
    enumerate. A dimension absent from it is treated as open, which is the
    catalog's own meaning of ``permitted_values: open`` — not a fallback.
    """
    verdict = refusal_for(governed_filter.operator, governed_filter.dimension)
    if not verdict.permitted:
        assert verdict.code is not None
        return FilterVerdict(
            False,
            verdict.code,
            f"{governed_filter.operator.value} is not permitted on {governed_filter.dimension}",
        )

    declared = dimension_type_for(governed_filter.dimension)
    if declared is DimensionType.ENUMERATED_TEXT:
        allowed = permitted_values.get(governed_filter.dimension) if permitted_values else None
        if allowed is None:
            # The type says the dimension enumerates, but no list was supplied.
            # Fail closed: guessing that anything goes would turn a membership
            # check into a check that always passes.
            return FilterVerdict(
                False,
                AnalyticsReasonCode.DIMENSION_TYPE_UNDECLARED,
                f"{governed_filter.dimension} enumerates its values but none were supplied",
            )
        outside = [value for value in governed_filter.values if value not in set(allowed)]
        if outside:
            return FilterVerdict(
                False,
                AnalyticsReasonCode.FILTER_VALUE_NOT_GOVERNED,
                f"{governed_filter.dimension} does not govern the supplied value(s)",
            )
        return FilterVerdict(True)

    if declared is DimensionType.OPEN_TEXT:
        for value in governed_filter.values:
            if not value or len(value) > _MAX_VALUE_LENGTH:
                return FilterVerdict(
                    False,
                    AnalyticsReasonCode.FILTER_VALUE_NOT_GOVERNED,
                    f"{governed_filter.dimension} requires a non-empty governed string",
                )
        return FilterVerdict(True)

    # temporal_date is unreachable here: refusal_for() already denied it above.
    return FilterVerdict(
        False,
        AnalyticsReasonCode.DIMENSION_TYPE_UNDECLARED,
        f"{governed_filter.dimension} has no usable declared type",
    )


def validate_filters(
    filters: Sequence[GovernedFilter],
    permitted_values: Mapping[str, Sequence[str]] | None = None,
) -> FilterVerdict:
    """Validate every filter, returning the **first** refusal.

    First-refusal-wins mirrors `001`'s gate pipeline: the caller gets one code to
    act on rather than a list to triage, and evaluation stops before a later rule
    can disclose anything about a dimension the first refusal already closed.
    """
    for governed_filter in filters:
        verdict = validate_filter(governed_filter, permitted_values)
        if not verdict.permitted:
            return verdict
    return FilterVerdict(True)
