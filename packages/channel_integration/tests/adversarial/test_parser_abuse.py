"""T142 — abusive payloads are refused structurally, before anything expensive.

The parse step decides **nothing about content**. Its job is to establish that what arrived is a
canonical request at all, and to do so before verification, identity, normalisation or any governed
read. So every abuse below must produce a refusal at the `RECEIVED` stage, naming no governed limit
— because at that point nothing about the sender is known and disclosing a bound would answer a
question an anonymous caller cannot ask.

Five abuses:

* **oversized** — beyond the structural ceiling;
* **deeply nested** — JSON that costs a recursive parser its stack;
* **doubly encoded** — a JSON string containing JSON, which a twice-decoding parser unwraps;
* **compressed** — bytes that are not text at all, plus a `content-encoding` claim;
* **content-type mismatch** — a form or XML body announced as JSON, and JSON announced as something
  else.

The instrument is the **stage**, not just the code: a refusal that arrived at `VERIFIED` would mean
the abusive payload had already been through verification, and the ceiling exists so it is not.
"""

from __future__ import annotations

import gzip
import json

import pytest

from channel_integration.contracts.audit import ChannelStage
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.envelope import ChannelEnvelope
from channel_integration.contracts.kinds import MessageKind
from channel_integration.contracts.raw import RawChannelRequest
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

#: A small, **valid** JSON object with undeclared fields. Deliberately not in `_ABUSES`: it parses
#: cleanly, so it is not a parse abuse, and it is refused later at `VERIFIED` by the shape check —
#: which is the correct ordering and is asserted separately below. The first version of this file
#: put it here and the stage assertion caught the miscategorisation.
_NESTED_BUT_VALID = json.dumps({"a": {"b": {"c": {"d": {"e": {}}}}}}).encode()

#: Every abusive body, built rather than pasted so the sizes and depths are visible.
_ABUSES: dict[str, bytes] = {
    "oversized": b'{"text":"' + b"a" * 200_000 + b'"}',
    "deeply nested": b"[" * 2_000 + b"]" * 2_000,
    "doubly encoded": json.dumps(json.dumps(wire_payload())).encode(),
    "compressed": gzip.compress(json.dumps(wire_payload()).encode()),
    "form encoded": b"tenant=tenant-a&text=oi",
    "xml": b"<request><tenant>tenant-a</tenant><text>oi</text></request>",
    "null bytes": b'{"text":"oi\x00\x00"}',
    "bare array": b"[]",
    "bare string": b'"oi"',
    "bare number": b"42",
    "truncated": json.dumps(wire_payload()).encode()[:-5],
    "empty": b"",
}


def _refuse(body: bytes, headers: tuple[tuple[str, str], ...] | None = None) -> ChannelRefusal:
    raw = RawChannelRequest(
        channel=_CHANNEL,
        body=body,
        headers=headers if headers is not None else (("content-type", "application/json"),),
        received_at=AT,
    )
    resolver = CountingIdentityResolver(active_binding(channel=_CHANNEL))
    pseudonymiser = CountingPseudonymiser()
    outcome = convert(
        raw,
        descriptor=descriptor_for(_CHANNEL),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(_CHANNEL),
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=resolver,
        pseudonymiser=pseudonymiser,
        at=AT,
    )
    assert isinstance(outcome, ChannelRefusal), f"an abusive payload was accepted: {body[:40]!r}"
    #: Zero cost surfaces on every refusal here, whatever stage it reached. A shape refusal at
    #: `VERIFIED` still precedes identity resolution: the eight-step ordering puts shape before
    #: identity precisely so a malformed payload never costs a registry read.
    assert resolver.calls == 0, "an abusive payload reached the identity registry"
    assert pseudonymiser.calls == 0, "an abusive payload caused a derivation"
    return outcome


@pytest.mark.parametrize("name", sorted(_ABUSES))
def test_every_abusive_payload_refuses_at_received(name: str) -> None:
    """One stage, one namespace, and no governed limit named.

    The stage assertion is the load-bearing one: `RECEIVED` means the refusal happened before
    verification, so the ceiling protected the expensive steps rather than being applied after them.
    """
    refusal = _refuse(_ABUSES[name])
    assert refusal.stage is ChannelStage.RECEIVED, f"{name} refused at {refusal.stage}"
    assert refusal.code in {
        ChannelReasonCode.CHANNEL_PAYLOAD_MALFORMED,
        ChannelReasonCode.CHANNEL_PAYLOAD_EXCEEDS_STRUCTURAL_LIMIT,
    }


def test_the_oversized_refusal_names_no_number() -> None:
    """A structural ceiling is not a governed bound, and it must not disclose one.

    An anonymous caller learning the exact ceiling learns how to sit just under it. The refusal says
    the payload exceeded a structural limit and stops there.
    """
    refusal = _refuse(_ABUSES["oversized"])
    assert refusal.code is ChannelReasonCode.CHANNEL_PAYLOAD_EXCEEDS_STRUCTURAL_LIMIT
    serialised = refusal.model_dump_json()
    for digits in ("200000", "65536", "32768", "16384", "8192", "4096"):
        assert digits not in serialised, f"the refusal discloses {digits}"


def test_a_deeply_nested_payload_does_not_exhaust_the_stack() -> None:
    """Two thousand levels, and the process survives.

    A `RecursionError` escaping would be a crash rather than a refusal, and a crash is a denial of
    service reachable by an unauthenticated stranger — the cheapest attack there is.
    """
    refusal = _refuse(_ABUSES["deeply nested"])
    assert refusal.stage is ChannelStage.RECEIVED


def test_a_doubly_encoded_payload_is_not_unwrapped_twice() -> None:
    """A JSON string containing JSON is a string, not a request.

    A parser that decoded until it found an object would accept an attacker's inner payload while
    the signature covered the outer one.
    """
    refusal = _refuse(_ABUSES["doubly encoded"])
    assert refusal.code is ChannelReasonCode.CHANNEL_PAYLOAD_MALFORMED


@pytest.mark.parametrize(
    "content_type",
    [
        "application/x-www-form-urlencoded",
        "text/xml",
        "text/plain",
        "application/json; charset=utf-16",
        "",
    ],
)
def test_a_content_type_that_is_not_json_refuses_rather_than_switching_parsers(
    content_type: str,
) -> None:
    """Measured: an unexpected content type **refuses**, at `RECEIVED`, with no parser switch.

    The first version of this test asserted the opposite — that the claim is ignored and a valid
    JSON body converts regardless — and it failed for four of the five claims. The measured
    behaviour is the stricter one and the better one: a boundary that switched parsers on the header
    would let the sender choose the parser, and choosing the parser is most of choosing the outcome.

    So what is asserted is that no claim causes a *different reading* of the body. Either the claim
    is the declared JSON type and the body is parsed as JSON, or the request is refused. There is no
    third behaviour, and that is what makes the header unusable as a lever.
    """
    valid = json.dumps(wire_payload()).encode()
    signed = signed_request(_CHANNEL, body=valid)
    raw = signed.model_copy(
        update={
            "headers": tuple(
                (name, content_type if name == "content-type" else value)
                for name, value in signed.headers
            )
        }
    )
    outcome = convert(
        raw,
        descriptor=descriptor_for(_CHANNEL),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(_CHANNEL),
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=CountingIdentityResolver(active_binding(channel=_CHANNEL)),
        pseudonymiser=CountingPseudonymiser(),
        at=AT,
    )
    assert isinstance(outcome, ChannelRefusal), (
        f"a content-type claim of {content_type!r} was accepted; if the type is now supported this "
        "case must move to the accepted set rather than be deleted"
    )
    assert outcome.stage is ChannelStage.RECEIVED
    assert outcome.code is ChannelReasonCode.CHANNEL_PAYLOAD_MALFORMED


@pytest.mark.parametrize("content_type", ["application/json", "application/json; charset=utf-8"])
def test_the_declared_json_type_is_accepted_with_or_without_a_charset(content_type: str) -> None:
    """The other side: the supported claims are supported, so the refusals above are specific.

    Without this, a boundary that refused **every** content type would satisfy the previous test
    while accepting nothing at all.
    """
    valid = json.dumps(wire_payload()).encode()
    signed = signed_request(_CHANNEL, body=valid)
    raw = signed.model_copy(
        update={
            "headers": tuple(
                (name, content_type if name == "content-type" else value)
                for name, value in signed.headers
            )
        }
    )
    outcome = convert(
        raw,
        descriptor=descriptor_for(_CHANNEL),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(_CHANNEL),
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=CountingIdentityResolver(active_binding(channel=_CHANNEL)),
        pseudonymiser=CountingPseudonymiser(),
        at=AT,
    )
    assert isinstance(outcome, ChannelEnvelope)


def test_a_valid_but_undeclared_shape_refuses_after_verification_not_before() -> None:
    """The ordering, asserted on the one case that reaches it.

    A small valid JSON object with undeclared fields parses cleanly, so it passes `RECEIVED` and is
    refused by the shape check at `VERIFIED`. That is the declared order — authenticity first, then
    shape — and a refusal at `RECEIVED` here would mean the shape check had moved before
    verification, which is how an unauthenticated caller gets their payload inspected.
    """
    #: Signed, unlike the `_ABUSES` cases. Those are refused before verification and so need no
    #: valid signature; this one has to **pass** verification to reach the shape check at all, which
    #: is the ordering being asserted. The first version reused the unsigned helper and refused at
    #: `CHANNEL_SIGNATURE_INVALID`, proving nothing about shape.
    signed = signed_request(_CHANNEL, body=_NESTED_BUT_VALID)
    resolver = CountingIdentityResolver(active_binding(channel=_CHANNEL))
    pseudonymiser = CountingPseudonymiser()
    outcome = convert(
        signed,
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
    refusal = outcome
    assert resolver.calls == 0, "a shape refusal reached the identity registry"
    assert pseudonymiser.calls == 0
    assert refusal.stage is ChannelStage.VERIFIED
    assert refusal.code in {
        ChannelReasonCode.CHANNEL_ENVELOPE_FIELD_UNKNOWN,
        ChannelReasonCode.CHANNEL_ENVELOPE_INCOMPLETE,
    }


def test_a_compressed_body_is_not_decompressed() -> None:
    """`content-encoding` is a transport concern, and this core is not the transport.

    Decompressing here would mean verifying a signature over bytes the sender did not send, and it
    would hand an unauthenticated caller a decompression bomb.
    """
    refusal = _refuse(
        _ABUSES["compressed"],
        headers=(("content-type", "application/json"), ("content-encoding", "gzip")),
    )
    assert refusal.stage is ChannelStage.RECEIVED
    assert refusal.code is ChannelReasonCode.CHANNEL_PAYLOAD_MALFORMED


def test_a_valid_body_still_converts_so_the_refusals_above_mean_something() -> None:
    """Anti-vacuity: a parser that refused everything would satisfy every case above."""
    outcome = convert(
        signed_request(_CHANNEL, payload=wire_payload()),
        descriptor=descriptor_for(_CHANNEL),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(_CHANNEL),
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=CountingIdentityResolver(active_binding(channel=_CHANNEL)),
        pseudonymiser=CountingPseudonymiser(),
        at=AT,
    )
    assert isinstance(outcome, ChannelEnvelope)
