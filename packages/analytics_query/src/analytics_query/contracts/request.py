"""The governed request — T021 (FR-001, FR-007, FR-009; SC-001).

`AnalyticsQuery` carries governed identifiers and nothing else. It has no field
for query text, for a freshness or coverage observation, for a data revision, or
for a fixture selector — and `extra="forbid"` is what makes those absences
structural rather than a validation rule someone must remember to write. A caller
sending `comparison`, `order_by` or `limit` is refused as sending an unknown
field (`BD-1`, ADR 0008), never silently ignored: ignoring it would leave the
caller believing a comparison was applied.

Structural filter rules live here because they need no catalog knowledge — nulls,
empty sets, duplicates, arity and range order. Type-dependent rules (matrix
applicability, value membership) are `filters.py`, and the date-dimension refusal
is `date_filter.py`. Splitting them keeps each rule testable on its own and
avoids an import cycle through the catalog.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import cast

from pydantic import Field, field_validator, model_validator

from ._base import ContractViolation, QueryModel
from .operators import OPERATOR_ARITY, Arity, GovernedOperator
from .reason_codes import AnalyticsReasonCode

__all__ = ["AnalyticsQuery", "DateRange", "GovernedFilter"]

_MAX_VALUE_LENGTH = 512


class DateRange(QueryModel):
    """The mandatory, authoritative temporal bound (`FR-007`).

    There is no default and no implicit "recent" window. A reversed range is
    refused, never swapped: swapping would answer a question the caller did not
    ask, and they would have no way to tell.
    """

    start: date
    end: date

    @model_validator(mode="after")
    def _end_is_not_before_start(self) -> DateRange:
        if self.end < self.start:
            raise ContractViolation(
                AnalyticsReasonCode.DATE_RANGE_INVALID,
                "the end date precedes the start date; the range is never reordered",
            )
        return self

    @property
    def days(self) -> int:
        """Inclusive length in days, for the governed maximum-range check."""
        return (self.end - self.start).days + 1


class GovernedFilter(QueryModel):
    """One governed predicate: a dimension, an allowlisted operator, and values.

    Values are strings here and become **bound query parameters** downstream.
    They are never rendered into query text, which is why a value's content
    cannot become syntax however hostile it looks.
    """

    dimension: str = Field(min_length=1)
    operator: GovernedOperator
    values: tuple[str, ...]

    @field_validator("dimension", mode="after")
    @classmethod
    def _dimension_is_a_governed_identifier(cls, value: str) -> str:
        """Shape-checked at parse, exactly like the request's other identifiers.

        A filter dimension reaches the emitted text as a column name, so it is an
        identifier and is held to the identifier rule — not merely to
        "non-empty". Downstream layers would refuse a predicate-shaped dimension
        too (the matrix has no entry for it, and slot resolution finds no
        governed column), but a caller must not have to reach a catalog lookup to
        be told that ``country; DROP TABLE x`` is not a dimension.
        """
        if not value.replace("_", "").isalnum() or not value.islower():
            raise ContractViolation(
                AnalyticsReasonCode.REQUEST_MALFORMED,
                f"{value!r} is not a governed identifier",
            )
        return value

    @field_validator("values", mode="before")
    @classmethod
    def _no_null_values(cls, raw: object) -> object:
        """Nulls are refused before typing, so the caller learns the real reason.

        Left to Pydantic's type check, a ``None`` element would surface as a
        generic type error. Nullity is not expressible as a filter in this
        feature at all — there is no ``is_null`` operator — so it earns its own
        code (`analytics-query-contract.md` §4.5).
        """
        if raw is None:
            raise ContractViolation(
                AnalyticsReasonCode.FILTER_VALUE_NULL,
                "a filter value may never be null",
            )
        if isinstance(raw, list | tuple):
            elements: tuple[object, ...] = tuple(cast("Sequence[object]", raw))
            if any(item is None for item in elements):
                raise ContractViolation(
                    AnalyticsReasonCode.FILTER_VALUE_NULL,
                    "a filter value may never be null, in any element",
                )
            return elements
        return raw

    @field_validator("values", mode="after")
    @classmethod
    def _values_are_well_formed(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ContractViolation(
                AnalyticsReasonCode.FILTER_VALUE_SET_EMPTY,
                "an empty value set is neither 'no filter' nor 'match nothing'",
            )
        for value in values:
            if not value or len(value) > _MAX_VALUE_LENGTH:
                raise ContractViolation(
                    AnalyticsReasonCode.FILTER_VALUE_NOT_GOVERNED,
                    "a filter value must be a non-empty string within the governed length",
                )
        return values

    @model_validator(mode="after")
    def _arity_matches_the_operator(self) -> GovernedFilter:
        arity = OPERATOR_ARITY[self.operator]
        count = len(self.values)
        if arity is Arity.ONE_OR_MORE and len(set(self.values)) != count:
            # Set semantics: a repeated member says nothing new, and silently
            # de-duplicating would answer a slightly different question than the
            # one asked. `between` is excluded deliberately -- its two values are
            # positional bounds, and equal bounds are a legitimate single-point
            # range (contract §4.4).
            raise ContractViolation(
                AnalyticsReasonCode.REQUEST_MALFORMED,
                "duplicate filter values are refused, never silently de-duplicated",
            )
        if arity is Arity.EXACTLY_ONE and count != 1:
            raise ContractViolation(
                AnalyticsReasonCode.REQUEST_MALFORMED,
                f"operator {self.operator.value} takes exactly one value, got {count}",
            )
        if arity is Arity.EXACTLY_TWO and count != 2:
            raise ContractViolation(
                AnalyticsReasonCode.REQUEST_MALFORMED,
                f"operator {self.operator.value} takes exactly two bounds, got {count}",
            )
        if arity is Arity.EXACTLY_TWO and self.values[1] < self.values[0]:
            raise ContractViolation(
                AnalyticsReasonCode.FILTER_RANGE_INVALID,
                "the upper bound precedes the lower bound; bounds are never swapped",
            )
        return self


class AnalyticsQuery(QueryModel):
    """A governed analytical request. Carries no query text and no observation.

    Deliberately absent — and therefore refused as unknown fields (`BD-1`):
    ``comparison``, ``order_by``, ``limit``. Also absent: anything accepting SQL,
    a freshness or coverage observation, a data revision, or a fixture selector.
    """

    metrics: tuple[str, ...] = Field(min_length=1)
    dimensions: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    filters: tuple[GovernedFilter, ...] = ()
    date_range: DateRange
    as_of: date | None = None

    @field_validator("metrics", "dimensions", "sources", mode="after")
    @classmethod
    def _identifiers_are_unique_and_well_formed(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Shape is checked before any catalog lookup.

        A predicate-shaped identifier dies here rather than reaching compilation,
        which keeps the compiler's inputs boring by construction.
        """
        for value in values:
            if not value or not value.replace("_", "").isalnum() or not value.islower():
                raise ContractViolation(
                    AnalyticsReasonCode.REQUEST_MALFORMED,
                    f"{value!r} is not a governed identifier",
                )
        if len(set(values)) != len(values):
            raise ContractViolation(
                AnalyticsReasonCode.REQUEST_MALFORMED,
                "duplicate identifiers are refused",
            )
        return values
