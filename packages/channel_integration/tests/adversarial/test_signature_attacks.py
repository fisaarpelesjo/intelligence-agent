"""T136 — signature and replay attacks, against what each scheme actually guarantees.

Verification happens in **this** feature's core, over the bytes as they arrived, before any cost
surface. Every case below attacks that placement: an attempt to have the boundary accept something
the signer did not sign, or accept twice what was signed once.

## The four schemes do not guarantee the same things, and this suite says so

The first version of this file asserted one uniform property — tamper the body, get
`CHANNEL_SIGNATURE_INVALID` — and **four cases failed**. They failed because the assertion was
wrong, not the code: the providers' published mechanisms differ, and the scheme modules already
declare the difference through `provides_signed_timestamp` and their own docstrings.

| Channel | Binds the body | Signs a timestamp | What defends against replay |
|---|---|---|---|
| Slack | yes, HMAC over `v0:ts:body` | **yes** | the signature itself, plus the tolerance |
| Generic webhook | yes, HMAC over `ts.body` | **yes** | the signature itself, plus the tolerance |
| WhatsApp | yes, HMAC over the body | **no** | process-local idempotency only |
| Telegram | **no** — a shared secret token header | **no** | process-local idempotency only |

So the properties are asserted **per scheme**, read from the scheme's own declaration rather than
from a list written here. A test that demanded body binding from Telegram would be demanding
something the provider does not offer, and a test that quietly dropped the demand for everyone would
let a real regression through on the two channels that do offer it.

## What this surfaces, and it is not a defect of this feature

On WhatsApp and Telegram a captured request can be presented again and the **conversion** step
cannot tell. The defence that remains is duplicate suppression, which is **process-local** and
claims nothing across processes. That is a real limitation of the deployed shape rather than a bug
in the code, it is recorded in `docs/release/multichannel-spec-revision-notes.md`, and nothing here
invents a policy to close it.

## Every refusal costs nothing

Each case asserts zero identity resolutions and zero pseudonym derivations. A refusal that read the
registry first would let an unauthenticated stranger drive lookups, which is the reason verification
precedes identity.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.envelope import ChannelEnvelope
from channel_integration.contracts.kinds import MessageKind
from channel_integration.contracts.raw import RawChannelRequest
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.contracts.refusal import ChannelRefusal
from channel_integration.inbound.convert import convert
from channel_integration.inbound.schemes import VerificationMaterial
from channel_integration.inbound.verify import scheme_for

from ..fixtures.channels import (
    AT,
    FIXTURE_MATERIAL,
    bounds_for,
    descriptor_for,
    signed_request,
    wire_payload,
)
from ..fixtures.identity import (
    FIXTURE_EXTERNAL,
    CountingIdentityResolver,
    CountingPseudonymiser,
    active_binding,
)

pytestmark = pytest.mark.adversarial

#: Which channels sign a timestamp, read from the **scheme's own declaration**. Restating it here as
#: a literal would let this suite and the schemes drift, and the drift would look like a passing
#: test.
_TIMESTAMP_IN_SIGNATURE = tuple(
    channel
    for channel in ChannelId
    if scheme_for(descriptor_for(channel)).provides_signed_timestamp
)

#: Which channels bind the body cryptographically. Telegram's mechanism is a shared secret token,
#: which authenticates the *sender* and says nothing about the bytes, so body tampering is
#: undetectable there by design of the provider's scheme.
_BODY_BOUND = tuple(channel for channel in ChannelId if channel is not ChannelId.TELEGRAM)


class _Attempt:
    """One conversion attempt with the cost surfaces counted."""

    def __init__(
        self,
        outcome: ChannelEnvelope | ChannelRefusal,
        resolutions: int,
        derivations: int,
    ) -> None:
        self.outcome = outcome
        self.resolutions = resolutions
        self.derivations = derivations

    @property
    def refusal(self) -> ChannelRefusal:
        assert isinstance(self.outcome, ChannelRefusal), (
            f"the attack was accepted: {type(self.outcome).__name__}"
        )
        return self.outcome

    def cost_nothing(self) -> None:
        assert self.resolutions == 0, (
            f"{self.resolutions} identity resolutions on a refused request"
        )
        assert self.derivations == 0, (
            f"{self.derivations} pseudonym derivations on a refused request"
        )


def _attempt(
    raw: RawChannelRequest,
    channel: ChannelId,
    *,
    at: object = None,
    material: VerificationMaterial | None = FIXTURE_MATERIAL,
) -> _Attempt:
    resolver = CountingIdentityResolver(active_binding(channel=channel))
    pseudonymiser = CountingPseudonymiser()
    outcome = convert(
        raw,
        descriptor=descriptor_for(channel),
        material=material,
        bounds=bounds_for(channel),
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=resolver,
        pseudonymiser=pseudonymiser,
        at=at if at is not None else AT,  # pyright: ignore[reportArgumentType]
    )
    return _Attempt(outcome, resolver.calls, pseudonymiser.calls)


@pytest.mark.parametrize("channel", list(ChannelId))
def test_the_fixture_request_converts_so_the_attacks_below_mean_something(
    channel: ChannelId,
) -> None:
    """Anti-vacuity, per channel.

    Without this, a scheme that rejected everything would make every attack below pass while the
    boundary was simply broken.
    """
    attempt = _attempt(signed_request(channel, payload=wire_payload()), channel)
    assert isinstance(attempt.outcome, ChannelEnvelope), (
        f"{channel.value} cannot convert its own fixture request, so its attack cases prove nothing"
    )


@pytest.mark.parametrize("channel", list(_TIMESTAMP_IN_SIGNATURE))
def test_a_replayed_body_with_a_fresh_timestamp_is_refused(channel: ChannelId) -> None:
    """The captured body, presented later with the clock moved forward.

    Asserted only on the channels whose signature covers the timestamp, because on those the
    signature itself is the defence. The others are covered by the tolerance test below, and merging
    the two would credit a scheme with a protection it does not provide.
    """
    original = signed_request(channel, payload=wire_payload(), at=AT)
    later = str(int((AT + timedelta(minutes=30)).timestamp()))
    tampered = original.model_copy(
        update={
            "headers": tuple(
                (name, later if "timestamp" in name.lower() else value)
                for name, value in original.headers
            )
        }
    )
    attempt = _attempt(tampered, channel)
    assert attempt.refusal.code is ChannelReasonCode.CHANNEL_SIGNATURE_INVALID
    attempt.cost_nothing()


@pytest.mark.parametrize("channel", list(_TIMESTAMP_IN_SIGNATURE))
def test_a_replay_outside_the_tolerance_is_refused_where_a_timestamp_is_signed(
    channel: ChannelId,
) -> None:
    """The bounded replay window, on the two channels that can evaluate one.

    A request whose signed timestamp sits outside the governed tolerance is refused, which is what
    makes replay a bounded window rather than an open one.
    """
    bounds = bounds_for(channel)
    late = AT + timedelta(seconds=bounds.replay_tolerance_seconds + 60)
    attempt = _attempt(signed_request(channel, payload=wire_payload(), at=AT), channel, at=late)
    assert attempt.refusal.code in {
        ChannelReasonCode.CHANNEL_TIMESTAMP_OUTSIDE_TOLERANCE,
        ChannelReasonCode.CHANNEL_SIGNATURE_INVALID,
    }
    attempt.cost_nothing()


@pytest.mark.parametrize(
    "channel", [channel for channel in ChannelId if channel not in _TIMESTAMP_IN_SIGNATURE]
)
def test_a_replay_is_not_detectable_at_conversion_where_no_timestamp_is_signed(
    channel: ChannelId,
) -> None:
    """The limitation, asserted rather than left implicit.

    WhatsApp signs the body and no timestamp; Telegram carries a secret token and neither. With no
    signed instant there is nothing to compare a tolerance against, and `received_at` is a transport
    claim this feature is forbidden to trust — an attacker replaying would set it to now anyway.

    So conversion **accepts**, and the only remaining defence is duplicate suppression, which is
    process-local. This test exists so that limitation is visible in the suite and not only in
    prose, and it fails the day a scheme starts signing an instant — at which point it must move to
    the assertion above rather than be deleted.
    """
    bounds = bounds_for(channel)
    late = AT + timedelta(seconds=bounds.replay_tolerance_seconds + 60)
    attempt = _attempt(signed_request(channel, payload=wire_payload(), at=AT), channel, at=late)
    assert isinstance(attempt.outcome, ChannelEnvelope), (
        f"{channel.value} now refuses a late replay, so its scheme evaluates an instant and this "
        "case belongs with the channels that do"
    )
    assert scheme_for(descriptor_for(channel)).provides_signed_timestamp is False


@pytest.mark.parametrize("channel", list(_BODY_BOUND))
def test_a_fresh_body_under_a_replayed_signature_is_refused(channel: ChannelId) -> None:
    """The signature is over the bytes, so different bytes do not verify.

    This is the case a verifier that re-serialised the parsed payload would pass: it would compute
    the signature over its own rendering rather than over what arrived.
    """
    original = signed_request(channel, payload=wire_payload())
    swapped = original.model_copy(update={"body": original.body.replace(b"julho", b"agosto")})
    attempt = _attempt(swapped, channel)
    assert attempt.refusal.code is ChannelReasonCode.CHANNEL_SIGNATURE_INVALID
    attempt.cost_nothing()


@pytest.mark.parametrize("channel", list(_BODY_BOUND))
def test_a_whitespace_only_mutation_is_refused(channel: ChannelId) -> None:
    """One insignificant-looking byte.

    JSON treats the added space as nothing, and a verifier that parsed before verifying would agree
    with the attacker. Byte comparison does not.
    """
    original = signed_request(channel, payload=wire_payload())
    attempt = _attempt(original.model_copy(update={"body": original.body + b" "}), channel)
    assert attempt.refusal.code is ChannelReasonCode.CHANNEL_SIGNATURE_INVALID
    attempt.cost_nothing()


def test_a_payload_signed_for_one_channel_is_refused_by_another() -> None:
    """Cross-channel presentation.

    Each scheme signs a different basestring and reads different headers, so a Slack-signed request
    presented as WhatsApp carries headers the WhatsApp scheme does not recognise. The refusal must
    be a refusal and not an acceptance-by-omission: a scheme that ignored unknown headers and found
    no signature to check would have to refuse, and this asserts it does.
    """
    slack_signed = signed_request(ChannelId.SLACK, payload=wire_payload())
    misdirected = slack_signed.model_copy(update={"channel": ChannelId.WHATSAPP})
    attempt = _attempt(misdirected, ChannelId.WHATSAPP)
    assert attempt.refusal.code in {
        ChannelReasonCode.CHANNEL_SIGNATURE_INVALID,
        ChannelReasonCode.CHANNEL_VERIFICATION_UNAVAILABLE,
    }
    attempt.cost_nothing()


@pytest.mark.parametrize("channel", list(ChannelId))
def test_retired_material_no_longer_verifies(channel: ChannelId) -> None:
    """Rotation that keeps accepting the old key is not rotation.

    The fixture material carries a retired key beside the active one. A request signed with the
    retired key must be refused: accepting it would make a compromised key valid forever, and the
    retired list exists to describe what *was* trusted, not what still is.
    """
    retired = FIXTURE_MATERIAL.retired[0]
    signed_with_retired = signed_request(
        channel,
        payload=wire_payload(),
        material=VerificationMaterial(active=retired, retired=()),
    )
    attempt = _attempt(signed_with_retired, channel)
    assert attempt.refusal.code is ChannelReasonCode.CHANNEL_SIGNATURE_INVALID
    attempt.cost_nothing()


@pytest.mark.parametrize("channel", list(ChannelId))
def test_absent_material_refuses_without_reaching_the_registry(channel: ChannelId) -> None:
    """No material means no verification, and no verification means no processing.

    `D-22` to `D-25` declare no material today, so this is the production path and not an edge case.
    The refusal names the unavailability rather than an invalid signature, because the two are
    different facts and an operator reading a log needs to tell them apart.
    """
    attempt = _attempt(signed_request(channel, payload=wire_payload()), channel, material=None)
    assert attempt.refusal.code is ChannelReasonCode.CHANNEL_VERIFICATION_UNAVAILABLE
    attempt.cost_nothing()


def test_telegram_does_not_detect_body_tampering_and_that_is_its_provider_scheme() -> None:
    """The other half of the same honesty, stated for the one channel that lacks body binding.

    Telegram's published mechanism is a shared secret token header. It authenticates that the sender
    knows the token and says nothing about the bytes, so a modified body is undetectable by the
    scheme. Integrity there rests on transport security, which is `D-30`'s listener and not this
    core.

    Asserted, rather than left as a gap somebody might later mistake for a bug: what protects
    Telegram is the token, and the next test is the one that proves the token is actually checked.
    """
    original = signed_request(ChannelId.TELEGRAM, payload=wire_payload())
    tampered = original.model_copy(update={"body": original.body.replace(b"julho", b"agosto")})
    attempt = _attempt(tampered, ChannelId.TELEGRAM)
    assert isinstance(attempt.outcome, ChannelEnvelope), (
        "Telegram now detects body tampering, so its scheme binds the body and this case must "
        "move to the body-bound group"
    )


def test_the_telegram_token_is_actually_compared() -> None:
    """A scheme whose only check is a token must fail on the wrong token.

    Without this, "Telegram accepts a tampered body" would be indistinguishable from "Telegram
    accepts anything", and the first is a documented provider limitation while the second is a hole.
    """
    wrong = VerificationMaterial(active="fixture-wrong-token", retired=())
    attempt = _attempt(
        signed_request(ChannelId.TELEGRAM, payload=wire_payload(), material=wrong),
        ChannelId.TELEGRAM,
    )
    assert attempt.refusal.code is ChannelReasonCode.CHANNEL_SIGNATURE_INVALID
    attempt.cost_nothing()
