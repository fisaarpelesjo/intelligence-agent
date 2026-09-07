"""Synchronous fail-closed audit emission — T096 (FR-050, FR-051, FR-053; SC-011).

**No result is released until its completion event is durably accepted.**
Emission is synchronous at all four stages, and a sink failure is fatal to the
request rather than logged and stepped over.

Where the failure lands determines what happens:

* before execution — the warehouse is never reached, so nothing was billed and
  nothing needs explaining;
* at ``EXECUTION_COMPLETE`` — the query already ran and was billed, so the
  **result is withheld**, the ledger entry retains `UNKNOWN`, and the caller
  receives ``AUDIT_EMISSION_FAILED``.

That second case is the uncomfortable one, and it is deliberate. A result
delivered without a durable audit record is a figure nobody can later attribute,
dispute or reproduce — and the moment it is out, no retrospective fix exists.
Retaining `UNKNOWN` is what lets a retry resume the audit path rather than
re-execute, so the caller pays a delay and never a second bill.

Fire-and-forget emission would make `SC-011` unmeasurable: "100% of stages emit
a correlated event" cannot be true if emission is allowed to fail quietly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from ..contracts._base import ContractViolation
from ..contracts.audit import AuditStage
from ..contracts.reason_codes import AnalyticsReasonCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..contracts.audit import AnalyticsAuditEvent

__all__ = [
    "PRE_EXECUTION_STAGES",
    "AuditEmissionFailed",
    "AuditSink",
    "emit_or_refuse",
    "withholds_result",
]


class AuditSink(Protocol):
    """Durable acceptance, or an exception. There is no third answer.

    A sink that returned a status code would invite a caller to inspect it and
    continue; raising is what makes "durably accepted" the only way past this
    line.
    """

    def accept(self, event: AnalyticsAuditEvent) -> None:
        """Persist the event durably. Raises if it could not."""
        ...


class AuditEmissionFailed(Exception):  # noqa: N818 - a governed refusal, not an error
    """The event could not be durably accepted."""

    def __init__(self, stage: AuditStage, detail: str) -> None:
        self.code = AnalyticsReasonCode.AUDIT_EMISSION_FAILED
        self.stage = stage
        self.detail = detail
        super().__init__(f"{self.code.value} at {stage.value}: {detail}")


#: Stages that occur before the warehouse is reached. A failure at one of these
#: costs nothing, because nothing was billed yet.
PRE_EXECUTION_STAGES: frozenset[AuditStage] = frozenset(
    {AuditStage.VALIDATION, AuditStage.REFUSAL, AuditStage.EXECUTION_START}
)


def withholds_result(stage: AuditStage) -> bool:
    """Whether a failure at this stage means a billed result must be withheld.

    Only ``EXECUTION_COMPLETE`` does. At the earlier stages the request never
    reached the warehouse, so there is no result to withhold and no cost to
    explain.
    """
    return stage is AuditStage.EXECUTION_COMPLETE


def emit_or_refuse(sink: AuditSink, event: AnalyticsAuditEvent) -> None:
    """Emit synchronously; refuse if the sink will not durably accept.

    Every sink failure becomes ``AUDIT_EMISSION_FAILED``. The distinction that
    matters to the caller is not *why* the sink failed but *when* — which
    ``withholds_result`` answers.
    """
    try:
        sink.accept(event)
    except AuditEmissionFailed:
        raise
    except Exception as exc:
        raise AuditEmissionFailed(
            event.stage, f"the audit sink did not accept the event: {exc}"
        ) from exc


def refusal_for(failure: AuditEmissionFailed) -> ContractViolation:
    """The caller-facing refusal for a failed emission.

    Names the code and nothing about the sink. Which store failed, and why, is
    an operational detail a caller has no business learning from a refusal.
    """
    _ = failure
    return ContractViolation(
        AnalyticsReasonCode.AUDIT_EMISSION_FAILED,
        "the request could not be recorded, so its result is not released",
    )
