"""The date-dimension filter refusal — T023 (FR-005, FR-007; SC-001).

``date_range`` is mandatory and authoritative. A filter on the `date` dimension
would be a second temporal constraint on the same period, and every way of
reconciling the two is worse than refusing:

* **intersect** — silently changes the period the caller asked for;
* **override** — makes ``date_range`` advisory, contradicting `FR-007`;
* **duplicate** — admits contradictory bounds whose empty result is
  indistinguishable from genuinely absent data.

So no filter may target `date` at all, and the refusal carries its own code so a
caller learns *why* rather than receiving a generic operator error.

**`date` remains a valid breakdown dimension.** Only filtering on it is closed;
requesting it in ``dimensions`` is unaffected. The distinction matters: `date` is
observable in a result, it is simply not a place to set the period.

The compiler depends on this module (`T050` → `T023`), so a date filter can never
reach compilation — the ordering is a dependency edge, not a convention.
"""

from __future__ import annotations

from collections.abc import Sequence

from .matrix import dimension_type_for
from .operators import DimensionType
from .reason_codes import AnalyticsReasonCode
from .request import AnalyticsQuery, GovernedFilter

__all__ = [
    "DATE_DIMENSION",
    "DateFilterRefusal",
    "assert_no_date_filters",
    "is_date_dimension",
    "reject_date_filters",
]

#: The `001` dimension that names the period. Identified by its declared type
#: rather than by its name, so a future temporal dimension is closed too.
DATE_DIMENSION = "date"


class DateFilterRefusal:
    """A refusal naming the offending dimension, or a clean pass."""

    __slots__ = ("code", "detail", "dimension", "refused")

    def __init__(
        self,
        refused: bool,
        dimension: str | None = None,
        code: AnalyticsReasonCode | None = None,
        detail: str = "",
    ) -> None:
        self.refused = refused
        self.dimension = dimension
        self.code = code
        self.detail = detail

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"DateFilterRefusal(refused={self.refused!r}, dimension={self.dimension!r})"


def is_date_dimension(dimension: str) -> bool:
    """Whether ``dimension`` carries the temporal type, by declaration not by name."""
    return dimension_type_for(dimension) is DimensionType.TEMPORAL_DATE


def reject_date_filters(filters: Sequence[GovernedFilter]) -> DateFilterRefusal:
    """Refuse the first filter targeting a temporal dimension."""
    for governed_filter in filters:
        if is_date_dimension(governed_filter.dimension):
            return DateFilterRefusal(
                True,
                governed_filter.dimension,
                AnalyticsReasonCode.DATE_DIMENSION_NOT_FILTERABLE,
                (
                    f"{governed_filter.dimension} is not filterable; the period is set "
                    "solely by date_range"
                ),
            )
    return DateFilterRefusal(False)


def assert_no_date_filters(query: AnalyticsQuery) -> DateFilterRefusal:
    """Whole-request form. ``dimensions`` is untouched — only filters are closed."""
    return reject_date_filters(query.filters)
