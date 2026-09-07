"""T140 — an unverifiable stranger learns nothing and costs nothing, at any volume (`FR-025`).

Two properties, and the second is what makes the first worth having.

**Nothing is learned.** A refusal must not differ in a way that answers a question the sender was
not entitled to ask: whether a tenant exists, whether a principal is bound, whether a channel is
enabled, whether a message id was seen before. So the refusals for a stranger are compared **against
each other**, and any field that varies with the probe is a channel of information.

**Nothing is spent.** Zero identity resolutions, zero pseudonym derivations, zero interpretation —
at one request and at a thousand. `T052`'s counted-zero test asserts this for single requests; this
suite asserts it holds under volume, which is the case a flood exploits.

## Timing is asserted narrowly, and deliberately so

`test_verification_timing.py` already asserts that HMAC comparison is constant-time through
`hmac.compare_digest`. This suite does not re-measure wall-clock timing: a timing assertion in a
test suite that shares a machine with a compiler and a linter measures the machine, and a flaky
security test gets muted. What is asserted here is the **structural** property behind it — that the
refusal for a wrong signature carries no more detail than the refusal for an absent one.
"""

from __future__ import annotations

import json

import pytest

from channel_integration.contracts.audit import DetailClass
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.envelope import ChannelEnvelope
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
    wire_payload,
)
from ..fixtures.identity import (
    FIXTURE_EXTERNAL,
    CountingIdentityResolver,
    CountingPseudonymiser,
    active_binding,
)

pytestmark = pytest.mark.adversarial

_CHANNEL = ChannelId.SLACK

#: Probes a stranger would send to find out what exists. Every one is unverifiable — no valid
#: signature — because that is the position an attacker starts from, and the point is that they stay
#: there.
_PROBES = {
    "unknown tenant": wire_payload(tenant="tenant-does-not-exist"),
    "known tenant": wire_payload(tenant="tenant-a"),
    "empty text": wire_payload(text=" "),
    "long text": wire_payload(text="a" * 5_000),
    "repeat message id": wire_payload(message_id="provider-message-1"),
    "fresh message id": wire_payload(message_id="provider-message-probe-2"),
}


class _Unverified:
    """One unverifiable request and everything observable about its refusal."""

    def __init__(self, payload: dict[str, object]) -> None:
        raw = signed_request(_CHANNEL, body=json.dumps(payload).encode())
        # Strip the signature so the request cannot verify, whatever else it carries.
        stripped = raw.model_copy(
            update={
                "headers": tuple(
                    (name, value) for name, value in raw.headers if "signature" not in name.lower()
                )
            }
        )
        resolver = CountingIdentityResolver(active_binding(channel=_CHANNEL))
        pseudonymiser = CountingPseudonymiser()
        self.outcome: ChannelEnvelope | ChannelRefusal = convert(
            stripped,
            descriptor=descriptor_for(_CHANNEL),
            material=FIXTURE_MATERIAL,
            bounds=bounds_for(_CHANNEL),
            kind=MessageKind.TEXT,
            external=FIXTURE_EXTERNAL,
            resolver=resolver,
            pseudonymiser=pseudonymiser,
            at=AT,
        )
        self.resolutions = resolver.calls
        self.derivations = pseudonymiser.calls

    @property
    def refusal(self) -> ChannelRefusal:
        assert isinstance(self.outcome, ChannelRefusal), "an unverifiable request was accepted"
        return self.outcome


@pytest.mark.parametrize("name", sorted(_PROBES))
def test_every_probe_is_refused_and_costs_nothing(name: str) -> None:
    """The counted-zero property, per probe."""
    attempt = _Unverified(_PROBES[name])
    assert attempt.refusal.code is ChannelReasonCode.CHANNEL_SIGNATURE_INVALID
    assert attempt.resolutions == 0, f"{name} caused {attempt.resolutions} registry reads"
    assert attempt.derivations == 0, f"{name} caused {attempt.derivations} derivations"


def test_no_two_probes_produce_distinguishable_refusals() -> None:
    """The enumeration property: the refusal is the same whatever the probe asked about.

    Compared as serialised refusals, so a field this test does not know about is covered too. If a
    future field legitimately varies — a correlation id, say — this fails and the question becomes
    whether that field tells a stranger something, which is a question worth being forced to answer.
    """
    serialised = {
        name: _Unverified(payload).refusal.model_dump_json()
        for name, payload in sorted(_PROBES.items())
    }
    distinct = set(serialised.values())
    assert len(distinct) == 1, (
        "probes produce distinguishable refusals, so a stranger can enumerate by comparing them: "
        f"{serialised}"
    )


def test_a_wrong_signature_and_an_absent_signature_carry_the_same_code() -> None:
    """The same code, and a detail class that distinguishes only the sender's own input.

    The first version of this test demanded byte-identical refusals and failed: the detail classes
    are `SIGNATURE_MISMATCH` and `SIGNATURE_ABSENT`. Measured, that is **not** an information
    channel — the prober chose whether to send a signature, so the distinction tells them something
    they already know. What would be a channel is a refusal that varied with what they were probing
    *for*, and the test above asserts exactly that and finds no variation.

    So the assertion here is the one that holds and still has teeth: one code for both, so neither
    reveals how far into verification the request travelled, and both detail classes belong to the
    closed `DetailClass` set rather than carrying free text.
    """
    raw = signed_request(_CHANNEL, payload=wire_payload())
    wrong = raw.model_copy(
        update={
            "headers": tuple(
                (name, "v0=" + "0" * 64 if "signature" in name.lower() else value)
                for name, value in raw.headers
            )
        }
    )
    absent = raw.model_copy(
        update={
            "headers": tuple(
                (name, value) for name, value in raw.headers if "signature" not in name.lower()
            )
        }
    )

    outcomes: list[ChannelRefusal] = []
    for request in (wrong, absent):
        outcome = convert(
            request,
            descriptor=descriptor_for(_CHANNEL),
            material=FIXTURE_MATERIAL,
            bounds=bounds_for(_CHANNEL),
            kind=MessageKind.TEXT,
            external=FIXTURE_EXTERNAL,
            resolver=CountingIdentityResolver(active_binding(channel=_CHANNEL)),
            pseudonymiser=CountingPseudonymiser(),
            at=AT,
        )
        assert isinstance(outcome, ChannelRefusal)
        outcomes.append(outcome)

    assert outcomes[0].code is outcomes[1].code is ChannelReasonCode.CHANNEL_SIGNATURE_INVALID
    assert outcomes[0].detail_class in DetailClass
    assert outcomes[1].detail_class in DetailClass
    #: The stage must match too: a refusal reaching a later stage for one of them would say how far
    #: the request got, which is a fact about the boundary rather than about the sender's own input.
    assert outcomes[0].stage is outcomes[1].stage


def test_a_flood_of_unverifiable_traffic_costs_nothing_in_total() -> None:
    """Volume changes nothing, which is the property a flood attacks.

    Five hundred unverifiable requests through one resolver and one pseudonymiser: the counters must
    still read zero. A per-request assertion would miss a cache that warmed up, a lazy registry that
    loaded on the tenth call, or a counter that reset.
    """
    resolver = CountingIdentityResolver(active_binding(channel=_CHANNEL))
    pseudonymiser = CountingPseudonymiser()
    codes: set[ChannelReasonCode] = set()

    for index in range(500):
        raw = signed_request(
            _CHANNEL, body=json.dumps(wire_payload(message_id=f"flood-{index}")).encode()
        )
        stripped = raw.model_copy(
            update={
                "headers": tuple(
                    (name, value) for name, value in raw.headers if "signature" not in name.lower()
                )
            }
        )
        outcome = convert(
            stripped,
            descriptor=descriptor_for(_CHANNEL),
            material=FIXTURE_MATERIAL,
            bounds=bounds_for(_CHANNEL),
            kind=MessageKind.TEXT,
            external=FIXTURE_EXTERNAL,
            resolver=resolver,
            pseudonymiser=pseudonymiser,
            at=AT,
        )
        assert isinstance(outcome, ChannelRefusal)
        codes.add(outcome.code)

    assert resolver.calls == 0, f"the flood caused {resolver.calls} registry reads"
    assert pseudonymiser.calls == 0, f"the flood caused {pseudonymiser.calls} derivations"
    assert codes == {ChannelReasonCode.CHANNEL_SIGNATURE_INVALID}, (
        f"the flood produced varying refusals: {codes}"
    )


def test_a_verifiable_request_does_reach_the_registry() -> None:
    """Anti-vacuity for every counter above.

    Without this, a resolver that was never called at all — because conversion refused for an
    unrelated reason — would make every zero above meaningless.
    """
    resolver = CountingIdentityResolver(active_binding(channel=_CHANNEL))
    pseudonymiser = CountingPseudonymiser()
    outcome = convert(
        signed_request(_CHANNEL, payload=wire_payload()),
        descriptor=descriptor_for(_CHANNEL),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(_CHANNEL),
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=resolver,
        pseudonymiser=pseudonymiser,
        at=AT,
    )
    assert isinstance(outcome, ChannelEnvelope)
    assert resolver.calls >= 1, (
        "a verified request never reached the registry, so the zeros mean nothing"
    )
    assert pseudonymiser.calls >= 1
