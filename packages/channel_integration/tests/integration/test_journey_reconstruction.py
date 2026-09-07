"""A message's journey, rebuilt from the audit trail alone — T131 [US7].

`FR-081` - `FR-084`; `SC-039`, `SC-040`.

The claim under test is narrow and awkward on purpose: **an operator holds the events and nothing
else**. So every node below reconstructs from `RecordingAuditSink.events` and does not look at the
`RoundTripResult` while doing it. Where a comparison against the result is made, it happens *after*
the reconstruction is complete, and the reconstruction function cannot see the result at all — it
takes a sequence of `ChannelAuditEvent` and returns journeys. A test that peeked would be asserting
that two views of the same object agree, which is not what `FR-084` asks.

## What a journey is, expressed as something a grouping can produce

Group by `correlation_id`. Within a group, the six stages in `CHANNEL_STAGE_ORDER`, one channel,
one tenant, one principal reference, one pseudonymous external reference, one message key, and a
terminal code that says how it ended. Every one of those is a field the event already carries, and
none of them is content — which is the whole design: the journey is reconstructible **because** the
event set was chosen to make it so without a payload field existing.

## Interleaving, and why it is constructed rather than threaded

`handle` is one synchronous call that emits its six events before returning, so two journeys cannot
be woven together *inside* one invocation. Two runs share one sink and the merged list is then
round-robin interleaved, which preserves each journey's own internal order while maximising the
interleave between them. That is the worst arrival order a shared sink could present, and grouping
by `correlation_id` has to survive it. Real threads would make it a race that could pass by luck.

## The honest hole in `SC-039`, measured 2026-08-19

`SC-039` says a complete journey is reconstructible "in 100% of cases". Measured, that is not
achievable and the reason is structural rather than an omission: `build_event` requires a tenant, a
principal reference, a correlation id and a message key, and none of the four is resolved before
step 7. A message refused at steps 1 to 7 therefore emits **nothing** and has no journey to rebuild
— `handle` returns `stages == ()` and the sink stays empty. Read strictly, the criterion is 100% of
*identified* messages, and the alternative would be a trail carrying a placeholder tenant and a
synthetic correlation id, which is a record that reads as true in exactly the field an operator
would trust. The node below asserts the emptiness and says what it costs: for such a message the
audit trail answers nothing, and the refusal returned to the transport holder is the only account
of it that exists.

## The forbidden-content scan

Modelled on `tests/security/test_leak_scan.py`, and marked the same way: one distinctive sentinel
per category, so a failure names the category instead of reporting that a string turned up
somewhere. Four categories are driven here — the question text, the answer text, the raw external
identity, and the governed limit numbers. The limits are given unmistakable values through
`TransportBounds.model_copy` rather than scanned for as small integers: a correlation id is a hex
digest, and searching one for `"60"` would be a coin flip rather than a test.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, get_args

import pytest

from channel_integration.contracts.audit import (
    CHANNEL_STAGE_ORDER,
    ChannelAuditEvent,
    ChannelStage,
    DetailClass,
)
from channel_integration.contracts.delivery import DeliveryOutcome
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.envelope import ChannelEnvelope
from channel_integration.contracts.identity import ExternalIdentity
from channel_integration.contracts.kinds import MessageKind
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.contracts.refusal import ChannelRefusal
from channel_integration.outbound.preserve import payload_governed_strings
from channel_integration.roundtrip import RoundTripResult, handle
from tests.fixtures.channels import (
    AT,
    FIXTURE_BOUNDS,
    FIXTURE_MATERIAL,
    RecordingAuditSink,
    RecordingDeliveryPort,
    assert_the_production_resolver_still_refuses,
    descriptor_for,
    fixture_capabilities,
    signed_request,
    wire_payload,
)
from tests.fixtures.identity import (
    CountingIdentityResolver,
    active_binding,
    fixture_principal_context,
    fixture_pseudonymiser,
)
from tests.fixtures.interaction import recording_interaction
from tests.fixtures.payloads import FixturePayload, payload_for

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

pytestmark = pytest.mark.integration

CHANNEL = ChannelId.SLACK
_ALL_FOUR = "all four claim classes"

#: One distinctive sentinel per forbidden category, so a failure names the category. The question
#: keeps a plausible pt-BR shape so it still passes the envelope's usability validator: a sentinel
#: that could not be sent would be a sentinel that never reaches the surface under test.
_MARKED_QUESTION = "LEAKMARKQUESTION quantas instalacoes tivemos em julho?"
_MARKED_IDENTITY = ExternalIdentity("LEAKMARKIDENTITY-5511999990000")

#: Governed limit numbers, given values no digest will contain by accident. `handle` reads none of
#: the three, which is part of the point: they are the numbers a careless record would echo.
_MARKED_LIMITS: tuple[str, ...] = ("987654321", "987654322", "987654323")
_MARKED_BOUNDS = FIXTURE_BOUNDS.model_copy(
    update={
        "idempotency_window_seconds": 987654321,
        "rate_limit_per_minute": 987654322,
        "maximum_inbound_bytes": 987654323,
    }
)


def _drive(
    *,
    message_id: str = "provider-message-1",
    kind: MessageKind = MessageKind.TEXT,
    sink: RecordingAuditSink | None = None,
    delivery: RecordingDeliveryPort | None = None,
    port_present: bool = True,
) -> tuple[RoundTripResult, RecordingAuditSink, FixturePayload]:
    """One message through the composition, marked in every forbidden category at once."""
    fixture = payload_for(_ALL_FOUR)
    trail = sink if sink is not None else RecordingAuditSink()
    transport = delivery if delivery is not None else RecordingDeliveryPort()
    result = handle(
        signed_request(CHANNEL, payload=wire_payload(text=_MARKED_QUESTION, message_id=message_id)),
        descriptor=descriptor_for(CHANNEL),
        material=FIXTURE_MATERIAL,
        bounds=_MARKED_BOUNDS,
        kind=kind,
        external=_MARKED_IDENTITY,
        resolver=CountingIdentityResolver(active_binding()),
        pseudonymiser=fixture_pseudonymiser(),
        at=AT,
        principal=fixture_principal_context(),
        wording=fixture.wording,
        port=recording_interaction(fixture.answer) if port_present else None,
        capabilities=fixture_capabilities,
        delivery=transport,
        sink=trail,
    )
    return result, trail, fixture


# --------------------------------------------------------------------------- #
# The reconstruction, which sees events and nothing else                       #
# --------------------------------------------------------------------------- #


def _journeys(events: Iterable[ChannelAuditEvent]) -> dict[str, tuple[ChannelAuditEvent, ...]]:
    """Every journey in ``events``, keyed by `correlation_id`, each in arrival order.

    Deliberately the whole reconstruction algorithm: one grouping over one field. If rebuilding a
    journey needed anything cleverer than this, `FR-084` would not be satisfied by the event
    contract — it would be satisfied by whoever happened to write the right query.
    """
    grouped: dict[str, list[ChannelAuditEvent]] = {}
    for event in events:
        grouped.setdefault(str(event.correlation_id), []).append(event)
    return {key: tuple(value) for key, value in grouped.items()}


def _constant(events: Sequence[ChannelAuditEvent], field: str) -> object:
    """The one value ``field`` takes across a journey, or fail naming the disagreement.

    A journey whose channel or tenant changed halfway would not be one journey, and an operator
    reading it would draw a conclusion about a message that never existed.
    """
    values = {getattr(event, field) for event in events}
    assert len(values) == 1, f"{field} is not constant across the journey: {values}"
    return values.pop()


def _interleaved(events: Sequence[ChannelAuditEvent]) -> list[ChannelAuditEvent]:
    """Weave the two halves of ``events`` together, alternating, keeping each half's own order."""
    half = len(events) // 2
    woven: list[ChannelAuditEvent] = []
    for left, right in zip(events[:half], events[half:], strict=True):
        woven.append(left)
        woven.append(right)
    return woven


def _leaked(serialised: str, categories: Mapping[str, tuple[str, ...]]) -> list[str]:
    """Which forbidden categories appear in ``serialised``. Empty is the only pass."""
    return sorted(
        name for name, values in categories.items() if any(value in serialised for value in values)
    )


def _forbidden_categories(fixture: FixturePayload) -> dict[str, tuple[str, ...]]:
    """The four categories, with the marked values that stand for each.

    The answer text is taken from `payload_governed_strings` rather than retyped, so the category
    tracks whatever the payload actually carries — including the values with their units, which are
    the strings a record is most tempted to keep "just the number" of.
    """
    return {
        "the question the sender wrote": (_MARKED_QUESTION, "LEAKMARKQUESTION"),
        "the raw external identity": (_MARKED_IDENTITY.reveal(), "LEAKMARKIDENTITY"),
        "the answer text": tuple(payload_governed_strings(fixture)),
        "a governed limit number": _MARKED_LIMITS,
    }


def _serialise(events: Iterable[ChannelAuditEvent]) -> str:
    """Every event as the bytes a sink would durably hold. The surface the scan actually reads."""
    return "\n".join(event.model_dump_json() for event in events)


# --------------------------------------------------------------------------- #
# Reconstruction                                                               #
# --------------------------------------------------------------------------- #


def test_one_journey_is_fully_rebuilt_from_the_events_alone() -> None:
    """`SC-039`, `FR-084`: everything an operator needs, recovered by grouping on one field.

    The six stages in order, and the constants that make the group a journey rather than a pile.
    Nothing here reads the `RoundTripResult`; the comparison against it is a separate node,
    deliberately, so this one cannot borrow an answer from the object it is meant to reconstruct.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    _, trail, _ = _drive()

    journeys = _journeys(trail.events)
    assert len(journeys) == 1
    (journey,) = journeys.values()

    assert tuple(event.stage for event in journey) == CHANNEL_STAGE_ORDER
    assert _constant(journey, "channel") is CHANNEL
    assert str(_constant(journey, "tenant")) == "tenant-a"
    assert str(_constant(journey, "message_key")) == "provider-message-1"
    principal = _constant(journey, "principal_ref")
    assert isinstance(principal, str)
    assert principal
    reference = _constant(journey, "external_identity_ref")
    assert reference is not None, "the journey cannot be joined to an actor"

    assert journey[-1].code == ChannelReasonCode.CHANNEL_RESPONSE_DELIVERED.value, (
        "the trail does not say how the message ended"
    )
    assert {event.detail_class for event in journey} == {DetailClass.NONE}


def test_the_rebuilt_journey_agrees_with_the_run_that_produced_it() -> None:
    """The comparison, made **after** the reconstruction and never during it.

    Reconstruction first, from events only; then the result is opened and the two are compared. Run
    the other way round this would prove that the trail can be made to match a known answer, which
    is a different and much weaker statement.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    result, trail, _ = _drive()

    ((correlation, journey),) = _journeys(trail.events).items()
    rebuilt_stages = tuple(event.stage for event in journey)
    rebuilt_channel = _constant(journey, "channel")
    rebuilt_message_key = str(_constant(journey, "message_key"))

    assert isinstance(result.envelope, ChannelEnvelope)
    assert correlation == str(result.envelope.correlation_id)
    assert rebuilt_stages == result.stages
    assert rebuilt_channel is result.envelope.channel
    assert rebuilt_message_key == str(result.envelope.message_id)
    assert result.delivery is DeliveryOutcome.DELIVERED


def test_two_interleaved_correlations_separate_cleanly() -> None:
    """The property that makes `correlation_id` the key rather than arrival order.

    One sink holds both trails; the merged list is then woven one-for-one, so no journey's events
    are adjacent. Grouping must still return two journeys of six, each in its own stage order, each
    with its own message key — and the two must share nothing but the channel and the tenant.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    trail = RecordingAuditSink()
    _drive(message_id="provider-message-1", sink=trail)
    _drive(message_id="provider-message-2", sink=trail)
    assert len(trail.events) == 12

    woven = _interleaved(trail.events)
    assert [str(event.message_key) for event in woven[:4]] == [
        "provider-message-1",
        "provider-message-2",
        "provider-message-1",
        "provider-message-2",
    ], "the merged trail was not actually interleaved, so the separation claim is untested"

    journeys = _journeys(woven)
    assert len(journeys) == 2
    keys: set[str] = set()
    for journey in journeys.values():
        assert len(journey) == 6
        assert tuple(event.stage for event in journey) == CHANNEL_STAGE_ORDER
        keys.add(str(_constant(journey, "message_key")))
        assert _constant(journey, "channel") is CHANNEL
    assert keys == {"provider-message-1", "provider-message-2"}


def test_a_journey_that_stopped_early_says_where_it_stopped_and_nothing_more() -> None:
    """ "Where did this message die?" is a query over the trail, not an investigation.

    A message with no interaction port stops at `SUBMITTED`. The rebuilt journey therefore has four
    stages, not six, and its last event carries the boundary code rather than a delivery code.
    Reconstructing a partial journey is the case an operator actually meets, so it is asserted at
    the same standard as the complete one.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    _, trail, _ = _drive(port_present=False)

    (journey,) = _journeys(trail.events).values()
    stages = tuple(event.stage for event in journey)
    assert stages == CHANNEL_STAGE_ORDER[:4]
    assert stages[-1] is ChannelStage.SUBMITTED
    assert journey[-1].code == ChannelReasonCode.INTERACTION_BOUNDARY_UNAVAILABLE.value
    assert ChannelStage.DELIVERED not in stages, "a trail claims a delivery that did not happen"


def test_a_refusal_before_identity_leaves_no_journey_to_reconstruct() -> None:
    """The measured limit of `SC-039`, asserted rather than rounded up to 100%.

    A non-textual message refuses at step 4, before a tenant, a principal reference, a correlation
    id or a message key is resolved — so no compliant event is constructible and none is emitted.
    What this costs is worth naming: for such a message the audit trail answers nothing at all, and
    the governed refusal handed back to whoever holds the transport is the only account that exists.
    The alternative — a placeholder tenant and a synthetic correlation id — would produce a journey
    that reads as true and is false in the two fields an operator would rely on most.
    """
    result, trail, _ = _drive(kind=MessageKind.AUDIO)

    assert isinstance(result.refusal, ChannelRefusal)
    assert result.refusal.code is ChannelReasonCode.CHANNEL_MESSAGE_KIND_UNSUPPORTED
    assert result.stages == ()
    assert trail.events == []
    assert _journeys(trail.events) == {}, "an unidentified message produced a journey from nothing"


# --------------------------------------------------------------------------- #
# Forbidden content                                                            #
# --------------------------------------------------------------------------- #


def test_no_serialised_event_carries_any_forbidden_content() -> None:
    """`SC-040`, over the trail the composed path actually emitted.

    Every category is marked in the same run: the question is a sentinel, the external identity is a
    sentinel, the bounds carry sentinel numbers, and the answer's governed strings come from the
    payload itself. A leak in any one of them names its own category.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    _, trail, fixture = _drive()

    serialised = _serialise(trail.events)
    assert serialised, "nothing was serialised, so the scan read an empty surface"
    leaks = _leaked(serialised, _forbidden_categories(fixture))
    assert not leaks, f"the audit trail leaked: {leaks}"


def test_a_provider_failure_reaches_the_trail_as_a_code_and_not_as_its_message() -> None:
    """`FR-061`, `FR-082`: an exception's message is provider text, and provider text never travels.

    Driven separately from the node above because it needs a provider that throws, and a throwing
    provider changes the terminal code — which is itself the assertion: the trail records
    `CHANNEL_DELIVERY_ATTEMPTS_EXHAUSTED` and carries not one word of what the provider said.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    _, trail, fixture = _drive(delivery=RecordingDeliveryPort(raises=True))

    serialised = _serialise(trail.events)
    assert not _leaked(serialised, _forbidden_categories(fixture))
    assert trail.events[-1].code == ChannelReasonCode.CHANNEL_DELIVERY_ATTEMPTS_EXHAUSTED.value


def test_no_event_field_could_hold_a_governed_limit_even_if_someone_tried() -> None:
    """The structural half, because a scan alone only proves nothing leaked *this time*.

    `ChannelAuditEvent` declares no numeric field at all. The only two fields that could carry a
    governance number are `policy_version` and `capability_version`, and measured 2026-08-19 the
    composed path passes neither — `roundtrip._record` calls `build_event` without them, so both are
    `None` on every event a journey contains. That is asserted here rather than assumed, because if
    either ever starts being populated it must be a version string and never a limit.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    _, trail, _ = _drive()

    for event in trail.events:
        assert event.policy_version is None
        assert event.capability_version is None
    numeric = (int, float, Decimal)
    for name, field in ChannelAuditEvent.model_fields.items():
        # Compared as **types**, not as substrings of the annotation's repr. The first draft matched
        # `"int" in str(annotation)` and reported `tenant`, whose repr contains the package name
        # `channel_integration`. A scan that reports the package it is scanning is not a scan.
        candidates = (field.annotation, *get_args(field.annotation))
        offending = [
            one for one in candidates if isinstance(one, type) and issubclass(one, numeric)
        ]
        assert not offending, (
            f"ChannelAuditEvent.{name} can hold a number ({offending}), so a governed limit has "
            "somewhere to go"
        )


# --------------------------------------------------------------------------- #
# Anti-vacuity                                                                 #
# --------------------------------------------------------------------------- #


def test_the_scan_and_the_grouping_can_both_report_a_failure() -> None:
    """Anti-vacuity, for the two instruments this whole file rests on.

    The scan would pass over any trail if `_leaked` never matched, and the separation claim would
    pass over any trail that only ever contained one correlation. So the scan is shown catching a
    planted sentinel in each category, and the grouping is shown collapsing to a single journey once
    the correlation ids are forced to agree — which is exactly the failure the interleave node would
    otherwise not be able to detect.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    _, trail, fixture = _drive()
    categories = _forbidden_categories(fixture)
    clean = _serialise(trail.events)

    for name, values in categories.items():
        poisoned = clean + "\n" + values[0]
        assert name in _leaked(poisoned, categories), (
            f"the scan cannot detect {name}, so its absence proves nothing"
        )

    assert _leaked(clean, categories) == [], (
        "the clean trail already leaks, so the plants prove nothing"
    )
    assert len(_journeys(trail.events)) == 1
