"""The audit contract — T143 (FR-051, FR-052, FR-054, FR-074; SC-025).

    Evidence: enum equality **and order** asserted against
    `contracts/audit-and-observability.md` §2; a reordered enum fails.
    — `tasks.md` T143

## The ordering assertion, and why equality alone is not enough

An arbitrary six-value enum satisfies "six members". A set comparison satisfies
"the same six names". Neither catches a reordering — and the order is the
sequence the trail describes, so an enum whose members were shuffled would
produce a trail that reads as a different sequence of events.

So the comparison is against a **tuple**, written out in full below rather than
derived from the enum it checks. Deriving it would compare the enum to itself.

## Absent, never zero-filled

A pre-authorization refusal never reached step 9, so it carries no interpretation
identity — and the fields are ``None`` rather than ``""`` or ``0``. Absent means
"no interpretation was ever formed"; a zero would assert one that resolved to
nothing, and a reader could not tell the two apart.

## Emission is synchronous, and each stage's failure withholds correctly

The whole matrix is asserted, stage by stage, against all three sink failure
shapes: raising, returning a value, and absent. A single "broken sink" case would
prove one shape and miss the two that look like success.
"""

from __future__ import annotations

import ast
import contextlib
import inspect
from pathlib import Path
from typing import cast

import pytest
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode

from analytics_interaction.audit import emit as emit_module
from analytics_interaction.audit.emit import (
    WITHHOLDING,
    AuditEmissionFailed,
    InterpretationAuditSink,
    emit,
    emit_sequence,
)
from analytics_interaction.contracts.audit import (
    AUDIT_EVENT_FIELDS,
    IDENTITY_DERIVED_FIELDS,
    STAGE_ORDER,
    InterpretationAuditEvent,
    InterpretationStage,
    outcome_for_code,
)
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode

from ..fixtures.audits import (
    AcknowledgingSink,
    RaisingSink,
    RecordingSink,
    populated_event,
    preauthorization_refusal,
    release_event,
)

pytestmark = pytest.mark.contract

#: §2's enum, written out. **Not derived from the enum under test** — deriving it
#: would compare the enum to itself and assert nothing.
CONTRACT_STAGES: tuple[str, ...] = (
    "INTAKE",
    "INTERPRETATION",
    "CLARIFICATION",
    "REFUSAL",
    "SUBMISSION",
    "RELEASE",
)


# --- exactly six stages, in exactly this order -------------------------------------


def test_the_stage_enum_equals_the_contract_exactly() -> None:
    """Members **and** order. An arbitrary six-value enum fails."""
    assert tuple(stage.value for stage in InterpretationStage) == CONTRACT_STAGES
    assert tuple(STAGE_ORDER) == tuple(InterpretationStage)
    assert len(InterpretationStage) == 6


def test_a_reordered_enum_would_fail_this_assertion() -> None:
    """The ordering claim, shown to be load-bearing.

    A set comparison passes on a shuffled enum; the tuple comparison above does
    not. This demonstrates the difference rather than asserting it in prose.
    """
    shuffled = ("RELEASE", "INTAKE", "INTERPRETATION", "CLARIFICATION", "REFUSAL", "SUBMISSION")

    assert set(shuffled) == set(CONTRACT_STAGES)
    assert shuffled != CONTRACT_STAGES


def test_no_stage_was_added_or_renamed() -> None:
    """A seventh stage is a contract change, not an implementation detail."""
    assert set(InterpretationStage) == {
        InterpretationStage.INTAKE,
        InterpretationStage.INTERPRETATION,
        InterpretationStage.CLARIFICATION,
        InterpretationStage.REFUSAL,
        InterpretationStage.SUBMISSION,
        InterpretationStage.RELEASE,
    }


def test_the_stage_is_a_str_enum_so_order_survives_iteration() -> None:
    """A plain set of strings would make the ordering claim unassertable."""
    assert issubclass(InterpretationStage, str)
    ordered = list(InterpretationStage)
    assert ordered[0] is InterpretationStage.INTAKE
    assert ordered[-1] is InterpretationStage.RELEASE


# --- every required field present ----------------------------------------------------


def test_the_event_declares_every_contract_field() -> None:
    """`data-model.md` §8's field list, present and named."""
    required = {
        "stage",
        "correlation_id",
        "interpretation_id",
        "principal_ref",
        "principal_type",
        "authorization_scope",
        "granted_access_tags",
        "metric_ids",
        "dimension_ids",
        "source_ids",
        "period",
        "route",
        "outcome",
        "reason_code",
        "rounds_consumed",
        "catalog_release",
        "policy_version",
        "vocabulary_version",
    }
    assert required <= set(AUDIT_EVENT_FIELDS)


def test_the_event_is_versioned() -> None:
    """An archive read years later must know which contract produced its rows."""
    assert "schema_version" in AUDIT_EVENT_FIELDS
    assert populated_event().schema_version == 1


def test_an_unknown_field_refuses() -> None:
    """``extra="forbid"``: no payload, metadata, context, details or extension."""
    with pytest.raises(ValueError, match="extra"):
        InterpretationAuditEvent.model_validate(
            {**populated_event().model_dump(), "payload": {"question": "quantas instalações?"}}
        )


@pytest.mark.parametrize(
    "field", ["payload", "metadata", "context", "details", "extra", "attributes", "notes"]
)
def test_no_free_form_extension_field_is_declared(field: str) -> None:
    """The names a value arrives under when nobody declared one for it."""
    assert field not in AUDIT_EVENT_FIELDS


def test_an_unknown_stage_refuses() -> None:
    with pytest.raises(ValueError, match="stage"):
        InterpretationAuditEvent.model_validate(
            {**populated_event().model_dump(), "stage": "ARCHIVED"}
        )


def test_an_unknown_outcome_refuses() -> None:
    with pytest.raises(ValueError):
        InterpretationAuditEvent.model_validate(
            {**populated_event().model_dump(), "outcome": "MAYBE"}
        )


def test_a_zero_schema_version_refuses() -> None:
    with pytest.raises(ValueError):
        InterpretationAuditEvent.model_validate(
            {**populated_event().model_dump(), "schema_version": 0}
        )


# --- absent, never zero-filled --------------------------------------------------------


def test_a_pre_authorization_refusal_carries_no_identity_derived_field() -> None:
    """**The distinction the trail must preserve.**

    Absent means "no interpretation was ever formed". A zero would assert one
    that resolved to nothing, and a reader could not tell the two apart.
    """
    event = preauthorization_refusal()

    for name in IDENTITY_DERIVED_FIELDS:
        assert getattr(event, name) is None, name


def test_the_absent_fields_are_none_and_not_empty_strings() -> None:
    """``""`` and ``0`` are assertions; ``None`` is an absence."""
    event = preauthorization_refusal()

    assert event.interpretation_id is None
    assert event.catalog_release is None
    assert event.rounds_consumed is None
    assert event.period is None
    assert event.rounds_consumed != 0
    assert event.catalog_release != ""


def test_the_correlation_id_is_present_even_before_interpretation() -> None:
    """Generated at step 1, so pre-authorization events still join the trail."""
    assert preauthorization_refusal().correlation_id == "corr-1"


def test_an_intake_event_carrying_an_interpretation_identity_refuses() -> None:
    """`INTAKE` precedes step 9; an identity there describes an ordering nobody ran."""
    with pytest.raises(ValueError, match="precedes interpretation"):
        populated_event(InterpretationStage.INTAKE)


def test_a_refusal_after_interpretation_may_carry_the_identity() -> None:
    """A refusal happens at any step; the late ones legitimately carry it."""
    late = populated_event(InterpretationStage.REFUSAL, code=ReasonCode.METRICS_NOT_COMPARABLE)
    assert late.interpretation_id == "interp-1"


def test_a_release_without_its_versions_refuses() -> None:
    """An event recording that *something* was released records nothing."""
    with pytest.raises(ValueError, match="RELEASE event states"):
        InterpretationAuditEvent.model_validate(
            {**release_event().model_dump(), "catalog_release": None}
        )


# --- codes come from their own namespaces --------------------------------------------


@pytest.mark.parametrize(
    "code",
    [
        ReasonCode.REQUEST_ALLOWED,
        AnalyticsReasonCode.AUDIT_EMISSION_FAILED,
        InterpretationReasonCode.TERM_NOT_GOVERNED,
    ],
)
def test_a_code_from_any_of_the_three_namespaces_is_accepted(code: object) -> None:
    """Three namespaces, one event type. None is translated into another."""

    event = InterpretationAuditEvent(
        stage=InterpretationStage.REFUSAL,
        correlation_id="corr-1",
        principal_ref="p-1",
        principal_type=PrincipalType.USER,
        outcome=outcome_for_code(code),  # pyright: ignore[reportArgumentType]
        reason_code=code,  # pyright: ignore[reportArgumentType]
    )
    assert event.reason_code is code


def test_an_outcome_disagreeing_with_its_code_refuses() -> None:
    """Two events must not disagree about whether one refusal was a refusal."""
    with pytest.raises(ValueError, match="classified"):
        InterpretationAuditEvent(
            stage=InterpretationStage.REFUSAL,
            correlation_id="corr-1",
            principal_ref="p-1",
            principal_type=PrincipalType.USER,
            outcome=Outcome.ALLOW,
            reason_code=ReasonCode.ACCESS_DENIED,
        )


def test_the_classification_is_read_from_each_namespaces_own_table() -> None:
    """No local fourth table. A second opinion would eventually disagree."""
    source = Path(inspect.getfile(InterpretationAuditEvent)).read_text(encoding="utf-8")
    assert source.count("outcome_for") >= 3
    assert "REASON_CODE_OUTCOME = {" not in source


# --- emission is synchronous and fails closed ------------------------------------------


def test_a_healthy_sink_accepts_and_the_stage_completes() -> None:
    """The control. Without it, every failure assertion below is vacuous."""
    sink = RecordingSink()
    emit(sink, release_event())

    assert sink.count == 1
    assert sink.stages == [InterpretationStage.RELEASE]


@pytest.mark.parametrize("stage", list(InterpretationStage), ids=lambda s: s.value)
def test_a_raising_sink_withholds_at_every_stage(stage: InterpretationStage) -> None:
    """The whole matrix. Every stage's failure is a withholding."""
    sink = RaisingSink()
    event = (
        preauthorization_refusal()
        if stage is InterpretationStage.REFUSAL
        else populated_event(
            stage, interpretation_id=None if stage is InterpretationStage.INTAKE else "interp-1"
        )
    )

    with pytest.raises(AuditEmissionFailed) as failure:
        emit(sink, event)

    assert failure.value.stage is stage
    assert failure.value.code is AnalyticsReasonCode.AUDIT_EMISSION_FAILED
    assert failure.value.withheld == WITHHOLDING[stage]
    assert sink.count == 1


@pytest.mark.parametrize("stage", list(InterpretationStage), ids=lambda s: s.value)
def test_every_stage_has_a_declared_withholding(stage: InterpretationStage) -> None:
    """There is no stage whose audit failure is survivable."""
    assert stage in WITHHOLDING
    assert WITHHOLDING[stage]


def test_a_malformed_acknowledgement_withholds() -> None:
    """**The subtle one.** It does not raise, so it looks like success.

    A sink answering "queued" would otherwise pass as one answering "durably
    stored", and the answer would be released against an event nobody kept.
    """
    sink = AcknowledgingSink()

    with pytest.raises(AuditEmissionFailed) as failure:
        emit(cast("InterpretationAuditSink", sink), release_event())

    assert "malformed acknowledgement" in failure.value.detail
    assert sink.count == 1


@pytest.mark.parametrize("acknowledgement", ["queued", 200, True, {"status": "ok"}, []])
def test_any_returned_value_is_malformed(acknowledgement: object) -> None:
    """``None`` is the only acknowledgement. Everything else is a third answer."""
    with pytest.raises(AuditEmissionFailed):
        emit(
            cast("InterpretationAuditSink", AcknowledgingSink(acknowledgement=acknowledgement)),
            release_event(),
        )


def test_an_absent_sink_withholds_rather_than_bypassing() -> None:
    """A default no-op sink would make every guarantee here vacuous."""
    with pytest.raises(AuditEmissionFailed) as failure:
        emit(None, release_event())
    assert failure.value.stage is InterpretationStage.RELEASE


def test_a_release_is_withheld_when_its_audit_write_fails() -> None:
    """`FR-054`, stated as the rule it is.

    Releasing a value whose derivation could not be recorded produces an answer
    in the world with no trace of who asked for it.
    """
    released: list[str] = []

    def release_under_audit(sink: object) -> None:
        emit(sink, release_event())  # pyright: ignore[reportArgumentType]
        released.append("answer")

    with pytest.raises(AuditEmissionFailed):
        release_under_audit(RaisingSink())

    assert released == []


def test_the_answer_is_released_only_after_a_successful_release_event() -> None:
    """The positive half, so the ordering is observable rather than implied."""
    sink = RecordingSink()
    released: list[str] = []

    emit(sink, release_event())
    released.append("answer")

    assert sink.count == 1
    assert released == ["answer"]


# --- refusal auditing terminates ---------------------------------------------------------


def test_a_failed_refusal_emission_is_not_re_audited() -> None:
    """**Termination, counted.**

    A second `REFUSAL` describing the first's emission failure would fail the same
    way, and the loop is unbounded. The count is one.
    """
    sink = RaisingSink()

    with pytest.raises(AuditEmissionFailed) as failure:
        emit(sink, preauthorization_refusal())

    assert sink.count == 1
    assert failure.value.stage is InterpretationStage.REFUSAL
    assert failure.value.withheld == "the refusal stands and the failure is raised"


def test_an_audit_failure_from_a_sink_is_not_wrapped_twice() -> None:
    """One stage's failure is never reported as another's."""
    sink = RaisingSink(error=type("Boom", (Exception,), {}))

    with pytest.raises(AuditEmissionFailed) as failure:
        emit(sink, populated_event(InterpretationStage.SUBMISSION))

    assert failure.value.stage is InterpretationStage.SUBMISSION


def test_the_emitter_calls_the_sink_exactly_once() -> None:
    """No retry, no fallback, no second attempt on any path."""
    for sink in (RecordingSink(), AcknowledgingSink()):
        with contextlib.suppress(AuditEmissionFailed):
            emit(cast("InterpretationAuditSink", sink), release_event())
        assert sink.count == 1


# --- sequences stop at the first failure ---------------------------------------------------


def test_a_sequence_emits_in_order() -> None:
    """The trail is the order the sequence occurred in."""
    sink = RecordingSink()
    sequence = (
        populated_event(InterpretationStage.INTAKE, interpretation_id=None),
        populated_event(InterpretationStage.INTERPRETATION),
        populated_event(InterpretationStage.SUBMISSION),
        release_event(),
    )

    emit_sequence(sink, sequence)

    assert sink.stages == [
        InterpretationStage.INTAKE,
        InterpretationStage.INTERPRETATION,
        InterpretationStage.SUBMISSION,
        InterpretationStage.RELEASE,
    ]


def test_a_sequence_stops_at_the_first_failure() -> None:
    """Continuing would produce a trail implying an event nobody recorded."""

    class FailsOnSubmission(RecordingSink):
        def accept(self, event: InterpretationAuditEvent) -> None:
            if event.stage is InterpretationStage.SUBMISSION:
                raise RuntimeError("no")
            super().accept(event)

    sink = FailsOnSubmission()
    sequence = (
        populated_event(InterpretationStage.INTAKE, interpretation_id=None),
        populated_event(InterpretationStage.SUBMISSION),
        release_event(),
    )

    with pytest.raises(AuditEmissionFailed) as failure:
        emit_sequence(sink, sequence)

    assert failure.value.stage is InterpretationStage.SUBMISSION
    assert sink.stages == [InterpretationStage.INTAKE]


# --- determinism, and no clock ---------------------------------------------------------------


def test_equivalent_events_serialise_byte_identically() -> None:
    """`SC-028`. Two identical flows produce equivalent ordered sequences."""
    assert populated_event().model_dump_json() == populated_event().model_dump_json()


def test_no_clock_is_read_during_emission() -> None:
    """A timestamp read here would make every event unequal to every other."""
    for module in (emit_module,):
        tree = ast.parse(Path(inspect.getfile(module)).read_text(encoding="utf-8"))
        names = {
            node.attr if isinstance(node, ast.Attribute) else node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute | ast.Name)
        }
        assert not names & {"now", "utcnow", "today", "time", "monotonic", "perf_counter"}


def test_the_event_declares_no_timestamp_field() -> None:
    """Instants are supplied where a contract requires them, never read here."""
    assert "emitted_at" not in AUDIT_EVENT_FIELDS
    assert "timestamp" not in AUDIT_EVENT_FIELDS
