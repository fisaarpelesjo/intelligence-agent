"""A clarification chain reconstructs from audit alone — T142 (FR-083; SC-046).

    Evidence: a complete chain is reconstructible from audit alone despite the
    absence of state. — `tasks.md` T142

This feature holds no state. There is no conversation store, no session, no
ledger and no cache — so the only durable trace a multi-turn clarification leaves
is the audit trail, and if a chain cannot be reconstructed from that, it cannot
be reconstructed at all.

That is the claim under test, and it is a claim about **statelessness paying its
own way**: the design gave up server-side continuity, and what it owes in return
is a trail complete enough that an auditor asking "what happened to this
principal's question" gets a full answer from events.

## What a reconstruction needs, and how it is joined

``correlation_id``, generated at step 1 and present on **every** event including
pre-authorization refusals. It is the only join key, and it carries no principal
information — so a trail joins to itself without joining to a person.

`INTERPRETATION` onward also carry ``interpretation_id``, which distinguishes
*this* interpretation of a question from another principal's identical one.

## What the trail must not contain, and still does not

A reconstruction is exactly where the temptation to record "what they actually
asked" is strongest — it is the one thing that would make an auditor's job
easier. The suite asserts the chain is reconstructible **and** that the same
events carry no question text, no candidate wording, no seal preimage and no
value. Reconstructible and value-free at once is the whole difficulty.
"""

from __future__ import annotations

import re

import pytest
from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode

from analytics_interaction.audit.emit import AuditEmissionFailed, emit_sequence
from analytics_interaction.contracts.audit import (
    InterpretationAuditEvent,
    InterpretationStage,
    outcome_for_code,
)
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode

from ..fixtures.audits import RaisingSink, RecordingSink, populated_event, release_event

pytestmark = pytest.mark.integration

CORRELATION = "corr-chain-1"


def _event(
    stage: InterpretationStage,
    *,
    code: object = ReasonCode.REQUEST_ALLOWED,
    rounds: int | None = None,
    interpretation: str | None = "interp-1",
) -> InterpretationAuditEvent:
    """One event in a chain, carrying only what its stage may carry."""

    return InterpretationAuditEvent(
        stage=stage,
        correlation_id=CORRELATION,
        interpretation_id=None if stage is InterpretationStage.INTAKE else interpretation,
        principal_ref="p-1",
        principal_type=PrincipalType.USER,
        authorization_scope="tenant-a",
        granted_access_tags=("installs:read",),
        metric_ids=("installs",),
        outcome=outcome_for_code(code),  # pyright: ignore[reportArgumentType]
        reason_code=code,  # pyright: ignore[reportArgumentType]
        rounds_consumed=rounds,
        catalog_release=None if stage is InterpretationStage.INTAKE else "r-1",
        policy_version=None if stage is InterpretationStage.INTAKE else "pol-1",
        vocabulary_version=None if stage is InterpretationStage.INTAKE else "voc-1",
    )


#: A two-round clarification that resolves on the second reply and releases.
#:
#: Written as data so the reconstruction below reads the sequence rather than
#: re-deriving it — a test that built the chain from the same logic it checks
#: would be comparing an implementation to itself.
CHAIN: tuple[InterpretationAuditEvent, ...] = (
    _event(InterpretationStage.INTAKE),
    _event(InterpretationStage.INTERPRETATION, code=InterpretationReasonCode.INTENT_AMBIGUOUS),
    _event(
        InterpretationStage.CLARIFICATION,
        code=InterpretationReasonCode.CLARIFICATION_REQUIRED,
        rounds=0,
    ),
    _event(
        InterpretationStage.CLARIFICATION,
        code=InterpretationReasonCode.CLARIFICATION_REQUIRED,
        rounds=1,
    ),
    _event(InterpretationStage.INTERPRETATION),
    _event(InterpretationStage.SUBMISSION),
    _event(InterpretationStage.RELEASE),
)


# --- the chain reconstructs ----------------------------------------------------------


def test_the_whole_chain_is_recorded_in_order() -> None:
    """The trail is the sequence, and the sink sees it in the order it happened."""
    sink = RecordingSink()
    emit_sequence(sink, CHAIN)

    assert sink.stages == [
        InterpretationStage.INTAKE,
        InterpretationStage.INTERPRETATION,
        InterpretationStage.CLARIFICATION,
        InterpretationStage.CLARIFICATION,
        InterpretationStage.INTERPRETATION,
        InterpretationStage.SUBMISSION,
        InterpretationStage.RELEASE,
    ]


def test_every_event_joins_on_one_correlation_id() -> None:
    """**The only join key**, and the reason a stateless chain reconstructs.

    Generated at step 1 and present on every event, including a refusal that
    never reached interpretation.
    """
    sink = RecordingSink()
    emit_sequence(sink, CHAIN)

    assert {event.correlation_id for event in sink.accepted} == {CORRELATION}


def test_the_rounds_are_reconstructible_from_the_events_alone() -> None:
    """No state remembers them, so the trail must.

    Two clarification events, rounds 0 and 1: an auditor reads how many rounds
    this chain consumed without asking any component that kept a count.
    """
    sink = RecordingSink()
    emit_sequence(sink, CHAIN)

    rounds = [
        event.rounds_consumed
        for event in sink.accepted
        if event.stage is InterpretationStage.CLARIFICATION
    ]
    assert rounds == [0, 1]


def test_the_terminal_outcome_is_reconstructible() -> None:
    """Did this question end in an answer or a refusal? The trail says."""
    sink = RecordingSink()
    emit_sequence(sink, CHAIN)

    terminal = sink.accepted[-1]
    assert terminal.stage is InterpretationStage.RELEASE
    assert terminal.outcome is Outcome.ALLOW


def test_the_governing_versions_are_reconstructible_from_the_release() -> None:
    """Which definitions produced the answer, recoverable years later."""
    sink = RecordingSink()
    emit_sequence(sink, CHAIN)

    terminal = sink.accepted[-1]
    assert terminal.catalog_release == "r-1"
    assert terminal.policy_version == "pol-1"
    assert terminal.vocabulary_version == "voc-1"
    assert terminal.interpretation_id == "interp-1"


def test_a_chain_that_ends_in_refusal_reconstructs_too() -> None:
    """The other terminal shape, and the commoner one today."""
    refused = (
        _event(InterpretationStage.INTAKE),
        _event(
            InterpretationStage.CLARIFICATION,
            code=InterpretationReasonCode.CLARIFICATION_UNAVAILABLE,
            rounds=0,
        ),
        _event(
            InterpretationStage.REFUSAL,
            code=InterpretationReasonCode.CLARIFICATION_UNAVAILABLE,
        ),
    )
    sink = RecordingSink()
    emit_sequence(sink, refused)

    assert sink.stages[-1] is InterpretationStage.REFUSAL
    assert sink.accepted[-1].outcome is Outcome.DENY
    assert sink.accepted[-1].reason_code is InterpretationReasonCode.CLARIFICATION_UNAVAILABLE


def test_two_principals_asking_the_same_question_do_not_merge() -> None:
    """Distinct correlations, distinct chains.

    Without this, a reconstruction would attribute one principal's rounds to
    another's question — and the identity is deliberately principal-independent,
    so the correlation is what keeps them apart.
    """
    sink = RecordingSink()
    emit_sequence(sink, CHAIN)
    emit_sequence(
        sink,
        tuple(event.model_copy(update={"correlation_id": "corr-chain-2"}) for event in CHAIN),
    )

    correlations = {event.correlation_id for event in sink.accepted}
    assert correlations == {CORRELATION, "corr-chain-2"}
    assert len([e for e in sink.accepted if e.correlation_id == CORRELATION]) == len(CHAIN)


# --- and the chain still carries nothing forbidden --------------------------------------


def test_the_reconstructible_chain_carries_no_question_or_candidate_text() -> None:
    """**Reconstructible and value-free at once** — the whole difficulty.

    A reconstruction is exactly where recording "what they actually asked" is
    most tempting, because it is the one thing that would make an auditor's job
    easier.
    """
    sink = RecordingSink()
    emit_sequence(sink, CHAIN)

    payload = "".join(event.model_dump_json() for event in sink.accepted)
    for forbidden in ("quantas", "instalações?", "por favor", "sessions vs installs"):
        assert forbidden not in payload


def test_no_seal_preimage_or_key_material_reaches_the_trail() -> None:
    """A clarification event records lifecycle status, never the seal."""
    sink = RecordingSink()
    emit_sequence(sink, CHAIN)

    payload = "".join(event.model_dump_json() for event in sink.accepted)
    for forbidden in ("nonce", "seal", "key_id", "__algorithm__", "fixture-only-not-provisioned"):
        assert forbidden not in payload


def test_no_value_reaches_the_trail_at_any_stage() -> None:
    """The release event records that an answer was released, never the figure."""
    sink = RecordingSink()
    emit_sequence(sink, CHAIN)

    payload = "".join(event.model_dump_json() for event in sink.accepted)
    assert not re.search(r"[A-Za-z_]+\s*=\s*-?\d", payload)
    assert not re.search(r"(?<![\w.-])\d+\.\d{2,}(?![\w.])", payload)


def test_the_clarification_events_carry_only_lifecycle_and_safe_identifiers() -> None:
    """Status and rounds. No candidate wording, no reply, no contract body."""
    sink = RecordingSink()
    emit_sequence(sink, CHAIN)

    for event in sink.accepted:
        if event.stage is not InterpretationStage.CLARIFICATION:
            continue
        assert event.rounds_consumed is not None
        assert event.reason_code is InterpretationReasonCode.CLARIFICATION_REQUIRED
        assert set(event.metric_ids) <= {"installs"}


# --- and the chain is fail-closed at every link -------------------------------------------


def test_a_sink_failure_mid_chain_stops_the_chain() -> None:
    """A trail with a hole would imply a step that was never recorded.

    Continuing past it produces a reconstruction that reads as complete and is
    missing the event that mattered.
    """
    sink = RaisingSink()

    with pytest.raises(AuditEmissionFailed) as failure:
        emit_sequence(sink, CHAIN)

    assert failure.value.stage is InterpretationStage.INTAKE
    assert sink.count == 1


def test_the_release_is_withheld_when_its_own_event_fails() -> None:
    """The last link, and the one `FR-054` names."""

    class FailsOnRelease(RecordingSink):
        def accept(self, event: InterpretationAuditEvent) -> None:
            if event.stage is InterpretationStage.RELEASE:
                raise RuntimeError("no")
            super().accept(event)

    sink = FailsOnRelease()
    released: list[str] = []

    with pytest.raises(AuditEmissionFailed) as failure:
        emit_sequence(sink, CHAIN)
        released.append("answer")

    assert failure.value.stage is InterpretationStage.RELEASE
    assert released == []
    assert InterpretationStage.RELEASE not in sink.stages


def test_the_chain_is_deterministic() -> None:
    """`SC-028`: two equivalent flows yield equivalent ordered sequences."""
    first, second = RecordingSink(), RecordingSink()
    emit_sequence(first, CHAIN)
    emit_sequence(second, CHAIN)

    assert [event.model_dump_json() for event in first.accepted] == [
        event.model_dump_json() for event in second.accepted
    ]


def test_nothing_about_the_chain_is_stored_by_this_feature() -> None:
    """The sink is the caller's. This feature remembers nothing between calls.

    Two independent emissions of the same chain produce two independent records —
    no deduplication, no "already seen", no state that could make the second
    behave differently from the first.
    """
    sink = RecordingSink()
    emit_sequence(sink, CHAIN)
    emit_sequence(sink, CHAIN)

    assert sink.count == 2 * len(CHAIN)
    assert (
        release_event().model_dump_json()
        != populated_event(InterpretationStage.SUBMISSION).model_dump_json()
    )
