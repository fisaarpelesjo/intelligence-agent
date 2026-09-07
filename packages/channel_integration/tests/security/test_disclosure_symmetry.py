"""Disclosure symmetry — T063 (ADR 0018; FR-021, FR-022; SC-011).

An unmapped stranger and a known-but-revoked user must receive the **same bytes**.

The attack this closes is enumeration. If "unknown identity" and "your access was revoked" differed
in any observable way — different code, different wording, different length, different stage — then
a stranger could walk a phone-number space and learn which numbers belong to the organisation. The
collapse to a single code is what removes that oracle, and the collapse is only real if the
*response* is identical, not merely the code.

So the assertion is over the **sender projection, byte for byte**, across five distinct binding
conditions:

* no binding at all;
* a revoked binding;
* an expired binding;
* two usable bindings (ambiguous);
* a binding that belongs to another channel.

What legitimately differs is ``detail_class``, and that difference is asserted as *present* rather
than tolerated: it is the operator's channel, it never reaches a sender, and if it were equal
everywhere the collapse would have destroyed the operator's ability to diagnose. Two audiences, two
projections, one code.
"""

from __future__ import annotations

import pytest

from channel_integration.contracts.audit import DetailClass
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.identity import BindingStatus
from channel_integration.contracts.kinds import MessageKind
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.contracts.refusal import ChannelRefusal
from channel_integration.inbound.convert import convert

from ..fixtures.channels import (
    AT,
    FIXTURE_MATERIAL,
    bounds_for,
    descriptor_for,
    signed_request,
)
from ..fixtures.identity import (
    FIXTURE_EXTERNAL,
    CountingIdentityResolver,
    CountingPseudonymiser,
    active_binding,
)

pytestmark = pytest.mark.security

_CHANNEL = ChannelId.SLACK

#: The five conditions, named for what an attacker would want to distinguish.
_CONDITIONS: dict[str, CountingIdentityResolver] = {
    "a stranger nobody has ever mapped": CountingIdentityResolver(),
    "a known user whose access was revoked": CountingIdentityResolver(
        active_binding(status=BindingStatus.REVOKED)
    ),
    "a known user whose access expired": CountingIdentityResolver(
        active_binding(status=BindingStatus.EXPIRED)
    ),
    "a user mapped twice": CountingIdentityResolver(active_binding(), active_binding()),
    "a user mapped on another channel": CountingIdentityResolver(
        active_binding(channel=ChannelId.WHATSAPP)
    ),
}


def _refuse(resolver: CountingIdentityResolver) -> ChannelRefusal:
    outcome = convert(
        signed_request(_CHANNEL),
        descriptor=descriptor_for(_CHANNEL),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(_CHANNEL),
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=resolver,
        pseudonymiser=CountingPseudonymiser(),
        at=AT,
    )
    assert isinstance(outcome, ChannelRefusal), "every condition here must refuse"
    return outcome


def test_every_condition_produces_a_byte_identical_sender_response() -> None:
    """`SC-011`: the sender projection is one string, whatever the internal cause."""
    responses = {name: _refuse(resolver).sender_text() for name, resolver in _CONDITIONS.items()}
    distinct = set(responses.values())
    assert len(distinct) == 1, f"the response distinguishes conditions: {responses}"
    text = distinct.pop()
    assert text.strip(), "an empty response would be symmetric and useless"


def test_every_condition_produces_the_same_code_and_the_same_stage() -> None:
    refusals = [_refuse(resolver) for resolver in _CONDITIONS.values()]
    assert {refusal.code for refusal in refusals} == {ChannelReasonCode.CHANNEL_IDENTITY_UNMAPPED}
    assert len({refusal.stage for refusal in refusals}) == 1, (
        "a differing stage would be an oracle carried in the audit-facing field"
    )


def test_the_responses_are_the_same_length_not_merely_the_same_meaning() -> None:
    """Stated separately because length is observable even when wording is not.

    A response padded per condition, or one that interpolated an identifier, would pass a
    "same code" check and still leak through its size.
    """
    lengths = {len(_refuse(resolver).sender_text()) for resolver in _CONDITIONS.values()}
    assert len(lengths) == 1, f"response lengths differ across conditions: {sorted(lengths)}"


def test_no_response_names_the_identity_or_which_condition_occurred() -> None:
    """The wording is governed and generic. An interpolated handle would be the leak itself.

    Note what is **not** forbidden: the governed wording says there is no governed *binding* for
    this sender on this channel, and that sentence is identical for all five conditions. Naming the
    mechanism generically discloses nothing — naming *which* condition, or *who* asked, would.
    """
    text = _refuse(CountingIdentityResolver()).sender_text().lower()
    for fragment in (
        FIXTURE_EXTERNAL.reveal().lower(),
        "revoked",
        "revogad",
        "expirad",
        "expired",
        "ambíg",
        "ambig",
        "duplicad",
        "slack",
    ):
        assert fragment not in text, f"the response discloses {fragment!r}"


def test_the_operator_can_still_tell_the_conditions_apart() -> None:
    """The other half of the collapse. Symmetry for the sender, not blindness for the operator."""
    classes = {name: _refuse(resolver).detail_class for name, resolver in _CONDITIONS.items()}
    assert classes["a stranger nobody has ever mapped"] is DetailClass.BINDING_ABSENT
    assert classes["a known user whose access was revoked"] is DetailClass.BINDING_REVOKED
    assert classes["a known user whose access expired"] is DetailClass.BINDING_EXPIRED
    assert classes["a user mapped twice"] is DetailClass.BINDING_AMBIGUOUS
    assert len(set(classes.values())) >= 4, "the collapse destroyed the operator's diagnosis"


def test_the_detail_class_is_absent_from_the_sender_projection() -> None:
    """Asserted directly, because this is the one field that must not cross the boundary."""
    for resolver in _CONDITIONS.values():
        refusal = _refuse(resolver)
        assert refusal.detail_class.value not in refusal.sender_text()
        assert refusal.detail_class.value.lower() not in refusal.sender_text().lower()


def test_a_signature_failure_is_symmetric_in_the_same_way() -> None:
    """The second deliberate collapse (ADR 0018), asserted with the same instrument."""
    raw = signed_request(_CHANNEL)
    variants = {
        "absent": raw.model_copy(
            update={
                "headers": tuple(
                    (name, value) for name, value in raw.headers if "signature" not in name.lower()
                )
            }
        ),
        "mismatched": raw.model_copy(update={"body": raw.body.replace(b"julho", b"agosto")}),
        "malformed": raw.model_copy(
            update={
                "headers": tuple(
                    (name, "v0=not-hex" if "signature" in name.lower() else value)
                    for name, value in raw.headers
                )
            }
        ),
    }
    responses: dict[str, str] = {}
    classes: set[DetailClass] = set()
    for name, request in variants.items():
        outcome = convert(
            request,
            descriptor=descriptor_for(_CHANNEL),
            material=FIXTURE_MATERIAL,
            bounds=bounds_for(_CHANNEL),
            kind=MessageKind.TEXT,
            external=FIXTURE_EXTERNAL,
            resolver=CountingIdentityResolver(active_binding()),
            pseudonymiser=CountingPseudonymiser(),
            at=AT,
        )
        assert isinstance(outcome, ChannelRefusal)
        responses[name] = outcome.sender_text()
        classes.add(outcome.detail_class)
    assert len(set(responses.values())) == 1, responses
    assert len(classes) >= 2, "the operator cannot tell absent from mismatched"
