"""Governed pt-BR wording: coverage, determinism, disclosure — T025 (FR-045; SC-060).

**Presence, coverage and stability only.** Whether the Portuguese is correct stays the
`D-10` / `001:T117` reviewer duty and is never claimed here (`FR-099`). A test that
asserted correctness would read as a claim nobody made.

Three disclosure rules *are* asserted, because they are encoded in the wording itself
rather than left to callers: no message names a governed limit; the signature failure
modes read identically; and an unmapped identity reads the same as a known-but-
unauthorised one.
"""

from __future__ import annotations

import re

import pytest

from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.messages.registry import (
    MessageRegistryMalformed,
    load_registry,
    message_for,
)

pytestmark = pytest.mark.contract


def test_every_code_has_wording_and_there_is_no_orphan() -> None:
    registry = load_registry()
    assert registry.codes() == frozenset(ChannelReasonCode)
    assert registry.language == "pt-BR"
    assert registry.content_version == "unversioned"


def test_wording_is_byte_identical_across_repeats() -> None:
    first = [message_for(code, **_arguments(code)) for code in ChannelReasonCode]
    second = [message_for(code, **_arguments(code)) for code in ChannelReasonCode]
    assert first == second


def _arguments(code: ChannelReasonCode) -> dict[str, str]:
    """The allowlisted arguments each message declares.

    Only two names are allowlisted at all — ``channel`` and ``message_kind`` — which is
    what makes a leak through interpolation structurally impossible rather than merely
    unlikely.
    """
    needs_channel = {
        ChannelReasonCode.CHANNEL_NOT_CONFIGURED,
        ChannelReasonCode.CHANNEL_CREDENTIAL_UNAVAILABLE,
        ChannelReasonCode.CHANNEL_RATE_LIMIT_EXCEEDED,
        ChannelReasonCode.CHANNEL_DELIVERY_FAILED,
        ChannelReasonCode.CHANNEL_DELIVERY_ATTEMPTS_EXHAUSTED,
    }
    if code in needs_channel:
        return {"channel": "WHATSAPP"}
    if code is ChannelReasonCode.CHANNEL_MESSAGE_KIND_UNSUPPORTED:
        return {"message_kind": "AUDIO"}
    return {}


def test_no_message_names_a_governed_limit() -> None:
    """Unlike `003`, this feature never earns the right to name one.

    Its sender is unauthenticated at every step, so a `D-26` number may not appear in
    any refusal (`contracts/inbound-conversion.md` §3). Asserted as the absence of any
    digit sequence, which is the shape a limit would take.
    """
    for code in ChannelReasonCode:
        text = message_for(code, **_arguments(code))
        assert not re.search(r"\d", text), f"{code.value} names a number: {text!r}"


def test_no_message_uses_error_vocabulary() -> None:
    """A governed refusal is a state, not a fault (`FR-045`)."""
    forbidden = ("erro", "exceção", "falha interna", "stack", "trace", "exception")
    for code in ChannelReasonCode:
        text = message_for(code, **_arguments(code)).lower()
        for word in forbidden:
            assert word not in text, f"{code.value} uses error vocabulary: {word}"


def test_the_signature_failure_wording_discloses_no_mode() -> None:
    """One code, one wording: the sender cannot learn which half of the scheme failed."""
    text = message_for(ChannelReasonCode.CHANNEL_SIGNATURE_INVALID).lower()
    for leak in ("ausente", "expirad", "inválida para o canal", "chave", "cabeçalho"):
        assert leak not in text, f"the signature wording discloses {leak!r}"


def test_the_identity_wording_does_not_distinguish_unknown_from_unauthorised() -> None:
    """`FR-020`: the two responses must be indistinguishable to a sender."""
    text = message_for(ChannelReasonCode.CHANNEL_IDENTITY_UNMAPPED).lower()
    for leak in ("revogad", "expirad", "não autorizado", "sem permissão", "bloqueado"):
        assert leak not in text, f"the identity wording discloses {leak!r}"


def test_an_undeclared_argument_is_refused_rather_than_ignored() -> None:
    """A silently dropped argument is how a value ends up in a message with none."""
    with pytest.raises(MessageRegistryMalformed):
        message_for(ChannelReasonCode.CHANNEL_TEXT_NOT_USABLE, question="quantas instalações?")


def test_a_required_argument_may_not_be_omitted() -> None:
    with pytest.raises(MessageRegistryMalformed):
        message_for(ChannelReasonCode.CHANNEL_NOT_CONFIGURED)


def test_no_message_can_interpolate_content() -> None:
    """The allowlist is the mechanism: two names, neither of them content."""
    registry = load_registry()
    assert registry.codes()  # registry loaded, so the allowlist validated at load time
    forbidden = {
        "question",
        "answer",
        "value",
        "signature",
        "token",
        "header",
        "identity",
        "payload",
        "url",
        "limit",
    }
    for name in forbidden:
        with pytest.raises(MessageRegistryMalformed):
            message_for(ChannelReasonCode.CHANNEL_PAYLOAD_MALFORMED, **{name: "x"})
