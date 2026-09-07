"""Gate 5 (grain family and additivity) — T055 (FR-003, FR-050).

Two denials, both about combining numbers in ways that change what they mean.

``GRAIN_FAMILY_MISMATCH``
    Day-grained and cohort-grained metrics in one request. A day-grained value
    belongs to the day the event happened; a cohort-grained value belongs to the
    day the cohort formed. Putting them on one row without a declared weighting
    produces a number with no referent — not an approximate one, one that means
    nothing (A-14).

``AGGREGATION_INVALID_FOR_ADDITIVITY``
    The requested aggregation is not valid for the metric's additivity class.
    Summing seven daily distinct-user counts does not give a weekly figure — it
    counts returning users repeatedly. Summing a point-in-time store rating gives
    a number no one has ever seen. Both look completely ordinary in a chart,
    which is exactly why the contract declares additivity and this gate enforces
    it rather than trusting the caller.

``aggregate`` is what the caller *intends to do* with the result. When they
declare nothing, nothing is checked here: the gate refuses a stated unsafe
intent, and does not guess an unstated one.
"""

from __future__ import annotations

from ...contracts.metric import Additivity, GrainFamily
from ...contracts.reason_codes import ReasonCode
from ..decision import SubjectKind
from .context import GateContext, GateVerdict, deny

__all__ = ["INVALID_AGGREGATIONS", "gate_5_grain"]

#: Aggregations that change the meaning of a metric in each additivity class.
#: Additive metrics are absent because summing them is exactly what they are for.
INVALID_AGGREGATIONS: dict[Additivity, frozenset[str]] = {
    Additivity.NON_ADDITIVE: frozenset({"sum"}),
    Additivity.RATIO: frozenset({"sum", "avg", "average", "mean"}),
    Additivity.POINT_IN_TIME: frozenset({"sum", "avg", "average", "mean"}),
}


def gate_5_grain(context: GateContext) -> GateVerdict | None:
    """Refuse mixed grain families and aggregations the contract forbids."""
    catalog = context.bundle.internal
    request = context.request

    families: dict[GrainFamily, list[str]] = {}
    for metric_id in request.metrics:
        families.setdefault(catalog.metrics[metric_id].grain_family, []).append(metric_id)

    if len(families) > 1:
        mixed = ", ".join(
            f"{family.value}: {sorted(ids)}" for family, ids in sorted(families.items())
        )
        return deny(
            ReasonCode.GRAIN_FAMILY_MISMATCH,
            SubjectKind.REQUEST,
            ",".join(sorted(request.metrics)),
            f"request mixes grain families without a declared weighting ({mixed})",
        )

    if request.aggregate is None:
        return None

    aggregate = request.aggregate.lower()
    for metric_id in request.metrics:
        metric = catalog.metrics[metric_id]
        for version in metric.versions:
            forbidden = INVALID_AGGREGATIONS.get(version.additivity, frozenset())
            if aggregate in forbidden:
                return deny(
                    ReasonCode.AGGREGATION_INVALID_FOR_ADDITIVITY,
                    SubjectKind.METRIC,
                    metric_id,
                    (
                        f"aggregation {aggregate!r} is not valid for {metric_id!r}, "
                        f"which is {version.additivity.value}"
                    ),
                )

    return None
