"""Audit recovery — T097 (FR-034, FR-050, FR-078; SC-011, SC-012, SC-036).

A retry over an `UNKNOWN` entry **matching the full `ExecutionKey`** resumes the
audit path and never re-executes.

``audit_stages_accepted`` is what makes this resumable rather than a guess. It
records which stage events the sink durably accepted, so a retry knows exactly
where the previous attempt stopped and emits only what is still missing.
Without it the choices are re-emitting everything — duplicating records for
stages that succeeded — or emitting nothing and leaving the gap.

**The recovery path is key-scoped.** A request whose query identity matches but
whose authorization-context fingerprint differs presents a different key, and
therefore cannot resume, observe or inherit this audit trail (`FR-078`). It is
not merely refused a resume: it never sees the entry at all, because `get` and
`attach` require the full key.

The warehouse work is already paid for at this point, and the ledger records its
real cost. What the retry recovers is the **audit**, not the query — so a
transient sink outage costs a delay and never a second bill.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..contracts.audit import AuditStage
from ..execution.ledger_entry import ExecutionStatus

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..execution.ledger import ExecutionKey, ExecutionLedger
    from ..execution.ledger_entry import ExecutionLedgerEntry

__all__ = ["STAGE_ORDER", "RecoveryPlan", "plan_recovery", "stages_outstanding"]

#: The lifecycle order. Recovery emits what is missing in this order so a reader
#: of the audit trail sees the request unfold as it actually did.
STAGE_ORDER: tuple[AuditStage, ...] = (
    AuditStage.VALIDATION,
    AuditStage.REFUSAL,
    AuditStage.EXECUTION_START,
    AuditStage.EXECUTION_COMPLETE,
)


@dataclass(frozen=True, slots=True)
class RecoveryPlan:
    """What a retry must do to finish an interrupted request."""

    #: Stages still to emit, in lifecycle order.
    outstanding: tuple[AuditStage, ...]
    #: Always False. Recovery never re-executes — that is the whole point.
    re_execute: bool = False

    @property
    def is_complete(self) -> bool:
        """Whether the audit trail is already whole and nothing needs emitting."""
        return not self.outstanding


def stages_outstanding(accepted: tuple[AuditStage, ...]) -> tuple[AuditStage, ...]:
    """Which stages the sink has not durably accepted, in lifecycle order.

    ``REFUSAL`` is excluded when the request got as far as executing: a request
    that reached ``EXECUTION_START`` was not refused, so emitting a refusal
    event during recovery would fabricate an outcome that never happened.
    """
    already = set(accepted)
    executed = AuditStage.EXECUTION_START in already
    return tuple(
        stage
        for stage in STAGE_ORDER
        if stage not in already and not (executed and stage is AuditStage.REFUSAL)
    )


def plan_recovery(
    ledger: ExecutionLedger,
    key: ExecutionKey,
) -> RecoveryPlan | None:
    """Plan the audit work a retry must finish, or ``None`` if there is none.

    Returns ``None`` when no entry exists **for this exact key** — including
    when one exists for the same query identity under a different
    authorization-context fingerprint, which is invisible here by construction.

    Only an `UNKNOWN` entry is recoverable. A terminal entry finished and told
    its story; a running one still belongs to someone else.
    """
    entry: ExecutionLedgerEntry | None = ledger.get(key)
    if entry is None or entry.status is not ExecutionStatus.UNKNOWN:
        return None
    return RecoveryPlan(outstanding=stages_outstanding(entry.audit_stages_accepted))
