"""The analytics audit event — T026 (FR-052, FR-053, FR-054; SC-010).

A foundational contract, not an execution concern. Execution depends on it
(`T088` → `T026`), and so does every emitter and every result-release path: no
result is released before its completion event is durably accepted (ADR 0005).

`001`'s ``CatalogDecisionAuditEvent.requested_operation`` is a closed enum with no
``execute``, so this feature declares its own event carrying an explicit
``stage`` while reusing `001`'s ``AuditSink``. Transport stays undefined here,
exactly as the inherited `EXT-B` record requires.

**What the event may never carry** is enforced by the field set, not by review:
there is no field for a metric value, a fact row, a filter value, free-text
question input, a credential, or replayable query text. `metric_ids` and friends
are governed identifiers, so the event records *what was asked for* without
reproducing *what was typed*.

``principal_ref`` is opaque **and stable**. Opacity protects the subject;
stability preserves the audit, because an identifier that rotated per request
would make "this principal was refused eleven times" unobservable.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, StrictInt, model_validator
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode

from ._base import ContractViolation, QueryModel
from .reason_codes import AnalyticsReasonCode
from .reason_codes import outcome_for as analytics_outcome_for

__all__ = ["AnalyticsAuditEvent", "AuditStage", "PrincipalType"]


class AuditStage(StrEnum):
    """The four moments a request passes through.

    A pre-authorization refusal emits ``REFUSAL`` alone: it never reached the
    full evaluation, so there is no ``VALIDATION`` stage and no query identity.
    The correlation id, generated at request entry, is what joins the events.
    """

    VALIDATION = "validation"
    REFUSAL = "refusal"
    EXECUTION_START = "execution_start"
    EXECUTION_COMPLETE = "execution_complete"


class PrincipalType(StrEnum):
    """A human subject and a service principal need different review treatment."""

    USER = "user"
    SERVICE_PRINCIPAL = "service_principal"


class AnalyticsAuditEvent(QueryModel):
    """One event per lifecycle stage. Carries identifiers and outcomes, never data."""

    stage: AuditStage
    correlation_id: str = Field(min_length=1)
    #: Absent on a pre-authorization refusal, which never reaches the ledger.
    query_identity: str | None = None
    emitted_at: datetime

    # --- actor: pseudonymous, stable, never resolvable from this event alone ---
    principal_ref: str = Field(min_length=1)
    principal_type: PrincipalType
    authorization_scope: str | None = None
    granted_access_tags: tuple[str, ...] = ()

    # --- what was asked for, as governed identifiers only ---------------------
    metric_ids: tuple[str, ...] = ()
    dimension_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    date_range_start: str | None = None
    date_range_end: str | None = None

    # --- outcome and attribution ---------------------------------------------
    outcome: Outcome
    reason_code: AnalyticsReasonCode | ReasonCode
    resolved_versions: tuple[str, ...] = ()
    policy_version: str | None = None
    catalog_release_id: str | None = None

    # --- counts, never contents ----------------------------------------------
    dry_run_bytes: StrictInt | None = Field(default=None, ge=0)
    actual_bytes: StrictInt | None = Field(default=None, ge=0)
    row_count: StrictInt | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _outcome_matches_the_reason_code(self) -> AnalyticsAuditEvent:
        """The code decides the outcome; an emitter may not disagree with it.

        Letting two call sites disagree about whether the same refusal is a
        refusal is precisely how an audit trail stops being evidence. Both
        namespaces are checked against their own mapping.
        """
        if isinstance(self.reason_code, AnalyticsReasonCode):
            expected = analytics_outcome_for(self.reason_code)
        else:
            from semantic_catalog.contracts.reason_codes import outcome_for as catalog_outcome_for

            expected = catalog_outcome_for(self.reason_code)
        if self.outcome is not expected:
            raise ContractViolation(
                AnalyticsReasonCode.REQUEST_MALFORMED,
                (
                    f"reason code {self.reason_code.value} is classified "
                    f"{expected.value}, but the event claims {self.outcome.value}"
                ),
            )
        return self

    @model_validator(mode="after")
    def _pre_authorization_refusals_carry_no_identity(self) -> AnalyticsAuditEvent:
        """Absent, never zero-filled.

        Absent means "no execution was ever contemplated". A zero would assert an
        execution that measured nothing, which is a different and untrue claim.
        """
        if self.stage is AuditStage.REFUSAL and self.query_identity is None:
            for field, value in (
                ("dry_run_bytes", self.dry_run_bytes),
                ("actual_bytes", self.actual_bytes),
                ("row_count", self.row_count),
            ):
                if value is not None:
                    raise ContractViolation(
                        AnalyticsReasonCode.REQUEST_MALFORMED,
                        f"a pre-authorization refusal has no {field} to report",
                    )
        return self
