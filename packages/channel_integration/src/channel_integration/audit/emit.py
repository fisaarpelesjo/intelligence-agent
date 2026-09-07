"""Six-stage audit emission — T048 (ADR 0019; FR-080 — FR-084; SC-039, SC-040).

**Synchronous and fail-closed.** A stage emits before the next begins, so a trail cannot show a
submission that was never verified, and a sink that cannot accept an event raises
:class:`AuditEmissionFailed` — the caller withholds rather than proceeding unrecorded
(`FR-083`).

**A refusal emits its own stage and nothing after it**, which is what makes "where did this
message stop?" a query rather than an investigation.

**No clock.** The event carries no timestamp of its own: correlation is by `correlation_id` and
`message_key`, and ordering is the stage enum. A clock read here would be a clock read on the
request path (`R-5`), and an event ordered by wall time would be an event two processes could
disagree about.

**Nothing content-bearing can be passed.** The event contract has no field for a payload, a
question, an answer, a value, a credential or a signature, and this module adds no way to attach
one. The `external_identity_ref` is derived through the `D-31` port, so while `D-31` is
undeclared **no compliant event is constructible** and the flow refuses with
``CHANNEL_AUDIT_UNAVAILABLE`` before delivery (`R-13`).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from ..contracts._base import CorrelationId, MessageKey, PrincipalRef, TenantId
from ..contracts.audit import ChannelAuditEvent, ChannelStage, DetailClass
from ..contracts.descriptor import ChannelId
from ..contracts.identity import ExternalIdentity, ExternalIdentityRef
from ..contracts.reason_codes import ChannelReasonCode, Outcome, channel_outcome_for
from ..identity.pseudonymise import PseudonymPort

__all__ = [
    "AUDIT_ACTOR_LABEL",
    "AuditEmissionFailed",
    "ChannelAuditSink",
    "build_event",
    "emit",
    "emit_sequence",
]

#: Domain separator for the actor reference, so an audit actor and a conversation scope derived
#: from the same identity are different references.
AUDIT_ACTOR_LABEL = "audit-actor"


class AuditEmissionFailed(Exception):  # noqa: N818 - a governed withholding, not an error
    """The sink did not durably accept an event.

    Distinct from a governed refusal: the message may have been perfectly valid. What failed is
    the record, and `FR-083` forbids releasing what cannot be recorded — so the caller withholds
    and the condition stays recoverable.
    """


@runtime_checkable
class ChannelAuditSink(Protocol):
    """Where events go. Durable acceptance is the sink's promise, not this module's.

    The durable archive is `EXT-B` (record `001:T110`) and remains open, so today's sinks are
    fixture sinks: events are emitted and **not** durably archived, reconstructibility is proven
    against fixtures, and nothing here claims otherwise.
    """

    def accept(self, event: ChannelAuditEvent) -> None:
        """Accept ``event`` durably, or raise."""
        ...


def build_event(
    stage: ChannelStage,
    channel: ChannelId,
    tenant: TenantId,
    principal_ref: PrincipalRef,
    correlation_id: CorrelationId,
    message_key: MessageKey,
    code: ChannelReasonCode,
    pseudonymiser: PseudonymPort,
    external: ExternalIdentity | None = None,
    detail_class: DetailClass = DetailClass.NONE,
    policy_version: str | None = None,
    capability_version: str | None = None,
) -> ChannelAuditEvent:
    """One compliant event, or refuse.

    ``outcome`` is **derived** from the code rather than passed: two sources for one fact would
    eventually disagree, and a mismatch there would let a denial be recorded as an allow.

    ``external`` is optional because a `RECEIVED` event precedes identity resolution — not
    because it may be omitted once known. When present it is pseudonymised through the `D-31`
    port, and while that material is undeclared the call refuses.
    """
    reference: ExternalIdentityRef | None = None
    if external is not None:
        reference = ExternalIdentityRef(
            value=pseudonymiser.derive(AUDIT_ACTOR_LABEL, external.reveal()),
            key_version=pseudonymiser.key_version,
        )
    return ChannelAuditEvent(
        stage=stage,
        channel=channel,
        tenant=tenant,
        principal_ref=principal_ref,
        external_identity_ref=reference,
        correlation_id=correlation_id,
        message_key=message_key,
        outcome=channel_outcome_for(code),
        code=code.value,
        detail_class=detail_class,
        policy_version=policy_version,
        capability_version=capability_version,
    )


def emit(sink: ChannelAuditSink, event: ChannelAuditEvent) -> None:
    """Emit one event synchronously, or raise :class:`AuditEmissionFailed`."""
    try:
        sink.accept(event)
    except AuditEmissionFailed:
        raise
    except Exception as exc:
        raise AuditEmissionFailed(
            f"the audit sink did not accept the {event.stage.value} event"
        ) from exc


def emit_sequence(sink: ChannelAuditSink, events: Iterable[ChannelAuditEvent]) -> None:
    """Emit in order, stopping at the first failure.

    Stopping is the point: continuing after a failed stage would produce a trail whose later
    stages claim progress the record never captured.
    """
    for event in events:
        emit(sink, event)


def outcome_of(code: ChannelReasonCode) -> Outcome:
    """The outcome class ``code`` records. Re-exported so callers need no second import."""
    return channel_outcome_for(code)
