"""Gate 4 (combination) — T054 (FR-008, FR-009, FR-010).

Three distinct denials, each naming its offender. They are separate codes because
they send the reader to three different places:

``METRIC_NOT_AVAILABLE_FOR_SOURCE``
    The metric is available on **none** of the requested sources. Crash rate has
    no meaning for the website; downloads are a store event, not a telemetry one.

    Availability is checked against the requested set, not source by source, and
    that distinction is FR-022. Asking for store downloads while also naming an
    app source is not a combination error — the app source simply feeds nothing
    the request asked for, so it is *not required* (T066) and its state is never
    evaluated. Denying there would refuse a request whose answer would have been
    entirely correct.

``DIMENSION_NOT_APPLICABLE_TO_SOURCE``
    The source does not record that attribute at all — application version for
    the website. Absence from ``source_applicability`` means *not applicable*,
    not *not yet filled in*.

``DIMENSION_NOT_ALLOWED_FOR_METRIC``
    The source records it, but this metric's contract does not permit slicing by
    it. ``allowed_dimensions`` is deny-by-default: anything absent is forbidden.

Order within the gate matters too. Source applicability is checked before metric
permission, so "the website has no app_version" is reported rather than the
narrower and less useful "this metric does not allow app_version".
"""

from __future__ import annotations

from ...contracts.metric import AvailabilityStatus
from ...contracts.reason_codes import ReasonCode
from ..decision import SubjectKind
from .context import GateContext, GateVerdict, deny

__all__ = ["gate_4_combination"]


def gate_4_combination(context: GateContext) -> GateVerdict | None:
    """Check every metric x source and dimension x source x metric triple."""
    catalog = context.bundle.internal
    request = context.request

    for metric_id in request.metrics:
        metric = catalog.metrics[metric_id]
        available = {
            entry.source
            for entry in metric.source_availability
            if entry.status is AvailabilityStatus.AVAILABLE
        }
        if request.sources and not (available & set(request.sources)):
            return deny(
                ReasonCode.METRIC_NOT_AVAILABLE_FOR_SOURCE,
                SubjectKind.METRIC,
                metric_id,
                (
                    f"metric {metric_id!r} is not available for any requested source "
                    f"({', '.join(sorted(request.sources))})"
                ),
            )

    for dimension_id in request.dimensions:
        dimension = catalog.dimensions[dimension_id]
        applies_to = {entry.source for entry in dimension.source_applicability}
        for source_id in request.sources:
            if source_id not in applies_to:
                return deny(
                    ReasonCode.DIMENSION_NOT_APPLICABLE_TO_SOURCE,
                    SubjectKind.DIMENSION,
                    dimension_id,
                    f"dimension {dimension_id!r} does not apply to source {source_id!r}",
                )

    for metric_id in request.metrics:
        metric = catalog.metrics[metric_id]
        allowed: set[str] = set()
        for version in metric.versions:
            allowed.update(version.allowed_dimensions)
        for dimension_id in request.dimensions:
            if dimension_id not in allowed:
                return deny(
                    ReasonCode.DIMENSION_NOT_ALLOWED_FOR_METRIC,
                    SubjectKind.DIMENSION,
                    dimension_id,
                    f"metric {metric_id!r} does not permit the dimension {dimension_id!r}",
                )

    return None
