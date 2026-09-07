"""Typed query structure — T050 (FR-002; SC-001).

The whole SQL-safety design rests on this file. ``QueryStructure`` is a typed
tree whose leaves are **governed identifiers resolved from the catalog** and
**parameter placeholders** — and nothing else. There is no field capable of
holding a string that originated with the caller, so "no unrestricted SQL" is a
property of the type rather than a rule someone has to remember.

The distinction that makes it work: an ``Identifier`` here is never accepted from
a request. It is produced by resolution against `001`'s contracts (`slots.py`),
so by the time a value reaches this tree the catalog has already vouched for it.
Caller values take the other path entirely — they become ``BoundParameter``
placeholders, and the placeholder *name* is generated here, never supplied.

A date filter cannot reach compilation at all: `T023` refuses one at the request
boundary, so the structure has no date-predicate shape to represent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from ..contracts.operators import GovernedOperator

if TYPE_CHECKING:  # pragma: no cover - typing only
    from semantic_catalog.contracts.metric import Aggregation

__all__ = [
    "BoundParameter",
    "GroupBySlot",
    "PredicateSlot",
    "ProjectionSlot",
    "QueryStructure",
    "TableSlot",
    "parameter_name",
]


def parameter_name(index: int) -> str:
    """Generate a placeholder name.

    Generated positionally rather than derived from the dimension or the value.
    A name built from caller input would be one more channel through which
    caller-controlled characters reach the emitted text.
    """
    return f"p{index}"


@dataclass(frozen=True, slots=True)
class BoundParameter:
    """One caller value, held apart from the query text.

    This is the only place a caller value exists in the compiled form, and it is
    deliberately not a field of any slot that contributes text.
    """

    name: str
    value: str | int | float | bool | date


@dataclass(frozen=True, slots=True)
class ProjectionSlot:
    """A metric's aggregation over its governed column.

    Both halves come from the metric version's contract: `001` states the
    ``aggregation`` and the column; this feature chooses neither.
    """

    metric_id: str
    aggregation: Aggregation
    column: str
    alias: str
    unit: str


@dataclass(frozen=True, slots=True)
class TableSlot:
    """The metric version's ``source_view``, always ``semantic.``-prefixed.

    Held as a resolved value, never as a caller-supplied table name — the
    emitted-text guard additionally asserts the prefix, so a resolution bug
    cannot become a cross-dataset read.
    """

    view: str


@dataclass(frozen=True, slots=True)
class GroupBySlot:
    """A dimension validated for the metric-source pair by `001`."""

    dimension_id: str
    column: str


@dataclass(frozen=True, slots=True)
class PredicateSlot:
    """A governed filter: governed column, enum operator, bound parameters.

    Note what is absent — there is no ``expression``, ``raw`` or ``sql`` field,
    and ``parameters`` holds placeholder *references*, so a predicate cannot
    carry a value into the text even by mistake.
    """

    dimension_id: str
    column: str
    operator: GovernedOperator
    parameters: tuple[BoundParameter, ...]


@dataclass(frozen=True, slots=True)
class QueryStructure:
    """The complete compiled shape of one governed request.

    ``date_column`` and the two date bounds are separate from ``predicates``
    because the date range is not a filter: it is the request's mandatory
    temporal bound, and `temporal_date` is not a filterable dimension type
    (contract §4.3.1).
    """

    table: TableSlot
    projections: tuple[ProjectionSlot, ...]
    group_by: tuple[GroupBySlot, ...] = ()
    predicates: tuple[PredicateSlot, ...] = ()
    date_column: str = "event_date"
    date_start: BoundParameter | None = None
    date_end: BoundParameter | None = None

    def parameters(self) -> dict[str, str | int | float | bool | date]:
        """Every bound value, keyed by placeholder name.

        The single source for what ``render`` must hand the adapter — and what
        the emitted-text guard asserts is *absent* from the text.
        """
        collected: dict[str, str | int | float | bool | date] = {}
        for predicate in self.predicates:
            for parameter in predicate.parameters:
                collected[parameter.name] = parameter.value
        for bound in (self.date_start, self.date_end):
            if bound is not None:
                collected[bound.name] = bound.value
        return collected
