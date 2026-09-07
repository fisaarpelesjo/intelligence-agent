"""Slot resolution — T051 (FR-002; SC-001).

Turns a governed request plus `001`'s contracts into a ``QueryStructure``. Every
slot is **resolved from the catalog**, never carried across from the request:

* projection ← the metric version's ``aggregation`` and ``unit``;
* table ← the metric version's ``source_view``;
* group-by ← dimensions `001` declared in ``allowed_dimensions``;
* filter column ← the governed dimension id, checked against the same list.

The request contributes exactly two things: *which* governed ids to look up, and
the filter **values** — and those values never become slots at all. They become
bound parameters, which is the whole point of the separation.

Resolution refuses rather than guessing. A dimension not in ``allowed_dimensions``
is not silently dropped and not passed through; the request does not compile.
Duplicating `001`'s own combination gate is not the intent — this is the narrower
structural check that the tree cannot be built from something the catalog never
vouched for (`FR-015` keeps the governance verdict upstream).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from semantic_catalog.contracts._base import Identifier

from .plan import (
    BoundParameter,
    GroupBySlot,
    PredicateSlot,
    ProjectionSlot,
    QueryStructure,
    TableSlot,
    parameter_name,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from semantic_catalog.contracts.metric import MetricVersion

    from ..contracts.request import AnalyticsQuery

__all__ = ["CompilationDefect", "resolve_structure"]


class CompilationDefect(RuntimeError):  # noqa: N818 - a defect, deliberately not a governed refusal
    """The decision and the compiler disagree about what is representable.

    Compilation runs **after** `001` has allowed the request, so anything
    structurally impossible here means two components disagree — a defect, not a
    caller error. It carries no governed reason code and is never surfaced to a
    caller as a refusal, exactly as a guard failure is not (execution-contract
    §2). Turning it into a refusal would let an internal inconsistency masquerade
    as a governance decision.
    """


#: Governed views live in this dataset and nowhere else. Asserted again by the
#: emitted-text guard, so a resolution bug cannot become a cross-dataset read.
_SEMANTIC_PREFIX = "semantic."


def resolve_structure(
    request: AnalyticsQuery,
    *,
    metric_version: MetricVersion,
    metric_id: Identifier,
    dimension_columns: dict[str, str],
) -> QueryStructure:
    """Build the typed tree for one metric version.

    ``dimension_columns`` maps a governed dimension id to its column in the
    view. It is supplied by the caller of the compiler from catalog content —
    the request never reaches it.
    """
    view = str(metric_version.source_view)
    if not view.startswith(_SEMANTIC_PREFIX):
        raise CompilationDefect(
            f"metric {metric_id!r} resolves to a view outside the semantic dataset"
        )

    allowed = {str(d) for d in metric_version.allowed_dimensions}

    projections = (
        ProjectionSlot(
            metric_id=metric_id,
            aggregation=metric_version.aggregation,
            column=metric_id,
            alias=metric_id,
            unit=str(metric_version.unit),
        ),
    )

    group_by: list[GroupBySlot] = []
    for dimension_id in request.dimensions:
        _require_allowed(dimension_id, allowed, metric_id, "breakdown")
        group_by.append(
            GroupBySlot(dimension_id=dimension_id, column=_column(dimension_id, dimension_columns))
        )

    index = 0
    predicates: list[PredicateSlot] = []
    for governed_filter in request.filters:
        _require_allowed(governed_filter.dimension, allowed, metric_id, "filter")
        bound: list[BoundParameter] = []
        for value in governed_filter.values:
            bound.append(BoundParameter(name=parameter_name(index), value=value))
            index += 1
        predicates.append(
            PredicateSlot(
                dimension_id=governed_filter.dimension,
                column=_column(governed_filter.dimension, dimension_columns),
                operator=governed_filter.operator,
                parameters=tuple(bound),
            )
        )

    # The date range is the request's mandatory temporal bound, not a filter.
    # It binds like any other value — dates are never rendered into text.
    date_start = BoundParameter(name=parameter_name(index), value=request.date_range.start)
    date_end = BoundParameter(name=parameter_name(index + 1), value=request.date_range.end)

    return QueryStructure(
        table=TableSlot(view=view),
        projections=projections,
        group_by=tuple(group_by),
        predicates=tuple(predicates),
        date_column=str(metric_version.time_dimension),
        date_start=date_start,
        date_end=date_end,
    )


def _require_allowed(
    dimension_id: Identifier, allowed: set[str], metric_id: Identifier, role: str
) -> None:
    """Refuse rather than drop.

    Dropping an ungoverned dimension would answer a narrower question than the
    one asked, and would look exactly like a correct answer (`FR-020`).
    """
    if dimension_id not in allowed:
        raise CompilationDefect(f"{role} dimension is not declared for metric {metric_id!r}")


def _column(dimension_id: Identifier, columns: dict[str, str]) -> str:
    """Resolve a governed column, or refuse.

    Falling back to the dimension id as a column name would be a caller-derived
    string reaching the emitted text through the back door.
    """
    column = columns.get(dimension_id)
    if not column:
        raise CompilationDefect(f"no governed column is declared for dimension {dimension_id!r}")
    return column
