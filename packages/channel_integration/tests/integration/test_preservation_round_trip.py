"""T126 [US3] — the whole payload corpus through the composed path, byte-compared on the way out.

`FR-043` to `FR-049`, `SC-014`, `SC-015`, `SC-019`, `SC-020`. The path under test is all of it —
`roundtrip.handle`: envelope, port, render, preserve, deliver — and the bytes compared are the ones
the **delivery port was actually handed**, read back off `RecordingDeliveryPort.calls`.

## What this adds over `tests/contract/test_preservation.py`, which already exists

That file calls `render_answer` and `assert_preserved` directly, on a payload it holds in its hand.
It proves the renderer and the gate agree about a payload nobody transported. This file proves the
same strings survive six further steps — structural parse, signature verification, identity
resolution, envelope construction, the interaction port, and the delivery attempt — and it compares
against what the **transport received**, not against the presentation object `handle` returned,
because "the rendering was correct" and "the correct rendering is what went out" are two claims and
only the second one is a round trip.

Nothing here is parametrised over a literal list of entry names. `CORPUS` is the instrument, the
names are read from it, and a corpus entry added tomorrow is driven the moment it exists rather
than when somebody remembers this file.

## The split is measured, and which side an entry falls on is derived rather than listed

Some corpus entries deliver and at least one withholds. An entry withholds when some claim's
`LocalizedRef` has no resolved string in its wording lookup, which is ADR 0026's withhold
condition — a reference with no resolved string is a pointer, and delivering a pointer to a reader
is the failure the withhold exists to prevent.

The contract test names its one exemption in a literal set; here the predicate is **computed** and
then held against the measurement, so a future entry with an unresolved reference joins the
withholding group by itself, and a renderer that quietly started substituting a fallback string
would fail the prediction instead of passing a thinner test.

## What "byte-compared" means here, exactly

Two comparisons against `outbound.preserve.payload_governed_strings(payload)`, both over the
delivered fragment bodies joined the way the gate joins them:

1. **presence** — every governed string the payload carries occurs in the delivered bytes as the
   exact substring it is. Containment rather than equality, because channel syntax may surround
   content; what it may not do is alter one byte of it.
2. **residue** — strip every governed string, every governed label the capability matrix declares,
   and `preserve.PERMITTED_SEPARATORS`. What survives is text nobody authorised, and it must be
   empty. The separator tuple is **imported** rather than restated: it is closed and small on
   purpose, every addition to it is a character this check stops noticing, and that trade should be
   one edit visible in one place rather than two lists that can disagree.

Replacement runs longest-first, for the reason `preserve.py` records against its own history:
stripping "numero 1" before "numero 12" leaves a stray "2" and reports it as unauthorised content.

## Injecting a capability matrix measures the composition and nothing about readiness

`D-28` is undeclared, so `resolve_capability_matrix` refuses for every channel and the shipped round
trip stops at `RENDERED`. Every node below calls `assert_the_production_resolver_still_refuses`
first, so a fixture rendering can never be read as evidence that a channel works.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from channel_integration.contracts.audit import ChannelStage
from channel_integration.contracts.delivery import DeliveryOutcome
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.kinds import MessageKind
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.outbound.preserve import (
    assert_preserved,
    payload_governed_strings,
    preservation_report,
    strip_structure,
)
from channel_integration.outbound.withhold import WithheldAfterRendering
from channel_integration.roundtrip import RoundTripResult, handle
from tests.fixtures.channels import (
    AT,
    FIXTURE_CAPABILITY,
    FIXTURE_MATERIAL,
    RecordingAuditSink,
    RecordingDeliveryPort,
    assert_the_production_resolver_still_refuses,
    bounds_for,
    descriptor_for,
    fixture_capabilities,
    signed_request,
)
from tests.fixtures.identity import (
    FIXTURE_EXTERNAL,
    CountingIdentityResolver,
    active_binding,
    fixture_principal_context,
    fixture_pseudonymiser,
)
from tests.fixtures.interaction import recording_interaction
from tests.fixtures.payloads import CORPUS, FixturePayload

if TYPE_CHECKING:
    from collections.abc import Mapping

pytestmark = pytest.mark.integration

#: Every channel, because preservation is a property of the (payload, channel) pairing. A corpus
#: driven on one channel would say nothing about the three whose capability entry is the same
#: fixture mapping but whose destination derivation is not.
_CHANNELS = list(ChannelId)

#: The entry the anti-vacuity node corrupts. Named rather than picked at random, so a failure
#: reports which payload was mutilated.
_ALL_FOUR = "all four claim classes"


def _withholds_by_construction(payload: FixturePayload) -> bool:
    """True when some claim points at wording the payload's lookup cannot resolve (ADR 0026).

    Derived from the payload rather than read from a list of exempt names, so the corpus decides
    which group it belongs to and this file cannot drift away from it.
    """
    return any(
        payload.wording.text_for(claim.message.code) is None for claim in payload.answer.claims
    )


_DELIVERS = sorted(name for name in CORPUS if not _withholds_by_construction(CORPUS[name]))
_WITHHOLDS = sorted(name for name in CORPUS if _withholds_by_construction(CORPUS[name]))


def _run(
    name: str, channel: ChannelId
) -> tuple[RoundTripResult, RecordingDeliveryPort, RecordingAuditSink]:
    """Drive one corpus entry through the whole path, with every collaborator injected."""
    fixture = CORPUS[name]
    transport = RecordingDeliveryPort()
    trail = RecordingAuditSink()
    result = handle(
        signed_request(channel),
        descriptor=descriptor_for(channel),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(channel),
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=CountingIdentityResolver(active_binding(channel=channel)),
        pseudonymiser=fixture_pseudonymiser(),
        at=AT,
        principal=fixture_principal_context(),
        wording=fixture.wording,
        port=recording_interaction(fixture.answer),
        capabilities=fixture_capabilities,
        delivery=transport,
        sink=trail,
    )
    return result, transport, trail


def _delivered(transport: RecordingDeliveryPort) -> str:
    """The fragment bodies the transport was handed, joined the way the gate joins them."""
    assert transport.calls, "nothing was transmitted, so there are no delivered bytes to compare"
    _, fragments = transport.calls[0]
    return "\n\n".join(fragments)


def _governed_labels() -> tuple[str, ...]:
    """The governed claim-class labels the fixture capability entry declares."""
    declared = FIXTURE_CAPABILITY["claim_class_labels"]
    assert isinstance(declared, dict), "the capability entry declares no claim_class_labels"
    labels = cast("Mapping[str, object]", declared)
    return tuple(value for value in labels.values() if isinstance(value, str))


def _residue(delivered: str, payload: FixturePayload) -> str:
    """What survives stripping governed content and the permitted separators. Must be empty."""
    strings = {*payload_governed_strings(payload), *_governed_labels()}
    residue = delivered
    for string in sorted(strings, key=len, reverse=True):
        residue = residue.replace(string, "")
    residue = strip_structure(residue)
    return residue


def test_the_corpus_is_not_empty_and_the_measured_split_matches_the_derived_one() -> None:
    """The instrument, checked before anything is measured with it.

    Three properties, and each closes a way this file could pass while testing nothing: an empty
    corpus would make every parametrised node below collect zero cases; an empty group would do the
    same to half of them; and a derived predicate that disagreed with what the composed path
    actually does would make the two groups arbitrary rather than meaningful.
    """
    assert CORPUS, "an empty corpus would make every parametrised node below collect nothing"
    assert _DELIVERS, "no entry delivers, so the preservation nodes would collect nothing"
    assert _WITHHOLDS, "no entry withholds, so the withhold node would collect nothing"
    assert sorted({*_DELIVERS, *_WITHHOLDS}) == sorted(CORPUS)

    assert_the_production_resolver_still_refuses(ChannelId.SLACK)
    for name in sorted(CORPUS):
        result, transport, _ = _run(name, ChannelId.SLACK)
        withheld = result.refusal is not None
        assert withheld == (name in _WITHHOLDS), (
            f"{name} was predicted from its own wording lookup to land in the other group, and "
            f"the composed path disagreed"
        )
        assert (transport.sends == 0) == withheld


@pytest.mark.parametrize("channel", _CHANNELS)
@pytest.mark.parametrize("name", _DELIVERS)
def test_every_governed_string_reaches_the_transport_unaltered(
    name: str, channel: ChannelId
) -> None:
    """`SC-014`, `SC-015`, against the transport's own record rather than the presentation object.

    The comparison is with `payload_governed_strings(payload)`, which reads the payload rather than
    the renderer's attestation about the payload — a renderer compared against its own list of what
    it carried would only ever prove itself self-consistent.
    """
    assert_the_production_resolver_still_refuses(channel)
    result, transport, trail = _run(name, channel)

    assert result.refusal is None, result.refusal
    assert result.delivery is DeliveryOutcome.DELIVERED
    assert transport.sends == 1
    assert trail.stages[-1] is ChannelStage.DELIVERED

    delivered = _delivered(transport)
    missing = [text for text in payload_governed_strings(CORPUS[name]) if text not in delivered]
    assert not missing, f"{name} on {channel.value}: the transport never received {missing}"


@pytest.mark.parametrize("channel", _CHANNELS)
@pytest.mark.parametrize("name", _DELIVERS)
def test_the_transport_receives_nothing_but_governed_content_and_permitted_separators(
    name: str, channel: ChannelId
) -> None:
    """`FR-046` — the differential half, on the wire rather than in the renderer.

    Presence alone cannot see an addition: a greeting, an apology, a bridging clause or a "part 2 of
    3" label would leave every governed string exactly where it was. Stripping what is authorised
    and requiring the remainder to be empty is what makes an addition visible.
    """
    assert_the_production_resolver_still_refuses(channel)
    _, transport, _ = _run(name, channel)

    residue = _residue(_delivered(transport), CORPUS[name])
    assert residue == "", (
        f"{name} on {channel.value}: the delivered bytes carry text no governed source "
        f"authorised: {residue!r}"
    )


@pytest.mark.parametrize("channel", _CHANNELS)
@pytest.mark.parametrize("name", _DELIVERS)
def test_every_fragment_the_transport_received_carries_every_caveat(
    name: str, channel: ChannelId
) -> None:
    """`FR-047`, `SC-019`, asserted per fragment rather than as a count.

    The contract test asserts `caveat_count` on the presentation. That is the weaker property: a
    count is a number the renderer wrote down. What matters to a reader is that no fragment can be
    read on its own as an uncaveated finding, so every caveat is required in every body the
    transport was handed — including "maximum caveat count", the entry where showing a subset would
    be most tempting.
    """
    assert_the_production_resolver_still_refuses(channel)
    result, transport, _ = _run(name, channel)

    payload = CORPUS[name]
    caveats = [caveat.message_pt_br for caveat in payload.answer.caveats.caveats]
    assert result.presentation is not None

    _, fragments = transport.calls[0]
    assert len(fragments) == len(result.presentation.fragments)
    for index, body in enumerate(fragments, start=1):
        for caveat in caveats:
            assert caveat in body, f"{name} on {channel.value}: fragment {index} omits a caveat"


@pytest.mark.parametrize("channel", _CHANNELS)
@pytest.mark.parametrize("name", _WITHHOLDS)
def test_an_entry_with_an_unresolved_reference_withholds_and_transmits_nothing(
    name: str, channel: ChannelId
) -> None:
    """ADR 0026, `FR-049`, `SC-020`. The designed-to-withhold entry, held to withholding.

    This is the half of the corpus a test is tempted to make pass. It must not: a reference with no
    resolved string is a pointer, and delivering a pointer to a reader is the failure the withhold
    exists to prevent. So what is asserted is that the path stops at `RENDERED`, that the trail
    records the stop, and that the transport was never called at all — `sends == 0` **and** an empty
    call list, because a call carrying zero fragments is still a call.

    `asks == 1` is asserted for the reason `handle` sets it: the question reached the port and was
    answered. Only the answer could not be rendered.
    """
    assert_the_production_resolver_still_refuses(channel)
    result, transport, trail = _run(name, channel)

    assert result.refusal is not None, f"{name} on {channel.value} was expected to withhold"
    assert result.refusal.stage is ChannelStage.RENDERED
    assert result.refusal.sender_text().strip(), "a withheld response still needs governed wording"
    assert result.presentation is None
    assert result.delivery is None
    assert transport.sends == 0
    assert transport.calls == []
    assert result.asks == 1
    assert trail.stages == (
        ChannelStage.RECEIVED,
        ChannelStage.VERIFIED,
        ChannelStage.IDENTIFIED,
        ChannelStage.SUBMITTED,
        ChannelStage.RENDERED,
    )


def test_a_corrupted_rendering_would_be_caught_before_anything_is_transmitted() -> None:
    """Anti-vacuity. Every node above passes on a path that works; this one proves it could fail.

    The presentation `handle` genuinely produced is copied with one governed string altered by a
    single character — the smallest change that is still a change — and both instruments are then
    pointed at it: this file's own residue check, and the production gate `handle` runs. Both must
    reject it. If either accepted the corruption, every assertion above would be measuring nothing
    but the absence of an obvious bug.

    The longest governed string is the victim, so the corruption cannot hide inside another one, and
    the honest run's own delivery is re-asserted afterwards, so it is clear that the corruption
    happened to a copy and never reached the transport.
    """
    assert _ALL_FOUR in CORPUS, "the anti-vacuity node names a corpus entry that no longer exists"
    assert_the_production_resolver_still_refuses(ChannelId.SLACK)
    result, transport, _ = _run(_ALL_FOUR, ChannelId.SLACK)

    payload = CORPUS[_ALL_FOUR]
    assert result.presentation is not None
    victim = max(payload_governed_strings(payload), key=len)
    corrupted = victim[:-1] + "X"
    fragments = tuple(
        fragment.model_copy(update={"body": fragment.body.replace(victim, corrupted)})
        for fragment in result.presentation.fragments
    )
    presentation = result.presentation.model_copy(update={"fragments": fragments})

    delivered = "\n\n".join(fragment.body for fragment in presentation.fragments)
    assert victim not in delivered, "the corruption did not take, so nothing below proves anything"
    assert _residue(delivered, payload) != "", "this file's own residue check would not notice"

    report = preservation_report(presentation, payload, FIXTURE_CAPABILITY)
    assert not report.preserved
    assert victim in report.missing_strings
    with pytest.raises(WithheldAfterRendering) as caught:
        assert_preserved(presentation, payload, FIXTURE_CAPABILITY)
    assert caught.value.code is ChannelReasonCode.CHANNEL_OUTBOUND_WITHHELD

    assert transport.sends == 1, "the honest run delivered; only the copy above was corrupted"
