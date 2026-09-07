"""T139 — nobody becomes the provider, and no machine message becomes a user's question.

Three impersonations, and they are different in kind:

* **claiming to be the provider** — headers that assert verification already happened, a
  provider-looking user agent, a source-ip header. This feature verifies in its own core and trusts
  no transport claim, so all of it is inert.
* **a bot message presented as a user message** — one the platform itself produced. Answering it
  would let a loop form: our answer arrives as a new question, which is answered, and so on.
* **a webhook retry presented as a new user message** — the provider redelivering, which must be
  recognised as the same message rather than answered twice.

The third is where the honest limit sits, and this suite states it: recognition is by provider
message id inside a **process-local** window. Two processes do not share it, and `T083` refuses a
multi-instance configuration rather than implying they do.
"""

from __future__ import annotations

import json

import pytest

from channel_integration.contracts.delivery import DeliveryOutcome
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.envelope import ChannelEnvelope
from channel_integration.contracts.kinds import MessageKind
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.contracts.refusal import ChannelRefusal
from channel_integration.idempotency.window import IdempotencyWindow
from channel_integration.inbound.convert import convert

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
    FIXTURE_PRINCIPAL,
    FIXTURE_TENANT,
    CountingIdentityResolver,
    CountingPseudonymiser,
    active_binding,
)

pytestmark = pytest.mark.adversarial

_CHANNEL = ChannelId.SLACK

#: Headers an attacker would add to look official, or to look already-verified. Each is a real
#: header name from some deployment somewhere, which is what makes them tempting to honour.
_IMPERSONATION_HEADERS = (
    ("x-verified", "true"),
    ("x-signature-verified", "yes"),
    ("x-forwarded-for", "127.0.0.1"),
    ("user-agent", "Slackbot 1.0 (+https://api.slack.com/robots)"),
    ("x-authenticated-principal", "principal-ref-a"),
    ("x-internal-request", "true"),
)


def _convert(
    payload: dict[str, object] | None = None,
    extra_headers: tuple[tuple[str, str], ...] = (),
    material: object = FIXTURE_MATERIAL,
) -> ChannelEnvelope | ChannelRefusal:
    raw = signed_request(_CHANNEL, body=json.dumps(payload or wire_payload()).encode())
    if extra_headers:
        raw = raw.model_copy(update={"headers": (*raw.headers, *extra_headers)})
    return convert(
        raw,
        descriptor=descriptor_for(_CHANNEL),
        material=material,  # pyright: ignore[reportArgumentType]
        bounds=bounds_for(_CHANNEL),
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=CountingIdentityResolver(active_binding(channel=_CHANNEL)),
        pseudonymiser=CountingPseudonymiser(),
        at=AT,
    )


@pytest.mark.parametrize("header", _IMPERSONATION_HEADERS, ids=lambda header: header[0])
def test_a_header_asserting_verification_changes_nothing_when_material_is_absent(
    header: tuple[str, str],
) -> None:
    """The sharpest form: no key material, plus a header claiming verification already happened.

    With no material this feature cannot verify, so it refuses. A boundary that honoured the header
    would accept an unauthenticated request on the strength of the request's own claim about itself.
    """
    outcome = _convert(extra_headers=(header,), material=None)
    assert isinstance(outcome, ChannelRefusal)
    assert outcome.code is ChannelReasonCode.CHANNEL_VERIFICATION_UNAVAILABLE


@pytest.mark.parametrize("header", _IMPERSONATION_HEADERS, ids=lambda header: header[0])
def test_an_impersonation_header_changes_nothing_at_all(header: tuple[str, str]) -> None:
    """Inertness asserted as a **difference**, which is the only form that actually holds.

    The first version asserted that the header's value appears nowhere in the envelope, and it
    failed on `x-authenticated-principal: principal-ref-a` — because that value is the principal the
    binding legitimately resolves. Absence of a string cannot distinguish "the header was honoured"
    from "the system reached the same value on its own".

    A differential can: convert the same request with and without the header and compare the whole
    envelope. Byte-identical means the header contributed nothing, whatever it happened to say.
    """
    with_header = _convert(extra_headers=(header,))
    without = _convert()
    assert isinstance(with_header, ChannelEnvelope) and isinstance(without, ChannelEnvelope)
    assert with_header.model_dump_json() == without.model_dump_json(), (
        f"the header {header[0]} changed the envelope, so a transport claim reached the canonical "
        "message"
    )


def test_a_header_naming_a_principal_does_not_become_the_principal() -> None:
    """Identity comes from the resolved binding, never from what the request says it is.

    The header even names the *correct* principal, which is the version that would slip past a check
    looking for something implausible.
    """
    outcome = _convert(extra_headers=(("x-authenticated-principal", str(FIXTURE_PRINCIPAL)),))
    assert isinstance(outcome, ChannelEnvelope)
    assert outcome.principal_ref == FIXTURE_PRINCIPAL, "identity must come from the binding"
    assert outcome.tenant == FIXTURE_TENANT


@pytest.mark.parametrize("kind", [kind for kind in MessageKind if kind is not MessageKind.TEXT])
def test_a_non_text_message_is_refused_naming_the_kind(kind: MessageKind) -> None:
    """A bot card, an attachment, a button press — none of them is a question.

    The refusal names the kind so an operator can see what arrived, and the kind is what the caller
    declared rather than something sniffed from the payload.
    """
    raw = signed_request(_CHANNEL, payload=wire_payload())
    outcome = convert(
        raw,
        descriptor=descriptor_for(_CHANNEL),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(_CHANNEL),
        kind=kind,
        external=FIXTURE_EXTERNAL,
        resolver=CountingIdentityResolver(active_binding(channel=_CHANNEL)),
        pseudonymiser=CountingPseudonymiser(),
        at=AT,
    )
    assert isinstance(outcome, ChannelRefusal)
    assert outcome.code is ChannelReasonCode.CHANNEL_MESSAGE_KIND_UNSUPPORTED


def test_a_webhook_retry_is_recognised_as_the_same_message() -> None:
    """The provider redelivering must not become a second question.

    Recognition is by the provider's message id, which is what a retry keeps and a new message
    changes. Two conversions produce two envelopes — conversion is a pure function and does not
    remember — and the window is what recognises the second as a duplicate.
    """
    first = _convert()
    second = _convert()
    assert isinstance(first, ChannelEnvelope) and isinstance(second, ChannelEnvelope)
    assert first.message_id == second.message_id

    window = IdempotencyWindow()
    assert window.check(_CHANNEL, first.message_id, AT).is_duplicate is False
    window.remember(
        _CHANNEL,
        first.message_id,
        FIXTURE_TENANT,
        FIXTURE_PRINCIPAL,
        DeliveryOutcome.DELIVERED,
        bounds_for(_CHANNEL),
        AT,
    )
    decision = window.check(_CHANNEL, second.message_id, AT)
    assert decision.is_duplicate is True
    assert decision.first_outcome is DeliveryOutcome.DELIVERED


def test_a_retry_seen_by_a_second_process_is_not_recognised_and_that_is_declared() -> None:
    """The limit, asserted so it cannot be mistaken for a guarantee.

    A second window is a second process. It has never seen the message, so it does not suppress it.
    `T083` refuses a multi-instance configuration for exactly this reason, and a test that pretended
    otherwise would be asserting a distributed claim this feature does not make.
    """
    envelope = _convert()
    assert isinstance(envelope, ChannelEnvelope)

    first_process, second_process = IdempotencyWindow(), IdempotencyWindow()
    first_process.remember(
        _CHANNEL,
        envelope.message_id,
        FIXTURE_TENANT,
        FIXTURE_PRINCIPAL,
        DeliveryOutcome.DELIVERED,
        bounds_for(_CHANNEL),
        AT,
    )
    assert first_process.check(_CHANNEL, envelope.message_id, AT).is_duplicate is True
    assert second_process.check(_CHANNEL, envelope.message_id, AT).is_duplicate is False


def test_a_new_message_id_is_not_suppressed_by_a_previous_one() -> None:
    """The other direction: suppression must not swallow a genuine second question.

    A boundary that keyed on the principal or the conversation rather than the message would answer
    a user once and then go quiet, which is a worse failure than a duplicate answer.
    """
    first = _convert(wire_payload(message_id="provider-message-1"))
    second = _convert(wire_payload(message_id="provider-message-2"))
    assert isinstance(first, ChannelEnvelope) and isinstance(second, ChannelEnvelope)

    window = IdempotencyWindow()
    window.remember(
        _CHANNEL,
        first.message_id,
        FIXTURE_TENANT,
        FIXTURE_PRINCIPAL,
        DeliveryOutcome.DELIVERED,
        bounds_for(_CHANNEL),
        AT,
    )
    assert window.check(_CHANNEL, second.message_id, AT).is_duplicate is False
