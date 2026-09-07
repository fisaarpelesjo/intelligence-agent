"""Gate 1 (existence) and Gate 2 (lifecycle) — T052 (FR-018, FR-040).

**Deny-by-default on unrecognised input.** Anything the catalog does not know is
refused, never passed through on the assumption that a later gate will catch it.

The distinction this gate exists to preserve:

``METRIC_NOT_GOVERNED``
    The concept does not exist here. The reader should go build their own
    number, or ask for it to be governed.

``METRIC_PENDING``
    It exists and is not publishable. The reader should go to the owner, and the
    denial names the unset fields so they know what they are waiting for.

Collapsing the two into "no" would send half the users to the wrong place. They
are separate codes for that reason, not for tidiness (R-8).

Gate 1 also covers dimensions and sources: a request naming a dimension or source
outside the catalog is denied here, before anything reasons about combinations.
"""

from __future__ import annotations

from ...contracts.metric import Lifecycle
from ...contracts.reason_codes import ReasonCode
from ...resolution.deprecation import DeprecationVerdict, deprecation_verdict
from ..decision import SubjectKind
from .context import GateContext, GateVerdict, caveat, deny

__all__ = ["dated_deprecation", "gate_1_existence", "gate_2_lifecycle"]


def gate_1_existence(context: GateContext) -> GateVerdict | None:
    """Every named metric, dimension and source must be governed."""
    catalog = context.bundle.internal
    request = context.request

    for metric_id in request.metrics:
        if metric_id not in catalog.metrics:
            return deny(
                ReasonCode.METRIC_NOT_GOVERNED,
                SubjectKind.METRIC,
                metric_id,
                f"metric {metric_id!r} is not governed by this catalog",
            )
    for dimension_id in request.dimensions:
        if dimension_id not in catalog.dimensions:
            return deny(
                ReasonCode.DIMENSION_NOT_GOVERNED,
                SubjectKind.DIMENSION,
                dimension_id,
                f"dimension {dimension_id!r} is not governed by this catalog",
            )
    for source_id in request.sources:
        if source_id not in catalog.sources:
            return deny(
                ReasonCode.SOURCE_NOT_GOVERNED,
                SubjectKind.SOURCE,
                source_id,
                f"source {source_id!r} is outside the declared sources",
            )
    return None


def gate_2_lifecycle(context: GateContext) -> GateVerdict | None:
    """Only a published metric is requestable for analysis (FR-002, FR-018).

    The denial names the unset fields — **names, never draft values**. Naming the
    gap is what makes it actionable; showing the draft would defeat the
    withholding that made the metric pending in the first place.

    Deprecation **annotates or refuses, depending on the dates** (T089). The
    non-temporal half was always here: a deprecation block exists, so the
    decision says so under ``DEPRECATED_METRIC``, which is ALLOW_WITH_CAVEAT.
    The dated half is now here too, because it is still a lifecycle question and
    the request already carries the period it needs:

    * period entirely before ``deprecated_from`` → the caveat, as before;
    * period on or after it, with no authored continuation version →
      ``METRIC_DEPRECATED_FOR_PERIOD``, a denial (FR-062);
    * period crossing it → ``SPANS_DEPRECATION_BOUNDARY``, a caveat carrying the
      segmentation (FR-063);
    * a comparison that would need the deprecated side →
      ``COMPARISON_REQUIRES_DEPRECATED_PERIOD``, a denial rather than a
      comparison silently shortened to the half that still exists.

    **No replacement is named here.** Gate 3 has not run, so this gate cannot
    know whether the requester is authorised for the replacement metric, and
    naming one they may not see would leak a relationship between two metrics.
    Disclosure happens once the decision is assembled (FR-064).
    """
    for metric_id in context.request.metrics:
        state = context.bundle.lifecycles.get(metric_id)
        if state is None:
            return deny(
                ReasonCode.METRIC_NOT_GOVERNED,
                SubjectKind.METRIC,
                metric_id,
                f"metric {metric_id!r} has no derived lifecycle",
            )
        if state.lifecycle is Lifecycle.PENDING:
            missing = ", ".join(state.missing_fields) or "; ".join(
                reason.value for reason in state.reasons
            )
            return deny(
                ReasonCode.METRIC_PENDING,
                SubjectKind.METRIC,
                metric_id,
                f"metric {metric_id!r} is pending: {missing}",
            )

    # Dated deprecation denials outrank every caveat, and are checked across all
    # metrics before any caveat is raised: a request naming one deprecated-past
    # metric and one refused-for-the-period metric is a refusal.
    verdicts = dated_deprecation(context)
    for verdict in verdicts:
        if verdict.is_denial:
            return deny(
                verdict.reason_code,
                SubjectKind.METRIC,
                verdict.metric_id,
                f"metric {verdict.metric_id!r} was deprecated from {verdict.deprecated_from} "
                "and no governed continuation version covers the requested period",
            )

    # Caveats only after every metric has cleared the denials above, so a
    # deprecated-and-pending metric reports the refusal rather than the caveat.
    if verdicts:
        first = verdicts[0]
        return caveat(
            first.reason_code,
            SubjectKind.METRIC,
            first.metric_id,
            f"metric {first.metric_id!r} is deprecated from {first.deprecated_from}",
        )
    return None


def dated_deprecation(context: GateContext) -> tuple[DeprecationVerdict, ...]:
    """Deprecation verdicts for every requested metric that has a boundary.

    Ordered by metric id so a request naming two deprecated metrics produces the
    same decision whichever order the caller listed them in.
    """
    comparison = context.request.comparison
    verdicts: list[DeprecationVerdict] = []
    for metric_id in sorted(set(context.request.metrics)):
        metric = context.bundle.internal.metrics.get(metric_id)
        if metric is None:
            continue
        verdict = deprecation_verdict(
            metric,
            context.request.date_range.start,
            context.request.date_range.end,
            comparison_start=comparison.baseline_range.start if comparison else None,
            comparison_end=comparison.baseline_range.end if comparison else None,
        )
        if verdict is not None:
            verdicts.append(verdict)
    return tuple(verdicts)
