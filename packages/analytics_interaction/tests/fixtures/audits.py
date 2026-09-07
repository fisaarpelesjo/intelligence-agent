"""Phase 13 test support: audit sinks and fully populated events.

Three sinks, because the fail-closed matrix has three distinct failure shapes and
a single "broken sink" would prove only one of them:

* :class:`RecordingSink` accepts and remembers — the control, without which a
  suite asserting failures would pass against a system that never emitted;
* :class:`RaisingSink` raises, which is what a real sink does when a write fails;
* :class:`AcknowledgingSink` **returns a value**, which is subtler and more
  dangerous: it looks like success at every call site that does not inspect the
  result, and a sink answering "queued" would pass as one answering "stored".

:func:`populated_event` builds an event with **every** field set, which is what
the content scan needs. A scan over a sparse event proves nothing about the
fields nobody filled — and those are exactly where a value gets smuggled.

TEST-ONLY.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode

from analytics_interaction.contracts.audit import (
    AuditPeriod,
    InterpretationAuditEvent,
    InterpretationStage,
)
from analytics_interaction.contracts.comparison import ComparisonRoute

__all__ = [
    "AcknowledgingSink",
    "RaisingSink",
    "RecordingSink",
    "populated_event",
    "preauthorization_refusal",
    "release_event",
]


@dataclass
class RecordingSink:
    """Accepts every event and remembers it, in order.

    The control. A suite that only ever used failing sinks would pass against a
    system that emitted nothing at all, and the ordering assertions need a place
    the order is actually observable.
    """

    accepted: list[InterpretationAuditEvent] = field(default_factory=list[InterpretationAuditEvent])

    def accept(self, event: InterpretationAuditEvent) -> None:
        self.accepted.append(event)

    @property
    def stages(self) -> list[InterpretationStage]:
        return [event.stage for event in self.accepted]

    @property
    def count(self) -> int:
        return len(self.accepted)


@dataclass
class RaisingSink:
    """Raises on every call, and counts them.

    Counting matters as much as raising: `T143` proves refusal auditing
    terminates by asserting the count is **one**, which a sink that only raised
    could not show.
    """

    calls: list[InterpretationStage] = field(default_factory=list[InterpretationStage])
    error: type[Exception] = RuntimeError

    def accept(self, event: InterpretationAuditEvent) -> None:
        self.calls.append(event.stage)
        raise self.error("the fixture sink refuses every event")

    @property
    def count(self) -> int:
        return len(self.calls)


@dataclass
class AcknowledgingSink:
    """Returns a value instead of ``None``. **The malformed acknowledgement.**

    The subtlest of the three. It does not raise, so a caller that ignores the
    return value sees success — and a sink answering "queued" would pass as one
    answering "durably stored".
    """

    acknowledgement: object = "queued"
    calls: list[InterpretationStage] = field(default_factory=list[InterpretationStage])

    def accept(self, event: InterpretationAuditEvent) -> object:
        self.calls.append(event.stage)
        return self.acknowledgement

    @property
    def count(self) -> int:
        return len(self.calls)


def populated_event(
    stage: InterpretationStage = InterpretationStage.RELEASE,
    *,
    code: ReasonCode = ReasonCode.REQUEST_ALLOWED,
    correlation_id: str = "corr-1",
    interpretation_id: str | None = "interp-1",
) -> InterpretationAuditEvent:
    """An event with **every** field set, for the content scan.

    A sparse event would let the scan pass over fields nobody filled — and those
    are exactly where a value gets smuggled into a name that sounds innocent.

    Every value here is a governed identifier, an enum member, a date or a
    bounded integer. Nothing is prose, and nothing is a figure: the fixture obeys
    the same rule the contract does, so a scan failure means the *contract*
    leaked rather than the fixture.
    """
    from semantic_catalog.contracts.reason_codes import outcome_for

    return InterpretationAuditEvent(
        schema_version=1,
        stage=stage,
        correlation_id=correlation_id,
        interpretation_id=interpretation_id,
        principal_ref="p-1",
        principal_type=PrincipalType.USER,
        authorization_scope="tenant-a",
        granted_access_tags=("installs:read", "sessions:read"),
        metric_ids=("installs", "sessions"),
        dimension_ids=("country", "platform"),
        source_ids=("appstore", "playstore"),
        period=AuditPeriod(start=date(2026, 7, 1), end=date(2026, 7, 31)),
        route=ComparisonRoute.TWO_EXECUTION,
        outcome=outcome_for(code),
        reason_code=code,
        rounds_consumed=1,
        catalog_release="r-1",
        policy_version="pol-1",
        vocabulary_version="voc-1",
    )


def release_event(correlation_id: str = "corr-1") -> InterpretationAuditEvent:
    """The event that guards an answer. Named because it is asserted often."""
    return populated_event(InterpretationStage.RELEASE, correlation_id=correlation_id)


#: A pre-authorization refusal: no interpretation was ever formed, so every
#: identity-derived field is **absent** rather than zero-filled.
def preauthorization_refusal(correlation_id: str = "corr-1") -> InterpretationAuditEvent:
    """`REFUSAL` alone, from step 2. The distinction the trail must preserve."""
    return InterpretationAuditEvent(
        stage=InterpretationStage.REFUSAL,
        correlation_id=correlation_id,
        principal_ref="p-1",
        principal_type=PrincipalType.USER,
        outcome=Outcome.DENY,
        reason_code=ReasonCode.ACCESS_DENIED,
    )
