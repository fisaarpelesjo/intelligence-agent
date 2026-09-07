"""The interpretation audit event — T136 (FR-051, FR-052, FR-074; SC-025).

**Six stages, exact members, exact order.** `contracts/audit-and-observability.md`
§2 is the authoritative enum, and `T143` asserts equality *and* ordering — so an
arbitrary six-value enum cannot pass, and a reordering fails.

```
InterpretationStage = INTAKE | INTERPRETATION | CLARIFICATION | REFUSAL | SUBMISSION | RELEASE
```

## Why a third event type

`001`'s ``CatalogDecisionAuditEvent.requested_operation`` is a closed enum with no
interpretation value. `002` hit the same wall for ``execute`` and answered it with
a new event type on `001`'s existing sink protocol rather than editing an approved
artifact (ADR 0005) — and its event carries execution-shaped fields, dry-run
bytes, actual bytes, row count, that an interpretation stage has no values for.

So a third event type on the same sink **protocol**. Transport stays undefined
here exactly as `D-13` / `EXT-B` requires. Three event types is a consequence of
the additive rule, not drift.

## Absent, never zero-filled

A request refused at the authorization-context preflight emits `REFUSAL` alone —
it never reached step 9, so there is no interpretation identity to carry. Those
fields are **absent**, not zero-filled: absent means "no interpretation was ever
formed", while a zero would assert one that resolved to nothing. The
``correlation_id`` is generated at step 1 and is always present, so the events
still join.

## What it never carries

Denylist-scanned, and the denylist is enforced **twice** — by a declared field-set
test (`T138`: no field *can* hold a forbidden value) and by a serialised-content
scan over a fully populated event (`T139`: catching a value smuggled into a field
whose name sounds innocent). `002` established that either alone misses the
other's failure mode.

No question text or any span of it; no free-text reply content; no metric value,
row, aggregate or **computed difference**; no filter value; no caveat text
embedding a figure; no credential, token, session id or seal key material; no
name, email, IdP claim, IP or device id.

The type is the first enforcement. Every field below is an enum, a governed
identifier, an opaque reference, a date or a bounded integer — there is no
``payload``, no ``metadata``, no ``context``, no ``details`` and no ``extra``, so
a value has nowhere to land even before a scan looks for one.

**A comparison event carries the verdict, window, formula and outcome — never the
difference.** That asymmetry is the point of the whole contract: the event
records what was asked and decided, never what was returned.

``principal_ref`` is **stable and opaque**. Stability matters as much as opacity:
an identifier that rotated per question would satisfy privacy and destroy the
audit, because "this principal was refused eleven times" would be unobservable.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from pydantic import Field, StrictInt, model_validator
from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode

from ._base import InteractionModel
from .comparison import ComparisonRoute
from .reason_codes import InterpretationReasonCode

__all__ = [
    "AUDIT_EVENT_FIELDS",
    "IDENTITY_DERIVED_FIELDS",
    "STAGE_ORDER",
    "AuditPeriod",
    "InterpretationAuditEvent",
    "InterpretationStage",
    "outcome_for_code",
]


class InterpretationStage(StrEnum):
    """`contracts/audit-and-observability.md` §2, verbatim.

    | Stage | When |
    |---|---|
    | ``INTAKE`` | after the intake contract parses **and** the authorization context resolves |
    | ``INTERPRETATION`` | after ``ResolvedIntent`` is assembled and identity derived |
    | ``CLARIFICATION`` | on issuing a clarification **and** on every resumption attempt |
    | ``REFUSAL`` | on any refusal, including a pre-authorization one at step 2 |
    | ``SUBMISSION`` | before each governed request crosses the execution port, **per side** |
    | ``RELEASE`` | before the answer is returned to the caller |

    Declaration order is the contract's order and is asserted as such. A
    ``StrEnum`` preserves it, so ``tuple(InterpretationStage)`` is the sequence
    `T143` compares against — not a set, which would make the ordering claim
    unassertable.
    """

    INTAKE = "INTAKE"
    INTERPRETATION = "INTERPRETATION"
    CLARIFICATION = "CLARIFICATION"
    REFUSAL = "REFUSAL"
    SUBMISSION = "SUBMISSION"
    RELEASE = "RELEASE"


#: The six, in order. Named so a caller can assert the sequence without relying
#: on enum iteration order being obvious to a reader.
STAGE_ORDER: tuple[InterpretationStage, ...] = tuple(InterpretationStage)

#: Fields that exist only once step 9 has produced an interpretation. On a
#: pre-authorization refusal every one of them is ``None`` — **absent**, not
#: zero-filled — and `T143` asserts the distinction.
IDENTITY_DERIVED_FIELDS: tuple[str, ...] = (
    "interpretation_id",
    "period",
    "route",
    "rounds_consumed",
    "catalog_release",
    "policy_version",
    "vocabulary_version",
)


class AuditPeriod(InteractionModel):
    """The resolved period, as two dates and nothing else.

    A nested model rather than two loose fields so "the period" is one thing in
    the event as it is in the intent — and so a period cannot be half-present,
    which on an audit trail would be worse than absent.
    """

    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> AuditPeriod:
        if self.end < self.start:
            raise ValueError("the audited period ends before it starts")
        return self


class InterpretationAuditEvent(InteractionModel):
    """One governed interpretation event. **Strict, versioned, extra-forbidden.**

    ``schema_version`` is declared rather than implied: an event archived today
    is read years later by something that must know which contract produced it,
    and inferring the version from which fields happen to be present is how an
    archive becomes unreadable.

    Every field is an enum, a governed identifier, an opaque reference, a date or
    a bounded integer. There is deliberately no free-text field of any kind —
    ``reason_code`` carries the governed fact and the wording lives in the
    registry, so an event never holds a sentence anybody could have interpolated.
    """

    schema_version: StrictInt = Field(default=1, ge=1)
    stage: InterpretationStage
    correlation_id: str = Field(min_length=1)

    # --- identity-derived: absent before step 9 -----------------------------
    interpretation_id: str | None = None

    # --- who asked. Opaque, stable, never reversible ------------------------
    principal_ref: str = Field(min_length=1)
    principal_type: PrincipalType
    authorization_scope: str | None = None
    granted_access_tags: tuple[str, ...] = ()

    # --- what was asked, as governed identifiers only -----------------------
    metric_ids: tuple[str, ...] = ()
    dimension_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    period: AuditPeriod | None = None
    route: ComparisonRoute | None = None

    # --- what was decided ---------------------------------------------------
    outcome: Outcome
    reason_code: ReasonCode | AnalyticsReasonCode | InterpretationReasonCode

    # --- governing versions, absent before step 9 ---------------------------
    rounds_consumed: StrictInt | None = Field(default=None, ge=0)
    catalog_release: str | None = None
    policy_version: str | None = None
    vocabulary_version: str | None = None

    @model_validator(mode="after")
    def _a_pre_interpretation_event_carries_no_interpretation(self) -> InterpretationAuditEvent:
        """`INTAKE` and a pre-authorization `REFUSAL` precede step 9.

        An ``INTAKE`` event carrying an interpretation id would assert that an
        interpretation existed before the sequence reached the step that forms
        one — which would make the audit trail describe an ordering the code
        never performed.

        ``REFUSAL`` is deliberately **not** constrained: a refusal can occur at
        any step, and one raised after interpretation legitimately carries the
        identity. The distinction between "absent because it never existed" and
        "absent because this stage is early" is exactly what the trail must
        preserve.
        """
        if self.stage is InterpretationStage.INTAKE and self.interpretation_id is not None:
            raise ValueError("an INTAKE event precedes interpretation and carries no identity")
        return self

    @model_validator(mode="after")
    def _a_release_states_what_it_released_under(self) -> InterpretationAuditEvent:
        """A `RELEASE` names the interpretation and the versions it stood on.

        Without them the event records that *something* was released and nothing
        about what — which is the state `FR-054` exists to prevent, arriving
        through the audit trail rather than around it.
        """
        if self.stage is not InterpretationStage.RELEASE:
            return self

        missing = [
            name
            for name in ("interpretation_id", "catalog_release", "policy_version")
            if getattr(self, name) is None
        ]
        if missing:
            raise ValueError(
                "a RELEASE event states the interpretation and versions it released under"
            )
        return self

    @model_validator(mode="after")
    def _the_outcome_matches_its_governed_code(self) -> InterpretationAuditEvent:
        """The code decides the outcome; an emitter may not disagree with it.

        Each namespace classifies its own codes. Letting a caller pass ``ALLOW``
        beside a denial code would let two events disagree about whether the same
        refusal was a refusal — and an audit trail that contradicts itself is
        worse than one that is missing.
        """
        expected = outcome_for_code(self.reason_code)
        if self.outcome is not expected:
            raise ValueError(
                f"reason code {self.reason_code.value} is classified {expected.value}, "
                f"but the event claims {self.outcome.value}"
            )
        return self


def outcome_for_code(
    code: ReasonCode | AnalyticsReasonCode | InterpretationReasonCode,
) -> Outcome:
    """Classify a code through **its own** namespace's mapping.

    Public because an emitter has to compute the outcome it is about to assert,
    and a private helper would push every call site into either duplicating the
    dispatch or reaching past the underscore. One dispatch, one place.

    Three namespaces, three tables, and none of them is restated here. A local
    fourth table would be a second opinion about what an upstream code means, and
    the two would eventually disagree on the code that mattered.
    """
    if isinstance(code, InterpretationReasonCode):
        from .reason_codes import outcome_for as interpretation_outcome

        return Outcome(interpretation_outcome(code).value)
    if isinstance(code, AnalyticsReasonCode):
        from analytics_query.contracts.reason_codes import outcome_for as query_outcome

        return query_outcome(code)
    from semantic_catalog.contracts.reason_codes import outcome_for as catalog_outcome

    return catalog_outcome(code)


#: Every declared field, named once so `T138`'s denylist test asserts against the
#: contract rather than against a list restated in the test.
AUDIT_EVENT_FIELDS: tuple[str, ...] = tuple(
    InterpretationAuditEvent.model_fields  # pyright: ignore[reportUnannotatedClassAttribute]
)
