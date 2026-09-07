"""Audit-event emission — T075 (FR-043; decision-contract §5).

**One event per decision, for every outcome.** ALLOW, DENY and ALLOW_WITH_CAVEAT
alike — an audit that records only refusals cannot answer "what was this
principal permitted to see", and one that records only allows cannot answer "who
was refused", which is the central question of authorisation auditing.

This module **consumes** the T020 contract and does not redefine it. The event's
shape, its required actor and its forbidden-content denylist all live there; this
is the integration that wraps the pipeline and populates one.

**A suppressed emission raises.** If the sink rejects an event, the caller finds
out. Swallowing the failure would leave a decision that happened and an audit
that says it did not, which is worse than no audit at all: it is an audit that
lies by omission and looks complete.

**Aggregated governed evidence only.** The event carries identifiers — metric,
dimension, source, revision, release, policy — plus a pseudonymous actor. No
metric value, no fact row, no raw external claim, no prompt text, no credential.
Not because a filter strips them, but because nothing puts them in, and the
contract's validators refuse them if anything ever tries.

Ownership stops at emission. Transport, storage, retention, indexing and access
control over the archive belong to the observability feature (D-13 / EXT-B).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime

from ..contracts.access_tag import PrincipalType
from ..contracts.audit_event import (
    AuditDateRange,
    CatalogDecisionAuditEvent,
    RequestedOperation,
)
from ..freshness.external import FreshnessSnapshot
from ..freshness.required import required_sources
from ..loader.bundle import Bundle
from ..validation.decision import CatalogDecision, CatalogValidationRequest
from ..validation.pipeline import evaluate, resolved_version_ids
from .identity import FinalisedDecision, finalise
from .revision import RevisionSnapshot, resolve_revisions

__all__ = [
    "AuditEmissionError",
    "AuditSink",
    "CollectingSink",
    "EvaluatedDecision",
    "emit_for_decision",
    "evaluate_and_emit",
]


class AuditEmissionError(RuntimeError):
    """A sink refused or dropped an event. Never swallowed."""


#: A sink is any callable that accepts one event. Transport is not this
#: feature's concern; refusing to define it is the boundary (D-13).
AuditSink = Callable[[CatalogDecisionAuditEvent], None]


@dataclass(slots=True)
class CollectingSink:
    """An in-memory sink for tests and local stewardship. Not an archive."""

    # The factory is parameterised so the element type survives strict checking;
    # a bare ``list`` leaves it unknown.
    events: list[CatalogDecisionAuditEvent] = field(default_factory=list[CatalogDecisionAuditEvent])

    def __call__(self, event: CatalogDecisionAuditEvent) -> None:
        self.events.append(event)

    @property
    def count(self) -> int:
        return len(self.events)


@dataclass(frozen=True, slots=True)
class EvaluatedDecision:
    """A decision, its finality, and the event that recorded it."""

    decision: CatalogDecision
    finalised: FinalisedDecision | None
    event: CatalogDecisionAuditEvent


def _metric_version_ids(bundle: Bundle, request: CatalogValidationRequest) -> tuple[str, ...]:
    """The same as-of resolution the pipeline used, not a second opinion.

    Delegated rather than recomputed. ``decision_id`` folds this set in, so an
    event or a finalisation that resolved versions differently from the decision
    it describes would produce an identity nothing else can reproduce.
    """
    return resolved_version_ids(bundle, request)


def emit_for_decision(
    decision: CatalogDecision,
    request: CatalogValidationRequest,
    bundle: Bundle,
    sink: AuditSink,
    *,
    principal_id: str,
    principal_type: PrincipalType,
    correlation_id: str,
    authorization_scope: str | None = None,
    operation: RequestedOperation = RequestedOperation.VALIDATE,
    occurred_at: datetime | None = None,
) -> CatalogDecisionAuditEvent:
    """Build and emit exactly one event for ``decision``.

    Construction happens **before** emission, so a contract violation — a
    forbidden pattern, a missing actor — fails here rather than reaching a sink.
    """
    event = CatalogDecisionAuditEvent(
        correlation_id=correlation_id,
        occurred_at=occurred_at or decision.evaluated_at,
        decision_id=decision.decision_id,
        principal_id=principal_id,
        principal_type=principal_type,
        authorization_scope=authorization_scope,
        requested_operation=operation,
        metric_ids=tuple(sorted(request.metrics)),
        dimension_ids=tuple(sorted(request.dimensions)),
        source_ids=tuple(sorted(request.sources)),
        date_range=AuditDateRange(start=request.date_range.start, end=request.date_range.end),
        granted_access_tags=tuple(sorted(request.requester_access)),
        outcome=decision.outcome,
        reason_code=decision.reason_code,
        resolved_versions=_metric_version_ids(bundle, request),
        policy_version=decision.policy_version,
        catalog_release_id=decision.catalog_release_id,
        evidence_refs=tuple(decision.evidence_refs),
    )

    try:
        sink(event)
    except Exception as exc:  # a dropped event must not pass silently
        raise AuditEmissionError(
            f"the audit sink refused the event for decision {decision.decision_id}: {exc}"
        ) from exc

    return event


def evaluate_and_emit(
    request: CatalogValidationRequest,
    bundle: Bundle,
    sink: AuditSink,
    *,
    principal_id: str,
    principal_type: PrincipalType,
    authorization_scope: str,
    correlation_id: str,
    on: date,
    snapshot: FreshnessSnapshot | None = None,
    revisions: RevisionSnapshot | None = None,
    supersedes_decision_id: str | None = None,
    evaluated_at: datetime | None = None,
) -> EvaluatedDecision:
    """Run the pipeline, finalise on the revision evidence, emit one event.

    The order matters. Finalisation runs **before** emission so the event records
    the decision's final identity — an event citing a pre-evidence id could never
    be joined to the decision a consumer actually received.
    """
    decision = evaluate(
        request,
        bundle,
        principal_type=principal_type,
        authorization_scope=authorization_scope,
        on=on,
        snapshot=snapshot,
        evaluated_at=evaluated_at,
    )

    requirements = required_sources(bundle.internal.metrics, request.metrics, request.sources)
    required = tuple(r.source for r in requirements if r.required)
    resolution = resolve_revisions(
        required,
        revisions,
        period_start=request.date_range.start,
        period_end=request.date_range.end,
    )
    finalised = finalise(
        decision,
        request,
        resolution,
        metric_version_ids=_metric_version_ids(bundle, request),
        freshness_snapshot_ids=(
            (snapshot.snapshot_id,) if snapshot is not None and snapshot.snapshot_id else ()
        ),
        supersedes_decision_id=supersedes_decision_id,
    )

    event = emit_for_decision(
        finalised.decision,
        request,
        bundle,
        sink,
        principal_id=principal_id,
        principal_type=principal_type,
        correlation_id=correlation_id,
        authorization_scope=authorization_scope,
    )

    return EvaluatedDecision(decision=finalised.decision, finalised=finalised, event=event)
