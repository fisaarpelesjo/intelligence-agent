"""Ledger entry, attachment record and status machine — T040 (FR-065, FR-066, FR-078).

**Metadata only, enforced by the field set.** There is no field capable of
holding a metric value, a result row, an aggregate, a filter value or query text
— not on the entry, and not on an attachment record either. A field-set test and
a serialised-content scan assert it, but the first line of defence is that no
such field is declared here (`FR-066`, `SC-013`).

``UNKNOWN`` is the honest terminal for a lost outcome. A process that dies
mid-flight leaves a question the system cannot answer truthfully any other way:
collapsing it into "never ran" would silently double-bill, and collapsing it into
"completed" would silently lose a result. Naming the uncertainty is what lets a
retry resolve through the ledger instead of by assumption.

**Attribution is append-only.** ``principal_ref`` names the *acquiring*
principal and is never rewritten. Every later attachment appends its own record,
so "who received this figure" stays answerable — which matters regardless of
tenancy, even where both callers are equally entitled to the data (`FR-078`).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, StrictInt, model_validator
from semantic_catalog.contracts.reason_codes import ReasonCode

from ..contracts._base import ContractViolation, QueryModel, build
from ..contracts.audit import AuditStage
from ..contracts.reason_codes import AnalyticsReasonCode

__all__ = [
    "TERMINAL_STATUSES",
    "ExecutionAttachment",
    "ExecutionLedgerEntry",
    "ExecutionStatus",
]


class ExecutionStatus(StrEnum):
    """Where an execution stands.

    ``PLANNED → DRY_RUN_OK → RUNNING →`` one of the terminals.
    """

    PLANNED = "planned"
    DRY_RUN_OK = "dry_run_ok"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED_OVER_LIMIT = "cancelled_over_limit"
    UNKNOWN = "unknown"


#: Terminal states. A retry against one of these is a **re-request** — a fresh
#: attempt with its own entry, billed on its own. `RUNNING` and `UNKNOWN` are
#: deliberately absent: both mean the execution may still be live or may already
#: have billed, so both attach rather than re-execute.
TERMINAL_STATUSES: frozenset[ExecutionStatus] = frozenset(
    {
        ExecutionStatus.COMPLETED,
        ExecutionStatus.FAILED,
        ExecutionStatus.TIMED_OUT,
        ExecutionStatus.CANCELLED_OVER_LIMIT,
    }
)


class ExecutionAttachment(QueryModel):
    """One principal attaching to an execution acquired by another.

    Carries the same content denylist as the entry: no values, filter values,
    credentials or query text. It records *that* a principal received this
    execution's result, never *what* the result was.
    """

    principal_ref: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)
    attached_at: datetime


class ExecutionLedgerEntry(QueryModel):
    """The execution of record for one ``ExecutionKey``."""

    # --- key: both halves, always ---
    query_identity: str = Field(min_length=1)
    authorization_context_fingerprint: str = Field(min_length=1)

    # --- attribution ---
    correlation_id: str = Field(min_length=1)
    #: The **acquiring** principal. Opaque, stable, pseudonymous — never a name,
    #: email or IdP claim, and never rewritten by a later attachment.
    principal_ref: str = Field(min_length=1)
    attachments: tuple[ExecutionAttachment, ...] = ()

    status: ExecutionStatus

    # --- cost and shape: counts only, never contents ---
    dry_run_bytes: StrictInt | None = Field(default=None, ge=0)
    actual_bytes: StrictInt | None = Field(default=None, ge=0)
    row_count: StrictInt | None = Field(default=None, ge=0)

    started_at: datetime | None = None
    ended_at: datetime | None = None

    data_revisions: tuple[str, ...] = ()
    catalog_release_id: str | None = None
    policy_version: str | None = None
    warehouse_job_ref: str | None = None
    terminal_reason_code: AnalyticsReasonCode | ReasonCode | None = None

    #: Which stage events the sink durably accepted — what makes audit recovery
    #: resumable rather than a guess.
    audit_stages_accepted: tuple[AuditStage, ...] = ()

    @model_validator(mode="after")
    def _terminal_entries_are_closed(self) -> ExecutionLedgerEntry:
        """A terminal entry must say when it ended and why.

        An entry that reports `COMPLETED` with no end instant cannot be
        reconciled against a warehouse bill, which is most of what the ledger is
        for.
        """
        if self.status in TERMINAL_STATUSES and self.ended_at is None:
            raise ContractViolation(
                AnalyticsReasonCode.REQUEST_MALFORMED,
                f"a {self.status.value} entry must record ended_at",
            )
        if self.status is ExecutionStatus.UNKNOWN and self.ended_at is not None:
            raise ContractViolation(
                AnalyticsReasonCode.REQUEST_MALFORMED,
                "an UNKNOWN entry has no honest end instant; the outcome is precisely "
                "what was lost",
            )
        return self

    @model_validator(mode="after")
    def _attachments_are_distinct_from_the_acquirer(self) -> ExecutionLedgerEntry:
        """The acquirer is attributed by ``principal_ref``, not by an attachment.

        Recording the acquirer twice would make "how many principals received
        this" wrong, which is the one question the attachment list exists to
        answer.
        """
        seen: set[tuple[str, str]] = set()
        for attachment in self.attachments:
            marker = (attachment.principal_ref, attachment.correlation_id)
            if marker in seen:
                raise ContractViolation(
                    AnalyticsReasonCode.REQUEST_MALFORMED,
                    "duplicate attachment record for the same principal and correlation id",
                )
            seen.add(marker)
            if attachment.correlation_id == self.correlation_id:
                raise ContractViolation(
                    AnalyticsReasonCode.REQUEST_MALFORMED,
                    "the acquiring request is attributed by principal_ref, not by an attachment",
                )
        return self

    def with_attachment(self, attachment: ExecutionAttachment) -> ExecutionLedgerEntry:
        """Append an attachment, leaving the acquirer's attribution untouched.

        Re-validates rather than using ``model_copy`` alone: ``model_copy``
        bypasses validators, so the acquirer-duplication and distinctness rules
        above would never run on the one path that actually adds an attachment.
        """
        candidate = self.model_copy(update={"attachments": (*self.attachments, attachment)})
        return build(ExecutionLedgerEntry, **candidate.model_dump())
