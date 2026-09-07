"""Gate 8 (freshness) — T068 (FR-021, FR-022, FR-070).

All five states are reachable, and each maps to one governed code:

``complete``   → passes
``delayed``    → within tolerance: ``SOURCE_LAGGING_WITHIN_TOLERANCE`` (caveat)
               → beyond tolerance: ``SOURCE_BEYOND_TOLERANCE`` (deny)
``partial``    → ``SOURCE_STATE_PARTIAL`` — **denies even within tolerance**
``failed``     → ``SOURCE_STATE_FAILED``
``unknown``    → ``SOURCE_STATE_UNKNOWN``

The rule worth stating twice is ``partial``. FR-070 forbids treating a partial
source as complete on the grounds of punctuality, and the reason is that the two
measure different things: lag says *when* the load ran, completeness says *how
much of it arrived*. A punctual but half-loaded source is the shortest route to
a confidently wrong number, because nothing about the output looks late.

**Only required sources gate the outcome** (T066). A source named in the request
that feeds no requested metric is not evaluated — its staleness is irrelevant to
an answer it does not contribute to. Refusal is per evaluation, never a
quarantine: the same stale source leaves untouched a request that does not need
it.

**Independent of coverage** (FR-071). This gate never asks whether the days
exist; Gate 7 already did, and being on time cannot manufacture a missing day.
"""

from __future__ import annotations

from ...contracts.reason_codes import ReasonCode
from ...freshness.external import CompletenessStatus
from ..decision import SubjectKind
from .context import GateContext, GateVerdict, caveat, deny

__all__ = ["STATUS_TO_REASON", "gate_8_freshness"]

#: Non-passing state to governed code. ``delayed`` is absent because its outcome
#: depends on the authored tolerance, which is a comparison rather than a lookup.
STATUS_TO_REASON = {
    CompletenessStatus.PARTIAL: ReasonCode.SOURCE_STATE_PARTIAL,
    CompletenessStatus.FAILED: ReasonCode.SOURCE_STATE_FAILED,
    CompletenessStatus.UNKNOWN: ReasonCode.SOURCE_STATE_UNKNOWN,
}


def gate_8_freshness(context: GateContext) -> GateVerdict | None:
    """Evaluate every required source against its authored tolerance."""
    if not context.required_source_ids:
        return None

    if context.snapshot is None:
        return deny(
            ReasonCode.SOURCE_STATE_UNKNOWN,
            SubjectKind.REQUEST,
            ",".join(context.required_source_ids),
            "no freshness snapshot was supplied; an unobserved state is unknown, not healthy",
        )

    lagging: GateVerdict | None = None

    for source_id in context.required_source_ids:
        source = context.bundle.internal.sources.get(source_id)
        record = context.snapshot.record_for(source_id)

        if source is None or record is None:
            return deny(
                ReasonCode.SOURCE_STATE_UNKNOWN,
                SubjectKind.SOURCE,
                source_id,
                f"the snapshot reports nothing for required source {source_id!r}",
            )

        code = STATUS_TO_REASON.get(record.status)
        if code is not None:
            ratio = (
                f", completeness {record.completeness_ratio}"
                if record.completeness_ratio is not None
                else ""
            )
            return deny(
                code,
                SubjectKind.SOURCE,
                source_id,
                f"required source {source_id!r} reports {record.status.value}{ratio}",
            )

        within = record.within_tolerance(source, now=context.snapshot.observed_at)
        if within is None:
            return deny(
                ReasonCode.SOURCE_STATE_UNKNOWN,
                SubjectKind.SOURCE,
                source_id,
                f"lag for {source_id!r} cannot be observed; unknown is refused, never assumed fine",
            )
        if not within:
            return deny(
                ReasonCode.SOURCE_BEYOND_TOLERANCE,
                SubjectKind.SOURCE,
                source_id,
                (
                    f"required source {source_id!r} last updated "
                    f"{record.last_successful_update}, beyond its tolerance "
                    f"{source.delay_tolerance}"
                ),
            )

        if record.status is CompletenessStatus.DELAYED and lagging is None:
            lagging = caveat(
                ReasonCode.SOURCE_LAGGING_WITHIN_TOLERANCE,
                SubjectKind.SOURCE,
                source_id,
                (
                    f"required source {source_id!r} is lagging but within tolerance; "
                    f"last update {record.last_successful_update}"
                ),
            )

    return lagging
