"""Contract hygiene across every canonical model — T017 (FR-002, FR-004, FR-107; SC-006, SC-007).

The claims that make this feature's guarantees structural rather than procedural:

* every canonical model is **frozen** and **closed to extras**;
* **no field can carry authority** — the forbidden-name set is unrepresentable;
* **no field can carry text derived from media** (`FR-108`);
* the envelope's nine identifying fields are all required, and the two dates are
  constructible in isolation with neither derived from the other.

Each is asserted over the **declared field sets**, so a field added in a refactor fails
here rather than being noticed when something leaks.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from channel_integration.contracts import (
    ChannelDescriptor,
    ChannelDestination,
    ChannelEnvelope,
    ChannelId,
    ChannelIdentityBinding,
    ChannelModel,
    ChannelViolation,
    CredentialRecord,
    Degradation,
    PresentationFragment,
    RawChannelRequest,
    RenderedPresentation,
    build,
)
from channel_integration.contracts._base import (
    ConversationRef,
    CorrelationId,
    MessageKey,
    PrincipalRef,
    TenantId,
)
from channel_integration.contracts.audit import ChannelAuditEvent
from channel_integration.contracts.reason_codes import ChannelReasonCode

pytestmark = pytest.mark.contract

_MODELS: tuple[type[ChannelModel], ...] = (
    RawChannelRequest,
    ChannelEnvelope,
    ChannelDescriptor,
    ChannelIdentityBinding,
    RenderedPresentation,
    PresentationFragment,
    Degradation,
    ChannelDestination,
    ChannelAuditEvent,
)

#: Names that must not exist on any canonical model. Each is a way a transport, a
#: caller or a provider could assert something it has no standing to assert
#: (`FR-004`, `FR-107`), or a way media-derived text could enter as a question
#: (`FR-108`), or a way a fixture could be selected at runtime (`FR-072`).
_FORBIDDEN_FIELD_NAMES = frozenset(
    {
        # authority
        "verified",
        "authenticated",
        "trusted",
        "principal",
        "access_tags",
        "scope",
        "role",
        "elevate",
        "authorized",
        # governed limits and versions a caller may not set
        "max_rows",
        "max_bytes",
        "maximum_bytes_billed",
        "threshold",
        "limit",
        "policy_version_override",
        "catalog_release",
        # observations a requester is never authoritative about
        "freshness",
        "coverage",
        "availability",
        "data_revision",
        # language, never detected
        "detected_language",
        "language_hint",
        "locale",
        # media-derived text
        "caption",
        "filename",
        "alt_text",
        "transcript",
        "ocr",
        "description",
        "summary",
        # runtime path selection
        "mode",
        "fixture",
        "debug",
        "sql",
        "query",
        "filter_expression",
    }
)


@pytest.mark.parametrize("model", _MODELS, ids=[m.__name__ for m in _MODELS])
def test_every_model_is_frozen_and_closed(model: type[ChannelModel]) -> None:
    assert model.model_config.get("frozen") is True
    assert model.model_config.get("extra") == "forbid"


@pytest.mark.parametrize("model", _MODELS, ids=[m.__name__ for m in _MODELS])
def test_no_model_declares_a_forbidden_field(model: type[ChannelModel]) -> None:
    declared = set(model.model_fields)
    assert not declared & _FORBIDDEN_FIELD_NAMES, sorted(declared & _FORBIDDEN_FIELD_NAMES)


def _envelope(**overrides: object) -> ChannelEnvelope:
    data: dict[str, object] = {
        "channel": ChannelId.WHATSAPP,
        "tenant": TenantId("tenant-a"),
        "principal_ref": PrincipalRef("principal-ref-a"),
        "language": "pt-BR",
        "reference_date": date(2026, 8, 17),
        "correlation_id": CorrelationId("corr-1"),
        "conversation_id": ConversationRef("conv-1"),
        "message_id": MessageKey("msg-1"),
        "text": "quantas instalações tivemos na Google Play em julho?",
    }
    data.update(overrides)
    # Through `build`, deliberately: pydantic wraps a validator's exception inside a
    # ValidationError, and `build` is what re-raises the governed `ChannelViolation` so
    # a caller can read the reason code instead of parsing a message.
    return build(ChannelEnvelope, ChannelReasonCode.CHANNEL_ENVELOPE_INCOMPLETE, **data)


def test_the_envelope_declares_exactly_the_nine_fields_plus_text() -> None:
    assert set(ChannelEnvelope.model_fields) == {
        "channel",
        "tenant",
        "principal_ref",
        "language",
        "reference_date",
        "as_of",
        "correlation_id",
        "conversation_id",
        "message_id",
        "text",
    }


@pytest.mark.parametrize(
    "absent",
    [
        "channel",
        "tenant",
        "principal_ref",
        "language",
        "reference_date",
        "correlation_id",
        "conversation_id",
        "message_id",
        "text",
    ],
)
def test_every_envelope_field_except_the_as_of_pin_is_required(absent: str) -> None:
    data = {
        "channel": ChannelId.WHATSAPP,
        "tenant": TenantId("tenant-a"),
        "principal_ref": PrincipalRef("principal-ref-a"),
        "language": "pt-BR",
        "reference_date": date(2026, 8, 17),
        "correlation_id": CorrelationId("corr-1"),
        "conversation_id": ConversationRef("conv-1"),
        "message_id": MessageKey("msg-1"),
        "text": "quantas instalações?",
    }
    del data[absent]
    with pytest.raises(ChannelViolation) as caught:
        build(ChannelEnvelope, ChannelReasonCode.CHANNEL_ENVELOPE_INCOMPLETE, **data)
    assert caught.value.code is ChannelReasonCode.CHANNEL_ENVELOPE_INCOMPLETE


def test_the_two_dates_are_independent_and_neither_is_derived() -> None:
    """`FR-005`: each constructible in isolation, no derivation in either direction.

    Structural rather than behavioural: the contract has no code that computes either
    from the other, so the proof is that an envelope with only a reference date leaves
    the pin absent, and one carrying both keeps both exactly as supplied.
    """
    without_pin = _envelope()
    assert without_pin.as_of is None, "an omitted pin is not filled from the reference date"

    with_pin = _envelope(as_of=date(2026, 7, 1))
    assert with_pin.reference_date == date(2026, 8, 17), "the pin does not move the reference date"
    assert with_pin.as_of == date(2026, 7, 1)


def test_an_unknown_envelope_field_is_refused_because_it_does_not_exist() -> None:
    with pytest.raises(ChannelViolation) as caught:
        build(
            ChannelEnvelope,
            ChannelReasonCode.CHANNEL_ENVELOPE_FIELD_UNKNOWN,
            **{
                "channel": ChannelId.WHATSAPP,
                "tenant": TenantId("tenant-a"),
                "principal_ref": PrincipalRef("principal-ref-a"),
                "language": "pt-BR",
                "reference_date": date(2026, 8, 17),
                "correlation_id": CorrelationId("corr-1"),
                "conversation_id": ConversationRef("conv-1"),
                "message_id": MessageKey("msg-1"),
                "text": "quantas instalações?",
                "access_tags": ["admin"],
            },
        )
    assert caught.value.code is ChannelReasonCode.CHANNEL_ENVELOPE_FIELD_UNKNOWN


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "!!!",
        "pergunta" + chr(0x202E) + "com override",
        "pergunta" + chr(0x200B) + "com zero width",
        "pergunta" + chr(0) + "com nul",
    ],
)
def test_unusable_text_refuses_rather_than_being_repaired(text: str) -> None:
    """Stripping would deliver a question the sender did not ask (`FR-038`)."""
    with pytest.raises(ChannelViolation) as caught:
        _envelope(text=text)
    assert caught.value.code is ChannelReasonCode.CHANNEL_TEXT_NOT_USABLE


def test_the_raw_request_carries_bytes_and_a_supplied_instant() -> None:
    request = RawChannelRequest(
        channel=ChannelId.SLACK,
        body=b'{"text":"ok"}',
        headers=(("x-slack-signature", "v0=deadbeef"),),
        received_at=datetime(2026, 8, 17, 12, 0, tzinfo=UTC),
    )
    assert isinstance(request.body, bytes), "verification runs over bytes, never a parse"
    assert request.received_at.tzinfo is UTC


def test_a_repeated_header_name_refuses_rather_than_choosing_one() -> None:
    """Providers disagree about first-wins versus last-wins; refusing removes the
    ambiguity instead of letting authenticity depend on a parser's choice."""
    with pytest.raises(ChannelViolation) as caught:
        build(
            RawChannelRequest,
            ChannelReasonCode.CHANNEL_PAYLOAD_MALFORMED,
            channel=ChannelId.SLACK,
            body=b"{}",
            headers=(("x-signature", "a"), ("X-Signature", "b")),
            received_at=datetime(2026, 8, 17, 12, 0, tzinfo=UTC),
        )
    assert caught.value.code is ChannelReasonCode.CHANNEL_PAYLOAD_MALFORMED


def test_a_descriptor_defaults_to_disabled_and_names_no_policy_value() -> None:
    """`enabled` is derived, and a descriptor carries references rather than values."""
    descriptor = ChannelDescriptor(
        channel=ChannelId.TELEGRAM,
        verification_scheme="telegram-secret-token",
        credential_record=CredentialRecord.D_24_TELEGRAM,
    )
    assert descriptor.enabled is False
    assert descriptor.transport_policy_ref is None
    assert descriptor.capability_ref is None


def test_a_presentation_refuses_an_incomplete_fragment_sequence() -> None:
    """A gap is a truncated answer wearing a continuation's clothes (ADR 0022)."""
    with pytest.raises(ChannelViolation) as caught:
        build(
            RenderedPresentation,
            ChannelReasonCode.CHANNEL_RESPONSE_NOT_REPRESENTABLE,
            channel=ChannelId.WHATSAPP,
            fragments=(
                PresentationFragment(index=1, total=3, body="parte um"),
                PresentationFragment(index=3, total=3, body="parte três"),
            ),
            caveat_count=0,
            language="pt-BR",
        )
    assert caught.value.code is ChannelReasonCode.CHANNEL_RESPONSE_NOT_REPRESENTABLE


def test_a_degradation_cannot_record_a_content_change() -> None:
    """Structural only: there is no field in which a content change could live."""
    declared = set(Degradation.model_fields)
    assert declared == {"capability_ref", "disclosure_code"}
