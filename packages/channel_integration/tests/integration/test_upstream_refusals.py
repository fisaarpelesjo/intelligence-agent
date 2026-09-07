"""T125 — every upstream reason code arrives unmodified, carried as a governed state (`SC-017`).

`SC-017`: 100% of reason codes arrive unmodified with their stored wording; zero are paraphrased,
translated at delivery time or presented as an error.

## An upstream refusal is an outcome, not a raise

`interaction/port.py` states the design and its reason: `InteractionPort.ask` returns
`AnalyticsAnswer | ClarificationContract | GovernedRefusal`, "returning a union rather than raising
is deliberate ... a caller that had to catch it could forget to". So every node here drives
`refusing_interaction(...)`, which returns the refusal exactly as `003` would, and the fact that
`handle` returned rather than raised is itself part of what "presented as a governed state" means.

## What `handle` does with it, measured

`outbound/render.py` exposes `render_for_channel(payload: GovernedAnswerPayload, ...)` and there is
no rendering path for a refusal. Measured 2026-08-19 across every code below: `handle` puts the
object on `result.upstream` **unread and unrendered**, `result.refusal is None`,
`result.delivery is None`, `result.presentation is None`, `asks == 1`, and the stage trail stops at
`SUBMITTED`.

The passthrough is asserted two ways, because they catch different failures. `is` **identity**
proves no copy, no re-validation and no re-serialisation happened at all — a layer that had parsed
and rebuilt the refusal could still produce equal fields while having decided what those fields
mean. **Field-by-field equality** proves the object was not mutated in place. Identity alone would
pass for a mutated object; equality alone would pass for a re-coded reconstruction. `SC-017` needs
both.

## A stand-in, because `GovernedRefusal` is not on the import allowlist

`003`'s `GovernedRefusal` sets `upstream_code` and `upstream_message` together for a refusal that
came from `001` or `002`, and carries them verbatim. That name is **not** in
`contracts/interaction-port.md` §3, so `tests/contract/test_import_allowlist.py` would fail on it,
and that file says plainly that "a twenty-second name is a new decision" which a test may not take.

So the corpus is built from a local frozen dataclass mirroring the two fields an upstream refusal
carries. That is not a compromise here — it is the tighter instrument. `handle` types this slot as
`object` and never reads it, and a deliberately foreign type makes "never read" demonstrable: any
implementation that had inspected, validated, coerced or re-coded the outcome would have had to know
what it was, and would fail on every one of these rather than pass.

## The measured thing that contradicts the obvious expectation

The audit trail for a carried upstream refusal records `CHANNEL_MESSAGE_ACCEPTED` at `SUBMITTED` —
an `ALLOW` code — even though upstream refused. That reads wrong at first and is right: the trail
records what the **channel** did, and the channel did accept the message and did submit it once. Had
it recorded a `004` DENY code instead, this layer would have restated an upstream verdict in its own
vocabulary, which is exactly what `FR-045` forbids. So it is asserted rather than assumed, together
with the fact that the upstream code and its wording appear nowhere in the serialised trail.

## Production's capability resolver is what this file passes

Nothing renders on this path, so `capabilities` is never called — and passing the **production**
resolver is the cleanest proof of that: `D-28` is undeclared, so `resolve_capability_matrix` refuses
for every channel, and a run that touched it would come back refused at `RENDERED` instead of
carrying anything. No fixture capability matrix is injected anywhere in this file, so no node here
needs `assert_the_production_resolver_still_refuses` to stay honest.
`test_rendering_is_never_attempted_for_a_carried_refusal` states the same fact a second way, with a
resolver that raises.

## What is not duplicated

`tests/contract/test_reason_code_namespaces.py` (T014) owns four-way pairwise disjointness as a
contract. This file asserts the **operational consequence** the passthrough depends on: not one of
the codes carried through here is a member of `ChannelReasonCode`, so an upstream code arriving at a
consumer can never be read as a channel code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from semantic_catalog.contracts.reason_codes import ReasonCode

from channel_integration.contracts.audit import ChannelStage
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.kinds import MessageKind
from channel_integration.contracts.reason_codes import (
    ChannelReasonCode,
    Outcome,
    channel_outcome_for,
)
from channel_integration.governance.capabilities import resolve_capability_matrix
from channel_integration.roundtrip import CapabilityResolver, RoundTripResult, handle
from tests.fixtures.channels import (
    AT,
    FIXTURE_BOUNDS,
    FIXTURE_MATERIAL,
    RecordingAuditSink,
    RecordingDeliveryPort,
    descriptor_for,
    signed_request,
)
from tests.fixtures.identity import (
    FIXTURE_EXTERNAL,
    CountingIdentityResolver,
    active_binding,
    fixture_principal_context,
    fixture_pseudonymiser,
)
from tests.fixtures.interaction import RecordingInteraction, refusing_interaction
from tests.fixtures.payloads import payload_for

if TYPE_CHECKING:
    from collections.abc import Mapping

pytestmark = pytest.mark.integration

CHANNEL = ChannelId.SLACK

_PAYLOAD = payload_for("all four claim classes")


@dataclass(frozen=True)
class _UpstreamRefusal:
    """A stand-in for the upstream half of `003`'s `GovernedRefusal`. **TEST-ONLY.**

    Two fields, because `GovernedRefusal` sets exactly those two together for a refusal that
    originated in `001` or `002` and carries both verbatim. See the module docstring for why the
    real type is not imported and why a foreign type is the better instrument here.

    Frozen, so a passthrough failure cannot be masked by this object having been edited between the
    port returning it and the assertion reading it.
    """

    upstream_code: str
    upstream_message: str


def _upstream_refusal(namespace: str, code: str) -> _UpstreamRefusal:
    """One refusal per upstream code, with wording that is **distinct per code**.

    Distinct deliberately: identical wording everywhere would let a swapped message pass a
    comparison that only really checked the code, and `SC-017` is a claim about the wording as much
    as about the code. It is stand-in wording rather than `001`/`002`/`003`'s real stored text —
    resolving that would mean reaching into three governed content roots this feature does not own —
    and the property under test is that whatever arrived leaves unchanged, which any distinct string
    measures exactly as well.
    """
    return _UpstreamRefusal(
        upstream_code=code,
        upstream_message=f"wording stored by {namespace} for {code}, resolved before 004 saw it",
    )


#: Every code in all three upstream namespaces, grouped by the layer that owns it. Enumerated from
#: the enums themselves rather than from a written list, so a code added upstream joins this corpus
#: on the next run instead of when somebody remembers.
_CORPUS: dict[str, tuple[_UpstreamRefusal, ...]] = {
    "001 ReasonCode": tuple(_upstream_refusal("001 ReasonCode", code.value) for code in ReasonCode),
    "002 AnalyticsReasonCode": tuple(
        _upstream_refusal("002 AnalyticsReasonCode", code.value) for code in AnalyticsReasonCode
    ),
    "003 InterpretationReasonCode": tuple(
        _upstream_refusal("003 InterpretationReasonCode", code.value)
        for code in InterpretationReasonCode
    ),
}

_NAMESPACE_NAMES = tuple(_CORPUS)

_EVERY_REFUSAL: tuple[_UpstreamRefusal, ...] = tuple(
    refusal for refusals in _CORPUS.values() for refusal in refusals
)

_IDS = tuple(refusal.upstream_code for refusal in _EVERY_REFUSAL)

#: The stage trail a carried upstream refusal produces. It stops at `SUBMITTED` because nothing
#: after submission happened: no rendering, no preservation check, no delivery.
_CARRIED_TRAIL = (
    ChannelStage.RECEIVED,
    ChannelStage.VERIFIED,
    ChannelStage.IDENTIFIED,
    ChannelStage.SUBMITTED,
)


def _is_the_same_object(sent: _UpstreamRefusal, carried: object) -> bool:
    """Is ``carried`` the very object the port returned, rather than a reconstruction of it?"""
    return carried is sent


def _fields_are_unmodified(sent: _UpstreamRefusal, carried: object) -> bool:
    """Field by field, **without** appealing to identity.

    Separate from the identity check on purpose: this one catches an object mutated in place, that
    one catches an object rebuilt. `test_the_checks_would_catch_a_substitution_or_a_paraphrase`
    proves that neither check subsumes the other and that both can fail.
    """
    if not isinstance(carried, _UpstreamRefusal):
        return False
    return (
        carried.upstream_code == sent.upstream_code
        and carried.upstream_message == sent.upstream_message
    )


def _capabilities_that_must_not_be_called(channel: ChannelId) -> Mapping[str, Any]:
    """A capability resolver that fails loudly if the composed path ever reaches rendering.

    An `AssertionError` rather than a governed refusal, deliberately: `handle` catches
    `ChannelViolation` and `ContentUnresolvable` around the rendering block, so a refusing resolver
    would be absorbed into a `RENDERED` refusal and the node would have to infer what happened.
    This escapes and names the defect.
    """
    raise AssertionError(
        f"rendering was attempted for {channel.value}, but the port returned an upstream refusal "
        "and only an AnalyticsAnswer renders"
    )


class _Carried:
    """One round trip whose port answered with an upstream refusal, and every surface it touched."""

    __slots__ = ("port", "result", "sink", "transport")

    def __init__(
        self,
        result: RoundTripResult,
        port: RecordingInteraction,
        transport: RecordingDeliveryPort,
        sink: RecordingAuditSink,
    ) -> None:
        self.result = result
        self.port = port
        self.transport = transport
        self.sink = sink


def _run(
    refusal: _UpstreamRefusal,
    capabilities: CapabilityResolver = resolve_capability_matrix,
) -> _Carried:
    """One **full** round trip — real bytes, real signature, real conversion — ending at the port.

    Not a direct call to `submit`: the claim is that an upstream code survives the *whole* composed
    path, and a shortcut past conversion would leave the transport half untested. ``capabilities``
    defaults to production's resolver, which refuses for every channel and is never called here.
    """
    port = refusing_interaction(refusal)
    transport = RecordingDeliveryPort()
    sink = RecordingAuditSink()
    result = handle(
        signed_request(CHANNEL),
        descriptor=descriptor_for(CHANNEL),
        material=FIXTURE_MATERIAL,
        bounds=FIXTURE_BOUNDS,
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=CountingIdentityResolver(active_binding()),
        pseudonymiser=fixture_pseudonymiser(),
        at=AT,
        principal=fixture_principal_context(),
        wording=_PAYLOAD.wording,
        port=port,
        capabilities=capabilities,
        delivery=transport,
        sink=sink,
    )
    return _Carried(result, port, transport, sink)


# --- every upstream code, one full round trip each ----------------------------------------


@pytest.mark.parametrize("refusal", _EVERY_REFUSAL, ids=_IDS)
def test_every_upstream_code_arrives_unmodified_with_its_stored_wording(
    refusal: _UpstreamRefusal,
) -> None:
    """`SC-017` says 100%, so this is 100% — every code, each through the whole composed path.

    Not a sampled subset and not a table of "representative" codes: a passthrough that special-cased
    one namespace, one prefix or one length would be invisible to a sample and is visible here.
    """
    carried = _run(refusal)

    assert _is_the_same_object(refusal, carried.result.upstream), (
        f"{refusal.upstream_code} arrived as a different object, so something rebuilt it"
    )
    assert _fields_are_unmodified(refusal, carried.result.upstream), (
        f"{refusal.upstream_code} arrived with a modified field"
    )
    assert carried.result.refusal is None, (
        f"a 004 refusal was produced alongside {refusal.upstream_code}"
    )


def test_the_corpus_is_every_code_in_all_three_upstream_namespaces() -> None:
    """A corpus that quietly shrank would make the node above pass over less and still read as 100%.

    Asserting the union as a set as well as the count catches the other failure — a corpus of the
    right size built from the wrong codes.
    """
    carried_codes = {refusal.upstream_code for refusal in _EVERY_REFUSAL}
    declared = (
        {code.value for code in ReasonCode}
        | {code.value for code in AnalyticsReasonCode}
        | {code.value for code in InterpretationReasonCode}
    )
    assert carried_codes == declared, "the corpus and the upstream enums disagree"
    assert len(carried_codes) == len(_EVERY_REFUSAL), "a code is carried twice and one is missing"
    assert len(_EVERY_REFUSAL) > 50, "the corpus shrank below anything worth calling 100%"
    assert len({refusal.upstream_message for refusal in _EVERY_REFUSAL}) == len(_EVERY_REFUSAL), (
        "two codes share wording, so a swapped message could pass the field check"
    )


@pytest.mark.parametrize("namespace", _NAMESPACE_NAMES)
def test_one_ask_nothing_delivered_and_nothing_transmitted(namespace: str) -> None:
    """One full round trip per upstream namespace, asserted on what did and did not happen.

    `asks == 1` and `delivery is None` are the pair that matters: the port **was** reached, so this
    is not a message that refused early, and yet nothing was transmitted, because only an
    `AnalyticsAnswer` renders. The trail stops at `SUBMITTED` for the same reason.
    """
    carried = _run(_CORPUS[namespace][0])

    assert carried.result.asks == 1, namespace
    assert carried.port.calls == 1, namespace
    assert carried.result.delivery is None, namespace
    assert carried.result.presentation is None, namespace
    assert carried.transport.sends == 0, namespace
    assert carried.transport.calls == [], namespace
    assert carried.result.stages == _CARRIED_TRAIL, namespace
    assert carried.sink.stages == _CARRIED_TRAIL, "the recorded trail is not the trail that fired"


@pytest.mark.parametrize("namespace", _NAMESPACE_NAMES)
def test_the_trail_substitutes_no_channel_code_for_the_upstream_one(namespace: str) -> None:
    """`FR-045`: this layer restates no upstream verdict in its own vocabulary.

    Every recorded code is `CHANNEL_MESSAGE_ACCEPTED`, classified `ALLOW` — see the module docstring
    for why an `ALLOW` beside an upstream refusal is the correct record and not a contradiction. The
    serialised scan is the other half: the upstream code and its wording are not smuggled into an
    allowed field of an event either.
    """
    refusal = _CORPUS[namespace][0]
    carried = _run(refusal)

    assert carried.result.refusal is None, "a channel refusal was manufactured for an upstream one"
    assert carried.sink.events, "an empty trail would satisfy the loop below"
    for event in carried.sink.events:
        assert event.code == ChannelReasonCode.CHANNEL_MESSAGE_ACCEPTED.value, event.stage
        assert channel_outcome_for(ChannelReasonCode(event.code)) is Outcome.ALLOW, event.stage

    serialised = "\n".join(event.model_dump_json() for event in carried.sink.events)
    assert refusal.upstream_code not in serialised, "the upstream code was written into the trail"
    assert refusal.upstream_message not in serialised, "the upstream wording reached the trail"


@pytest.mark.parametrize("namespace", _NAMESPACE_NAMES)
def test_the_stored_wording_is_carried_and_neither_rendered_nor_paraphrased(namespace: str) -> None:
    """The wording survives byte-for-byte on the carried object and is produced nowhere else.

    "Zero are paraphrased or translated at delivery time" is measurable here in the strongest form
    available: there was no delivery. The transport was never called, so the scan over its calls is
    satisfied by an empty list — the load-bearing half is the byte-identical presence on
    `result.upstream`, asserted against the string the port was handed rather than against a copy.
    """
    refusal = _CORPUS[namespace][0]
    carried = _run(refusal)

    assert isinstance(carried.result.upstream, _UpstreamRefusal)
    assert carried.result.upstream.upstream_message == refusal.upstream_message
    assert carried.transport.calls == [], "something was transmitted for an upstream refusal"


def test_the_upstream_refusal_arrives_as_an_outcome_and_not_as_an_error() -> None:
    """ "Presented as a governed state" — `handle` returned, and what it returned is not an error.

    Three separate facts. `handle` did not raise, so the caller receives a result rather than having
    to catch. The carried object is not a `BaseException`, so nothing on this path turned a governed
    refusal into an error. And `result.refusal is None`, so this layer did not present upstream's
    verdict as its own.
    """
    refusal = _CORPUS["003 InterpretationReasonCode"][0]
    carried = _run(refusal)

    assert isinstance(carried.result, RoundTripResult)
    assert not isinstance(carried.result.upstream, BaseException), (
        "the upstream refusal was presented as an error"
    )
    assert carried.result.refusal is None
    assert carried.result.envelope is not None, "the message really did convert and submit"


def test_rendering_is_never_attempted_for_a_carried_refusal() -> None:
    """Only an `AnalyticsAnswer` renders, asserted twice by two instruments that fail differently.

    First with production's resolver, which refuses for every channel while `D-28` is undeclared: a
    run that reached rendering would come back refused at `RENDERED` instead of carrying anything.
    Then with a resolver that raises, which names the defect directly instead of leaving the reader
    to infer it from an absent stage.
    """
    refusal = _CORPUS["002 AnalyticsReasonCode"][0]

    with_production = _run(refusal)
    assert ChannelStage.RENDERED not in with_production.result.stages
    assert with_production.result.refusal is None, "production's resolver was consulted after all"

    with_a_trap = _run(refusal, _capabilities_that_must_not_be_called)
    assert _is_the_same_object(refusal, with_a_trap.result.upstream)
    assert with_a_trap.result.stages == _CARRIED_TRAIL


def test_no_upstream_code_can_be_mistaken_for_a_channel_code() -> None:
    """The operational consequence the passthrough depends on, in the direction that can fail.

    `T014` owns four-way pairwise disjointness as a contract. What this file needs is narrower and
    is asserted against the corpus actually carried: not one of the codes that travelled through
    `handle` is a member of `ChannelReasonCode`, so a consumer switching on the single `code` string
    can never read an upstream refusal as a channel one. The three upstream namespaces are checked
    mutually disjoint too, so "which layer refused" stays answerable from the code alone.
    """
    channel_codes = {code.value for code in ChannelReasonCode}
    for refusal in _EVERY_REFUSAL:
        assert refusal.upstream_code not in channel_codes, refusal.upstream_code

    sets = {name: {refusal.upstream_code for refusal in group} for name, group in _CORPUS.items()}
    names = sorted(sets)
    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            shared = sets[left] & sets[right]
            assert not shared, f"{left} and {right} share: {sorted(shared)}"


# --- anti-vacuity ------------------------------------------------------------------------


def test_the_checks_would_catch_a_substitution_or_a_paraphrase() -> None:
    """Proof that the two predicates above have teeth, including against a real substituted run.

    Four cases, each failing a different way. A `004` code put where the upstream one was — the
    exact defect `SC-017` exists to prevent — fails the field check. An upper-cased message (the
    cheapest possible paraphrase) fails it too. A `None` upstream, which is what a path that dropped
    the refusal entirely would leave, fails it. And a **twin** with identical fields passes the
    field check while failing the identity check, which is what proves the two are not the same
    assertion written twice.

    The last block is the important one: the port is made to answer with the substituted object and
    the assertion from `test_every_upstream_code_arrives_unmodified_with_its_stored_wording` is
    re-run against the original. It fails, so that node is measuring what the port returned rather
    than being true by construction.
    """
    sent = _EVERY_REFUSAL[0]
    substituted = _UpstreamRefusal(
        ChannelReasonCode.CHANNEL_PAYLOAD_MALFORMED.value, sent.upstream_message
    )
    paraphrased = _UpstreamRefusal(sent.upstream_code, sent.upstream_message.upper())
    twin = _UpstreamRefusal(sent.upstream_code, sent.upstream_message)

    assert not _fields_are_unmodified(sent, substituted), "a substituted code passed the check"
    assert not _fields_are_unmodified(sent, paraphrased), "a paraphrased message passed the check"
    assert not _fields_are_unmodified(sent, None), "a dropped refusal passed the check"
    assert _fields_are_unmodified(sent, twin), "an equal copy must pass the field check..."
    assert not _is_the_same_object(sent, twin), "...and must still fail the identity check"
    assert _is_the_same_object(sent, sent)

    swapped = _run(substituted)
    assert not _is_the_same_object(sent, swapped.result.upstream)
    assert not _fields_are_unmodified(sent, swapped.result.upstream), (
        "the round-trip assertion would pass even when the port returned a substituted code"
    )
    assert _is_the_same_object(substituted, swapped.result.upstream), (
        "and it does carry whatever the port actually returned, including a wrong one"
    )
