"""The audit event's field set — T067 (ADR 0019; FR-081, FR-082; SC-039).

Three claims, and each is about a *set* rather than about one event:

* the **required** set is present and none of it is optional-by-accident: an event missing a tenant,
  a correlation id or an outcome is not a weaker record, it is an unusable one;
* the **forbidden** set is unrepresentable, so a value cannot be added — asserted by field set
  here and by serialised scan in `T065`;
* ``detail_class`` exists on the event and **never** on a response, which is the mechanism that
  lets the three deliberate collapses (ADR 0018) stay non-disclosing to a sender and analysable
  by an operator.

Two derived facts are asserted rather than trusted, because a second source for either would
eventually disagree with the first:

* ``outcome`` is **derived** from the code inside `build_event`, never passed in — so a DENY code
  cannot be recorded with an ALLOW outcome;
* the six stages are ordered by their declaration, and `CHANNEL_STAGE_ORDER` is that order.
"""

from __future__ import annotations

import inspect

import pytest
from pydantic import ValidationError

from channel_integration.audit.emit import build_event
from channel_integration.contracts._base import ChannelViolation, MessageKey
from channel_integration.contracts.audit import (
    CHANNEL_STAGE_ORDER,
    ChannelAuditEvent,
    ChannelStage,
    DetailClass,
)
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.reason_codes import ChannelReasonCode, Outcome
from channel_integration.contracts.refusal import ChannelRefusal, refusal_from_violation

from ..fixtures.identity import (
    FIXTURE_EXTERNAL,
    FIXTURE_PRINCIPAL,
    FIXTURE_TENANT,
    fixture_pseudonymiser,
)

pytestmark = pytest.mark.contract

#: Every field a compliant event must carry. The list is the contract, so it is written out rather
#: than derived from the model — a test that read the model would agree with any model.
_REQUIRED = {
    "stage",
    "channel",
    "tenant",
    "principal_ref",
    "correlation_id",
    "message_key",
    "outcome",
    "code",
}

#: Present, but legitimately absent in some states: the external reference before identity
#: resolution, the two governing versions while `D-26` and `D-28` are undeclared.
_CONDITIONAL = {"external_identity_ref", "detail_class", "policy_version", "capability_version"}


def _event(**overrides: object) -> ChannelAuditEvent:
    pseudonymiser = fixture_pseudonymiser()
    arguments: dict[str, object] = {
        "stage": ChannelStage.RECEIVED,
        "channel": ChannelId.SLACK,
        "tenant": FIXTURE_TENANT,
        "principal_ref": FIXTURE_PRINCIPAL,
        "correlation_id": "fixture-correlation-1",
        "message_key": MessageKey("fixture-message-key-1"),
        "code": ChannelReasonCode.CHANNEL_MESSAGE_ACCEPTED,
        "pseudonymiser": pseudonymiser,
    }
    arguments.update(overrides)
    return build_event(**arguments)  # type: ignore[arg-type]


def test_the_field_set_is_exactly_the_required_plus_the_conditional() -> None:
    assert set(ChannelAuditEvent.model_fields) == _REQUIRED | _CONDITIONAL


@pytest.mark.parametrize("field", sorted(_REQUIRED))
def test_every_required_field_is_required(field: str) -> None:
    """A required field with a default is an optional field with good intentions."""
    info = ChannelAuditEvent.model_fields[field]
    assert info.is_required(), f"{field} has a default and could be silently absent"


def test_an_event_missing_a_required_field_cannot_be_constructed() -> None:
    with pytest.raises(ValidationError):
        ChannelAuditEvent(  # type: ignore[call-arg]
            stage=ChannelStage.RECEIVED,
            channel=ChannelId.SLACK,
            tenant=FIXTURE_TENANT,
            principal_ref=FIXTURE_PRINCIPAL,
            message_key=MessageKey("fixture-message-key-1"),
            outcome=Outcome.ALLOW,
            code="CHANNEL_MESSAGE_ACCEPTED",
        )


def test_an_undeclared_field_is_refused_rather_than_ignored() -> None:
    """Closed twice, and both closures are asserted because they fail independently.

    The emitter has no parameter for a content-bearing field, so the call is a ``TypeError``; and
    the model is ``extra="forbid"``, so constructing one directly is a ``ValidationError``. Either
    alone would leave a route open — a new emitter keyword, or a direct construction.
    """
    with pytest.raises(TypeError, match="question"):
        _event(question="quantas instalações?")

    # Validated from a mapping rather than by keyword, because the keyword form is a static type
    # error: the field genuinely does not exist. The mapping is how a deserialised event would
    # arrive from a sink, which is the route that has to be closed at runtime.
    with pytest.raises(ValidationError) as caught:
        ChannelAuditEvent.model_validate(
            {
                "stage": ChannelStage.RECEIVED,
                "channel": ChannelId.SLACK,
                "tenant": FIXTURE_TENANT,
                "principal_ref": FIXTURE_PRINCIPAL,
                "correlation_id": "fixture-correlation-1",
                "message_key": "fixture-message-key-1",
                "outcome": Outcome.ALLOW,
                "code": "CHANNEL_MESSAGE_ACCEPTED",
                "question": "quantas instalações?",
            }
        )
    assert "question" in str(caught.value)


def test_the_outcome_is_derived_from_the_code_and_cannot_be_passed() -> None:
    """Two sources for one fact would eventually let a denial be recorded as an allow."""
    parameters = set(inspect.signature(build_event).parameters)
    assert "outcome" not in parameters
    assert _event(code=ChannelReasonCode.CHANNEL_MESSAGE_ACCEPTED).outcome is Outcome.ALLOW
    assert _event(code=ChannelReasonCode.CHANNEL_SIGNATURE_INVALID).outcome is Outcome.DENY


def test_the_external_reference_is_optional_only_before_identity_is_known() -> None:
    """Optional for a reason that is stated, not for convenience."""
    received = _event(stage=ChannelStage.RECEIVED)
    assert received.external_identity_ref is None
    identified = _event(stage=ChannelStage.IDENTIFIED, external=FIXTURE_EXTERNAL)
    assert identified.external_identity_ref is not None
    assert identified.external_identity_ref.key_version == "fixture-key-1"
    assert FIXTURE_EXTERNAL.reveal() not in identified.external_identity_ref.value


def test_the_detail_class_defaults_to_none_and_is_a_closed_enumeration() -> None:
    """Free text is where a phone number or a signature fragment would eventually appear."""
    assert _event().detail_class is DetailClass.NONE
    with pytest.raises(ValidationError):
        _event(detail_class="SOMETHING_DESCRIPTIVE")
    assert len(DetailClass) == 16, "a new class is a decision, not an addition"


def test_the_detail_class_is_on_the_event_and_never_on_a_response() -> None:
    """The disclosure boundary, asserted from both sides."""
    assert "detail_class" in ChannelAuditEvent.model_fields
    refusal = refusal_from_violation(
        ChannelViolation(ChannelReasonCode.CHANNEL_IDENTITY_UNMAPPED, "developer-facing detail"),
        ChannelStage.IDENTIFIED,
        DetailClass.BINDING_REVOKED,
    )
    assert isinstance(refusal, ChannelRefusal)
    assert refusal.detail_class is DetailClass.BINDING_REVOKED
    assert "BINDING_REVOKED" not in refusal.sender_text()
    assert "developer-facing detail" not in refusal.sender_text()


def test_the_six_stages_are_closed_and_declaration_order_is_the_sequence() -> None:
    assert tuple(ChannelStage) == CHANNEL_STAGE_ORDER
    assert len(CHANNEL_STAGE_ORDER) == 6
    assert CHANNEL_STAGE_ORDER[0] is ChannelStage.RECEIVED
    assert CHANNEL_STAGE_ORDER[-1] is ChannelStage.DELIVERED


def test_the_event_carries_no_timestamp_of_its_own() -> None:
    """`R-5`: ordering is the stage enum, correlation is the correlation id. Not wall time."""
    for field in ChannelAuditEvent.model_fields:
        assert "time" not in field and "_at" not in field, f"{field} looks like a clock read"


def test_the_governing_versions_are_absent_while_their_records_are_undeclared() -> None:
    """`D-26` and `D-28` undeclared: ``None`` is the honest value, not a fabricated version."""
    event = _event()
    assert event.policy_version is None
    assert event.capability_version is None
