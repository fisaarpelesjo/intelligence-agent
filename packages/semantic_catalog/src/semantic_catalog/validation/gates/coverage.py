"""Gate 7 (coverage) — T067 (FR-023, FR-024; ADR 0001 / BD-1).

**Lowest-common-coverage applies to cross-source requests only.** The
architectural baseline declares the flag unqualified, which reads as global;
the constitution and FR-023 both say otherwise, and both outrank it. ADR 0001
records the decision:

* a **single-source** request gets that source's full available coverage, never
  narrowed to match sources it does not use;
* a **cross-source** request gets the intersection across participating sources,
  returned with ``chosen_because`` — an unstated window is a window nobody can
  check (FR-024, SC-005).

Coverage is **observed**, from ``semantic.metric_availability``. Silence is not
coverage: a metric-source pair with no row has no observed coverage and is
refused, because the alternative is answering from data nobody has confirmed
exists.

Each metric is checked against **its own** declared sources, not the cross
product of every requested metric and every required source. A store metric has
no coverage on an app source and never claimed to; demanding it there would
refuse an answerable request over a pair nobody asked about.

This gate is independent of freshness (FR-071). It asks whether the days exist
at all; Gate 8 asks whether what exists is current. Neither can satisfy the
other, and the pair is evaluated separately for exactly that reason.
"""

from __future__ import annotations

from ...contracts.metric import AvailabilityStatus
from ...contracts.reason_codes import ReasonCode
from ...freshness.external import ObservedCoverage
from ..decision import ComparableWindow, SubjectKind
from .context import GateContext, GateVerdict, deny

__all__ = [
    "ComparableWindow",
    "comparable_window",
    "gate_7_coverage",
    "observed_rows",
    "window_for",
]


# ``ComparableWindow`` is imported from the decision contract and re-exported
# here — ADR 0016. It used to be declared in this module, which is why the
# published decision could only transport part of it: the type the gate computed
# and the type the contract carried were different types. They are now one, this
# module still owns the *calculation*, and every existing import of
# ``gates.coverage.ComparableWindow`` keeps working.


def comparable_window(rows: tuple[ObservedCoverage, ...]) -> ComparableWindow | None:
    """Full coverage for one source; the intersection for several (BD-1).

    ``None`` when there is nothing to compute from — no rows means no observed
    coverage, which the gate refuses rather than treating as unbounded.
    """
    if not rows:
        return None

    sources = tuple(sorted({row.source for row in rows}))
    if len(sources) == 1:
        row = rows[0]
        return ComparableWindow(
            start=row.min_date,
            end=row.max_date,
            sources=sources,
            chosen_because=(
                f"cobertura completa de {row.source}; pedidos de fonte única não são "
                "reduzidos para acompanhar outras fontes (FR-023)"
            ),
        )

    start = max(row.min_date for row in rows)
    end = min(row.max_date for row in rows)
    return ComparableWindow(
        start=start,
        end=end,
        sources=sources,
        chosen_because=(
            f"janela comparável entre {', '.join(sources)}: interseção das coberturas "
            f"observadas, de {start} a {end} (FR-024)"
        ),
    )


def gate_7_coverage(context: GateContext) -> GateVerdict | None:
    """Refuse a period the observed coverage does not contain."""
    if not context.required_source_ids:
        # Nothing required means nothing to cover. Later gates still apply.
        return None

    if context.snapshot is None:
        return deny(
            ReasonCode.SOURCE_STATE_UNKNOWN,
            SubjectKind.REQUEST,
            ",".join(context.required_source_ids),
            "no coverage snapshot was supplied; unobserved coverage is unknown, not unbounded",
        )

    period = context.request.date_range
    catalog = context.bundle.internal

    for metric_id in sorted(context.request.metrics):
        metric = catalog.metrics.get(metric_id)
        if metric is None:
            continue
        # Only the sources THIS metric is answered from. The cross product of
        # every requested metric against every required source would demand
        # coverage for pairs the catalog never claimed exist — a store metric
        # has none on an app source, and requiring it there would refuse a
        # perfectly answerable request on a pair nobody asked about.
        answered_from = {
            entry.source
            for entry in metric.source_availability
            if entry.status is AvailabilityStatus.AVAILABLE
        }
        for source_id in context.required_source_ids:
            if source_id not in answered_from:
                continue
            row = context.snapshot.coverage_for(metric_id, source_id)
            if row is None:
                return deny(
                    ReasonCode.RANGE_OUTSIDE_COVERAGE,
                    SubjectKind.METRIC,
                    metric_id,
                    (
                        f"no observed coverage for {metric_id!r} on {source_id!r}; "
                        "silence in the availability table is not coverage"
                    ),
                )
            if period.end < row.min_date or period.start > row.max_date:
                return deny(
                    ReasonCode.RANGE_OUTSIDE_COVERAGE,
                    SubjectKind.METRIC,
                    metric_id,
                    (
                        f"{metric_id!r} on {source_id!r} covers {row.min_date}..{row.max_date}, "
                        f"which does not overlap {period.start}..{period.end}"
                    ),
                )
            if row.max_date < period.end:
                return deny(
                    ReasonCode.COVERAGE_ENDS_BEFORE_PERIOD,
                    SubjectKind.SOURCE,
                    source_id,
                    (
                        f"coverage for {metric_id!r} on {source_id!r} ends {row.max_date}, "
                        f"before the requested period ends {period.end}"
                    ),
                )
            if row.min_date > period.start:
                return deny(
                    ReasonCode.RANGE_OUTSIDE_COVERAGE,
                    SubjectKind.SOURCE,
                    source_id,
                    (
                        f"coverage for {metric_id!r} on {source_id!r} starts {row.min_date}, "
                        f"after the requested period starts {period.start}"
                    ),
                )

    return None


def observed_rows(context: GateContext) -> tuple[ObservedCoverage, ...]:
    """The coverage rows gate 7 actually walked, in a stable order.

    Extracted from the gate rather than reimplemented beside it, so the rows the
    window is computed from are **the same rows the gate checked**. A second
    traversal with a slightly different pairing rule would produce a window
    describing coverage nobody validated — and the difference would be invisible,
    because both would look like plausible windows.

    Each metric is paired with **its own** declared sources, exactly as the gate
    does: a store metric has no coverage on an app source and never claimed to.
    """
    if context.snapshot is None:
        return ()

    catalog = context.bundle.internal
    rows: list[ObservedCoverage] = []
    for metric_id in sorted(context.request.metrics):
        metric = catalog.metrics.get(metric_id)
        if metric is None:
            continue
        answered_from = {
            entry.source
            for entry in metric.source_availability
            if entry.status is AvailabilityStatus.AVAILABLE
        }
        for source_id in context.required_source_ids:
            if source_id not in answered_from:
                continue
            row = context.snapshot.coverage_for(metric_id, source_id)
            if row is not None:
                rows.append(row)
    return tuple(rows)


def window_for(context: GateContext) -> ComparableWindow | None:
    """The comparable window for this request, computed by this gate — ADR 0016.

    **This gate is the authoritative calculator and this is its published
    output.** ``comparable_window`` has always computed the value; what was
    missing was a path from here to the decision, so `FR-024`'s "state which
    window was selected and why" and `SC-005`'s "zero cross-source comparisons
    return an unstated window" were requirements nothing satisfied.

    Returns ``None`` when there is nothing to compute from — no snapshot, or no
    observed coverage. ``None`` is not an empty window: an empty one would assert
    a comparison over no days, and a request whose coverage nobody observed is
    one gate 7 has already refused.

    Nothing here decides eligibility. The gate's own verdict is unchanged and is
    reached by the same code it always was; this function only reports what the
    gate's calculation produced.
    """
    return comparable_window(observed_rows(context))
