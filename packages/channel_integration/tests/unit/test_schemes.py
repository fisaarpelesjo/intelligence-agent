"""The four verification schemes — T058 (FR-010, FR-012; SC-003, SC-004).

Five failure modes per HMAC scheme, all reporting the **same** governed code and each carrying its
own operator-facing detail class: absent, malformed, mismatched, retired material, and — through
the descriptor — valid for another channel.

The positive case matters as much as the negatives: a scheme that refused everything would pass a
suite of refusals and verify nothing.
"""

from __future__ import annotations

import pytest

from channel_integration.contracts.audit import DetailClass
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.inbound.schemes import VerificationMaterial
from channel_integration.inbound.schemes.generic import GenericWebhookScheme
from channel_integration.inbound.schemes.slack import SlackScheme
from channel_integration.inbound.schemes.telegram import TelegramScheme
from channel_integration.inbound.schemes.whatsapp import WhatsAppScheme
from channel_integration.inbound.verify import SCHEMES, VerificationFailure, scheme_for

from ..fixtures.channels import AT, FIXTURE_MATERIAL, descriptor_for, signed_request

pytestmark = pytest.mark.unit

_CHANNELS = list(ChannelId)


@pytest.mark.parametrize("channel", _CHANNELS)
def test_a_correctly_signed_request_verifies(channel: ChannelId) -> None:
    """The positive case, per channel. Without it every negative below is vacuous."""
    raw = signed_request(channel)
    scheme = SCHEMES[descriptor_for(channel).verification_scheme]
    assert scheme.verify(raw.body, raw.headers, FIXTURE_MATERIAL).ok


@pytest.mark.parametrize("channel", _CHANNELS)
def test_an_absent_signature_refuses(channel: ChannelId) -> None:
    raw = signed_request(channel)
    scheme = SCHEMES[descriptor_for(channel).verification_scheme]
    stripped = tuple(
        (name, value)
        for name, value in raw.headers
        if "signature" not in name.lower() and "secret-token" not in name.lower()
    )
    outcome = scheme.verify(raw.body, stripped, FIXTURE_MATERIAL)
    assert not outcome.ok
    assert outcome.detail is DetailClass.SIGNATURE_ABSENT


@pytest.mark.parametrize("channel", _CHANNELS)
def test_a_body_altered_after_signing_refuses(channel: ChannelId) -> None:
    """Integrity, not just authenticity — for the three schemes that bind the body.

    Telegram's token binds nothing, which is why its own module records that limit rather than
    pretending otherwise. Asserted here as the honest difference between the schemes.
    """
    raw = signed_request(channel)
    scheme = SCHEMES[descriptor_for(channel).verification_scheme]
    tampered = raw.body.replace(b"julho", b"agosto")
    assert tampered != raw.body
    outcome = scheme.verify(tampered, raw.headers, FIXTURE_MATERIAL)
    if channel is ChannelId.TELEGRAM:
        assert outcome.ok, "the token scheme binds no body; the limit is recorded, not hidden"
    else:
        assert not outcome.ok
        assert outcome.detail is DetailClass.SIGNATURE_MISMATCH


@pytest.mark.parametrize(
    "channel", [ChannelId.WHATSAPP, ChannelId.SLACK, ChannelId.GENERIC_WEBHOOK]
)
def test_a_malformed_digest_refuses(channel: ChannelId) -> None:
    raw = signed_request(channel)
    scheme = SCHEMES[descriptor_for(channel).verification_scheme]
    mangled = tuple(
        (name, "not-a-hex-digest" if "signature" in name.lower() else value)
        for name, value in raw.headers
    )
    outcome = scheme.verify(raw.body, mangled, FIXTURE_MATERIAL)
    assert not outcome.ok
    assert outcome.detail is DetailClass.SIGNATURE_MALFORMED


@pytest.mark.parametrize("channel", _CHANNELS)
def test_retired_material_refuses_and_says_so_to_the_operator(channel: ChannelId) -> None:
    """A correct signature under a withdrawn key is refused, and named (`FR-074`).

    Accepting it would make a rotation cosmetic.
    """
    retired_key = "fixture-retired-key"
    material = VerificationMaterial(active="fixture-new-key", retired=(retired_key,))
    raw = signed_request(channel, material=VerificationMaterial(active=retired_key, retired=()))
    scheme = SCHEMES[descriptor_for(channel).verification_scheme]
    outcome = scheme.verify(raw.body, raw.headers, material)
    assert not outcome.ok
    assert outcome.detail is DetailClass.SIGNATURE_RETIRED_MATERIAL


def test_a_descriptor_naming_another_channels_scheme_refuses() -> None:
    """ "Valid for a different channel", closed at the descriptor rather than at the digest."""
    crossed = descriptor_for(ChannelId.SLACK).model_copy(
        update={"verification_scheme": WhatsAppScheme.name}
    )
    with pytest.raises(VerificationFailure) as caught:
        scheme_for(crossed)
    assert caught.value.code is ChannelReasonCode.CHANNEL_VERIFICATION_UNAVAILABLE
    assert caught.value.detail_class is DetailClass.SIGNATURE_WRONG_CHANNEL


def test_a_descriptor_naming_no_implemented_scheme_refuses() -> None:
    unknown = descriptor_for(ChannelId.SLACK).model_copy(
        update={"verification_scheme": "does-not-exist"}
    )
    with pytest.raises(VerificationFailure) as caught:
        scheme_for(unknown)
    assert caught.value.code is ChannelReasonCode.CHANNEL_VERIFICATION_UNAVAILABLE


def test_the_scheme_registry_covers_every_channel_exactly_once() -> None:
    assert set(SCHEMES) == {
        WhatsAppScheme.name,
        SlackScheme.name,
        TelegramScheme.name,
        GenericWebhookScheme.name,
    }
    assert len(SCHEMES) == 4


def test_which_schemes_provide_a_signed_timestamp() -> None:
    """Stated as a fact of the scheme, because the replay window depends on it."""
    assert SCHEMES[SlackScheme.name].provides_signed_timestamp is True
    assert SCHEMES[GenericWebhookScheme.name].provides_signed_timestamp is True
    assert SCHEMES[WhatsAppScheme.name].provides_signed_timestamp is False
    assert SCHEMES[TelegramScheme.name].provides_signed_timestamp is False


def test_a_signature_valid_at_one_instant_is_body_bound_not_time_bound() -> None:
    """Slack's basestring binds the timestamp, so re-signing at another instant differs.

    This is what makes the replay window meaningful for that channel: an attacker cannot move a
    captured signature to a fresh timestamp.
    """
    early = signed_request(ChannelId.SLACK, at=AT)
    later = signed_request(ChannelId.SLACK, at=AT.replace(hour=13), body=early.body)
    early_signature = dict(early.headers)["x-slack-signature"]
    later_signature = dict(later.headers)["x-slack-signature"]
    assert early_signature != later_signature
