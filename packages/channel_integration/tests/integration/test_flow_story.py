"""Transport determinism through the composed path — T128 [US5].

`FR-053` - `FR-060`, `FR-063` - `FR-065`, `FR-111`; `SC-024` - `SC-029`.

Six flow conditions, each with the **single** outcome `contracts/delivery.py` specifies, driven
through `channel_integration.roundtrip.handle` rather than through the individual transport
modules. `tests/integration/test_transport_flow.py` already drives `deliver_once`,
`deliver_with_retry` and `IdempotencyWindow` directly, and `tests/integration/test_retry_scope.py`
already counts asks across a retry sequence. Neither of them composes. This file's whole value is
the composition: what the transport modules promise **when nobody wires them in**.

| Condition | Outcome the composed path actually produces |
|---|---|
| Redelivery of one `message_id` | Nothing is suppressed — the whole path runs twice (measured) |
| Provider rate limit | One send, `RATE_LIMITED`, `CHANNEL_RATE_LIMIT_EXCEEDED` recorded |
| Timeout **before** acceptance | `ATTEMPTS_EXHAUSTED`, zero fragments accepted |
| Timeout **after** acceptance | `INDETERMINATE`, never acknowledged as delivered |
| Two messages out of order | Each processed against its own envelope, two distinct trails |
| Body past the structural ceiling | Refused at `RECEIVED`, empty stage trail, nothing recorded |

## Three measurements that contradicted what this file was going to assert

**Measured 2026-08-19 — `handle` never consults the idempotency window.** The source of
`roundtrip.py` contains neither `IdempotencyWindow` nor `idempotency`, and `handle`'s parameter
list has no window, no store and no key. So the first flow condition does **not** produce
`DUPLICATE_SUPPRESSED` today: the same `message_id` handled twice asks the port twice, renders twice
and sends twice. That is asserted below exactly as it happens, because a test written to the
intention would have passed for one composition and silently gone on passing for a different one.
The suppression itself is correct and is asserted separately — `IdempotencyWindow.check` reports the
redelivery and carries the first outcome class forward — so the gap is precisely "the composition
does not call it", not "the window is wrong".

**Measured 2026-08-19 — `handle` calls `deliver_once`, not `deliver_with_retry`.** `D-26`'s
`retry_attempts` is honoured by `delivery/retry.py` and by nothing on the composed path. A
rate-limited provider therefore produces exactly one send here, where the retry module would have
produced more. Both are correct statements about different code, and only one of them is what a
message actually experiences today.

**Measured 2026-08-19 — the governed inbound size bound is enforced nowhere.**
`TransportBounds.maximum_inbound_bytes` is declared in `governance/bounds.py`, listed in
`governance/transport_policy.py` and *named in a docstring* in `inbound/parse.py`. No module that
receives a body compares one against it. The only ceiling a body meets is
`parse.STRUCTURAL_MAX_BYTES`, 64 KiB. The consequence is not merely a missing check:
`QuestionIntake` caps question text at 8192 characters, so a body inside the structural ceiling
but past that cap makes `handle` raise `pydantic.ValidationError` **after** three audit stages
were recorded.

That escape is now stated in `handle`'s own docstring rather than contradicted by it — it is the
same mechanism the declared language uses, where the governed set belongs upstream and upstream's
model raises. Both escapes are asserted here so neither can change unnoticed.

No clock anywhere: every instant is `AT`, so a boundary is exercised at the second it flips.
"""

from __future__ import annotations

import inspect
import json
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from channel_integration import roundtrip as roundtrip_module
from channel_integration.contracts.audit import ChannelStage
from channel_integration.contracts.delivery import DeliveryOutcome, outcome_reason_code
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.envelope import ChannelEnvelope
from channel_integration.contracts.kinds import MessageKind
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.contracts.refusal import ChannelRefusal
from channel_integration.delivery.outcome import MAY_BE_REPORTED_DELIVERED, may_retry
from channel_integration.idempotency.window import IdempotencyWindow
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
    FIXTURE_EXTERNAL,
    CountingIdentityResolver,
    active_binding,
    fixture_principal_context,
    fixture_pseudonymiser,
)
from tests.fixtures.interaction import recording_interaction
from tests.fixtures.payloads import FIXTURE_CAPABILITY, FixturePayload, payload_for

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

    from channel_integration.roundtrip import CapabilityResolver

pytestmark = pytest.mark.integration

CHANNEL = ChannelId.SLACK
_ALL_FOUR = "all four claim classes"

#: The source of the composed module, read once. Every structural claim below is made against this
#: text rather than against a memory of it, so a rewrite of `roundtrip.py` moves the assertions.
_COMPOSITION_SOURCE = inspect.getsource(roundtrip_module)


def _narrow_capability(channel: ChannelId) -> Mapping[str, Any]:
    """A matrix entry narrow enough to need several fragments.

    ``channel`` is accepted and ignored for the same reason `fixture_capabilities` ignores it: one
    entry every channel shares cannot be mistaken for a declaration about any of them.
    """
    return {**FIXTURE_CAPABILITY, "maximum_body_characters": 260}


def _drive(
    *,
    payload: dict[str, object] | None = None,
    body: bytes | None = None,
    payload_name: str = _ALL_FOUR,
    delivery: RecordingDeliveryPort | None = None,
    sink: RecordingAuditSink | None = None,
    capabilities: CapabilityResolver = fixture_capabilities,
) -> tuple[RoundTripResult, RecordingDeliveryPort, RecordingAuditSink, FixturePayload]:
    """One inbound message through the whole composition, with everything injected.

    The transport and the sink are returnable and reusable across calls, which is what makes the
    redelivery condition measurable: two runs against **one** recorder is how a second send shows
    up.
    """
    fixture = payload_for(payload_name)
    transport = delivery if delivery is not None else RecordingDeliveryPort()
    trail = sink if sink is not None else RecordingAuditSink()
    result = handle(
        signed_request(CHANNEL, payload=payload, body=body),
        descriptor=descriptor_for(CHANNEL),
        material=FIXTURE_MATERIAL,
        bounds=FIXTURE_BOUNDS,
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=CountingIdentityResolver(active_binding()),
        pseudonymiser=fixture_pseudonymiser(),
        at=AT,
        principal=fixture_principal_context(),
        wording=fixture.wording,
        port=recording_interaction(fixture.answer),
        capabilities=capabilities,
        delivery=transport,
        sink=trail,
    )
    return result, transport, trail, fixture


def _delivered_code(trail: RecordingAuditSink) -> str:
    """The code the `DELIVERED` stage recorded. The single outcome, as an operator reads it."""
    assert trail.stages[-1] is ChannelStage.DELIVERED, trail.stages
    return trail.events[-1].code


# --------------------------------------------------------------------------- #
# Condition 1 — redelivery                                                     #
# --------------------------------------------------------------------------- #


def test_a_redelivered_message_drives_the_whole_composition_a_second_time() -> None:
    """The measured behaviour of the first flow condition, stated as it is rather than as intended.

    `SC-024` requires that a sender's second copy of one message produce no second answer. Measured
    2026-08-19, the composed path provides no part of that: the same `message_id` handled twice
    produces two envelopes with the same correlation id, two submissions, two renderings and two
    sends, and a twelve-event trail rather than a six-event one.

    Asserted at the exact numbers because a weaker assertion would keep passing after the window is
    wired in. When `handle` does start consulting `IdempotencyWindow`, this node fails and names the
    change, which is what a measurement is for.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    transport = RecordingDeliveryPort()
    trail = RecordingAuditSink()

    first, _, _, _ = _drive(delivery=transport, sink=trail)
    second, _, _, _ = _drive(delivery=transport, sink=trail)

    assert isinstance(first.envelope, ChannelEnvelope)
    assert isinstance(second.envelope, ChannelEnvelope)
    assert first.envelope.message_id == second.envelope.message_id
    assert first.envelope.correlation_id == second.envelope.correlation_id

    assert first.asks == 1
    assert second.asks == 1, "each pass reached the port once"
    assert transport.sends == 2, (
        "the redelivery was suppressed, so the composition now consults something — re-derive this "
        "node against whatever it consults"
    )
    assert len(trail.events) == 12
    assert second.delivery is DeliveryOutcome.DELIVERED


def test_the_window_the_composition_never_calls_still_decides_the_duplicate_correctly() -> None:
    """The suppression is right; only the wiring is absent. Both halves matter.

    Without this node, the one above could pass because `IdempotencyWindow` itself is broken — a
    window that never reports a duplicate would produce exactly the same two sends. So the decision
    is exercised on the envelope the composition actually produced, with the governed window and the
    passed instant, and it must report the redelivery and carry the first outcome class forward.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    result, _, _, _ = _drive()
    assert isinstance(result.envelope, ChannelEnvelope)
    envelope = result.envelope

    window = IdempotencyWindow()
    before = window.check(CHANNEL, envelope.message_id, AT)
    assert not before.is_duplicate, "an unseen message must not be suppressed"

    window.remember(
        CHANNEL,
        envelope.message_id,
        envelope.tenant,
        envelope.principal_ref,
        DeliveryOutcome.DELIVERED,
        FIXTURE_BOUNDS,
        AT,
    )
    after = window.check(CHANNEL, envelope.message_id, AT)
    assert after.is_duplicate
    assert after.first_outcome is DeliveryOutcome.DELIVERED
    assert window.size() == 1


def test_the_composition_names_no_suppression_surface_at_all() -> None:
    """Structural, so the gap cannot close by accident and go unnoticed.

    A composition that suppressed duplicates *somewhere else* — inside `convert`, inside an adapter,
    behind a helper — would make the two nodes above measure the wrong thing. The absence is
    therefore asserted over the composed module's own source, by name.
    """
    for absent in ("IdempotencyWindow", "idempotency"):
        assert absent not in _COMPOSITION_SOURCE, (
            f"roundtrip.py now names {absent!r}; the redelivery nodes above measure a system that "
            "no longer exists"
        )
    assert "deliver_once" in _COMPOSITION_SOURCE, "the composition no longer delivers at all"


# --------------------------------------------------------------------------- #
# Condition 2 — provider rate limit                                            #
# --------------------------------------------------------------------------- #


def test_a_provider_rate_limit_produces_one_send_and_one_recorded_code() -> None:
    """`FR-057`. One attempt, reported explicitly, never abandoned and never looped.

    Measured 2026-08-19: the composition calls `deliver_once`, so the governed retry bound is not
    applied here. `test_retry_scope.py` proves `deliver_with_retry` honours `retry_attempts`; this
    proves a message on the composed path gets one attempt and an explicit terminal status, which
    are different facts and only the second one describes today's behaviour.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    result, transport, trail, _ = _drive(
        delivery=RecordingDeliveryPort(outcomes=(DeliveryOutcome.RATE_LIMITED,))
    )

    assert result.delivery is DeliveryOutcome.RATE_LIMITED
    assert transport.sends == 1, "the composition retried, so it now honours a bound it did not"
    assert _delivered_code(trail) == outcome_reason_code(DeliveryOutcome.RATE_LIMITED).value
    assert _delivered_code(trail) == ChannelReasonCode.CHANNEL_RATE_LIMIT_EXCEEDED.value
    assert result.refusal is None, "a rate limit is an outcome, not a governed refusal"
    assert may_retry(DeliveryOutcome.RATE_LIMITED), "the outcome is retryable; nothing here retries"


def test_the_bounded_retry_lives_outside_the_composition() -> None:
    """Where the governed bound is honoured, and where it is not. Both stated.

    `D-26`'s `retry_attempts` is a governed number and `delivery/retry.py` applies it. The composed
    path does not import that module, so no message travelling through `handle` is retried at all.
    Recorded as a measurement rather than a defect claim: whether the composition should retry is a
    decision, and this node is what fails when that decision is taken.
    """
    assert "deliver_with_retry" not in _COMPOSITION_SOURCE
    assert FIXTURE_BOUNDS.retry_attempts > 0, "the fixture bound is zero, so this proves nothing"


# --------------------------------------------------------------------------- #
# Conditions 3 and 4 — the two timeouts                                        #
# --------------------------------------------------------------------------- #


def test_a_timeout_before_acceptance_is_attempts_exhausted_and_carries_no_provider_text() -> None:
    """`FR-061`: a provider client that throws becomes an outcome, and its words travel nowhere.

    The double raises after recording the call, so the provider *was* reached and nothing it said
    survives — asserted against the composed result and against the trail, because those are the two
    surfaces an operator reads.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    result, transport, trail, _ = _drive(delivery=RecordingDeliveryPort(raises=True))

    assert result.delivery is DeliveryOutcome.ATTEMPTS_EXHAUSTED
    assert _delivered_code(trail) == ChannelReasonCode.CHANNEL_DELIVERY_ATTEMPTS_EXHAUSTED.value
    serialised = "\n".join(event.model_dump_json() for event in trail.events)
    assert "Traceback" not in serialised
    assert transport.sends == 1, (
        "the provider was asked exactly once. `RecordingDeliveryPort` records the call before it "
        "raises, which is the honest count: the request left this feature even though nothing "
        "came back — the opposite of the withhold paths, where the provider is never reached"
    )


def test_a_timeout_after_acceptance_is_indeterminate_and_is_never_acknowledged() -> None:
    """The state the six-outcome enum exists for, asserted at the composed seam.

    Collapsing it into failure licenses a resend that double-delivers a governed answer; collapsing
    it into success claims something nobody verified. The composed path must do neither, and must
    record the indeterminate code rather than the delivered one.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    result, _, trail, _ = _drive(delivery=RecordingDeliveryPort(indeterminate_from=0))

    assert result.delivery is DeliveryOutcome.INDETERMINATE
    assert result.delivery not in MAY_BE_REPORTED_DELIVERED
    assert not may_retry(DeliveryOutcome.INDETERMINATE)
    assert _delivered_code(trail) == ChannelReasonCode.CHANNEL_DELIVERY_INDETERMINATE.value


# --------------------------------------------------------------------------- #
# Condition 5 — ordering and continuation                                      #
# --------------------------------------------------------------------------- #


def test_a_continuation_is_one_send_of_many_fragments_in_index_order() -> None:
    """`FR-058`, `FR-059`. A narrow channel splits the response; it does not send it twice.

    Every fragment is offered, in the renderer's own order, in a single call — so "one send" stays
    a true statement about a message even when the channel forces several fragments.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    result, transport, trail, _ = _drive(capabilities=_narrow_capability)

    assert result.delivery is DeliveryOutcome.DELIVERED
    assert result.presentation is not None
    assert len(result.presentation.fragments) > 1, "the ceiling no longer forces a continuation"
    offered = transport.calls[0][1]
    assert offered == tuple(fragment.body for fragment in result.presentation.fragments)
    assert transport.sends == 1, "a continuation is one send of many fragments, not many sends"
    assert _delivered_code(trail) == ChannelReasonCode.CHANNEL_RESPONSE_DELIVERED.value


def test_two_messages_arriving_out_of_order_are_processed_against_their_own_envelopes() -> None:
    """`US5` scenario 5: no ordering assumption the governed contracts do not carry.

    The second-sent message is handled first. Each still derives its own correlation id from its own
    provider message id, and neither trail borrows anything from the other — which is the property,
    because the alternative is a second message landing inside the first one's story.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    trail = RecordingAuditSink()
    later, _, _, _ = _drive(payload=wire_payload(message_id="provider-message-2"), sink=trail)
    earlier, _, _, _ = _drive(payload=wire_payload(message_id="provider-message-1"), sink=trail)

    assert isinstance(later.envelope, ChannelEnvelope)
    assert isinstance(earlier.envelope, ChannelEnvelope)
    assert later.envelope.correlation_id != earlier.envelope.correlation_id
    assert later.delivery is DeliveryOutcome.DELIVERED
    assert earlier.delivery is DeliveryOutcome.DELIVERED
    correlations = {str(event.correlation_id) for event in trail.events}
    assert len(correlations) == 2
    assert len(trail.events) == 12


# --------------------------------------------------------------------------- #
# Condition 6 — size limits                                                    #
# --------------------------------------------------------------------------- #


def test_a_body_past_the_structural_ceiling_stops_before_any_record_can_exist() -> None:
    """The one size limit that is actually enforced, and its full consequence.

    `parse.STRUCTURAL_MAX_BYTES` is a contract ceiling, not a governed one, and the refusal names no
    number because the sender is unauthenticated. Because the refusal lands at step 1, no compliant
    audit event is constructible: the trail is empty, the port is never reached and the transport is
    never touched. All four are asserted, because "refused" alone would not distinguish this from a
    refusal that still emitted something.
    """
    oversized = json.dumps(wire_payload(text="a" * (70 * 1024))).encode()
    result, transport, trail, _ = _drive(body=oversized)

    assert isinstance(result.refusal, ChannelRefusal)
    assert result.refusal.code is ChannelReasonCode.CHANNEL_PAYLOAD_EXCEEDS_STRUCTURAL_LIMIT
    assert result.refusal.stage is ChannelStage.RECEIVED
    assert result.stages == ()
    assert trail.events == []
    assert transport.sends == 0
    assert result.asks == 0
    assert not any(character.isdigit() for character in result.refusal.sender_text()), (
        "the refusal names a number to an unauthenticated stranger"
    )


def test_the_governed_inbound_size_bound_is_enforced_nowhere_and_upstream_validation_escapes() -> (
    None
):
    """The finding this file was not looking for, asserted rather than left in prose.

    Measured 2026-08-19. `maximum_inbound_bytes` appears in exactly three modules: it is *declared*
    in `governance/bounds.py`, *named as a required field* in `governance/transport_policy.py`, and
    *mentioned in a docstring* in `inbound/parse.py`. No module that receives a body compares one
    against it.

    The consequence is that `003`'s own field cap becomes the effective ceiling: `QuestionIntake`
    caps question text at 8192 characters, and a body well inside the structural ceiling reaches
    `submit` and `pydantic.ValidationError` escapes `handle`. Three stages are already on the record
    when it escapes, and nothing is sent.

    `handle`'s docstring now names this escape rather than claiming totality against it — the
    governed set belongs upstream, so upstream's model decides and upstream's error is raised, which
    is the same mechanism the declared language uses. This node fails the day either the `004` bound
    is enforced or the escape is caught, and either change is exactly the change that should make it
    fail.
    """
    from pathlib import Path

    source_root = roundtrip_module.__file__
    assert source_root is not None
    package = Path(source_root).parent
    naming = sorted(
        path.relative_to(package).as_posix()
        for path in package.rglob("*.py")
        if "__pycache__" not in path.parts
        and "maximum_inbound_bytes" in path.read_text(encoding="utf-8")
    )
    assert naming == [
        "governance/bounds.py",
        "governance/transport_policy.py",
        "inbound/parse.py",
    ], f"the governed inbound bound is now read somewhere new: {naming}"

    transport = RecordingDeliveryPort()
    trail = RecordingAuditSink()
    with pytest.raises(ValidationError):
        _drive(payload=wire_payload(text="a" * 9000), delivery=transport, sink=trail)

    assert trail.stages == (
        ChannelStage.RECEIVED,
        ChannelStage.VERIFIED,
        ChannelStage.IDENTIFIED,
    ), "the stages recorded before the escape changed, so the escape point moved"
    assert transport.sends == 0, "something was transmitted on a path that raised"
    assert FIXTURE_BOUNDS.maximum_inbound_bytes > 9000, (
        "the fixture bound is now below the text this node sends, so the two limits are confounded"
    )
    documentation = inspect.getdoc(handle) or ""
    assert "ValidationError" in documentation, (
        "handle's docstring no longer names the upstream validation escape it actually has"
    )


def test_a_governed_block_larger_than_the_channel_maximum_withholds_and_sends_nothing() -> None:
    """The outbound half of the size condition. Nothing to split, so nothing is cut.

    A single indivisible governed block that does not fit has no continuation available, and the
    only remaining behaviour is to withhold: cutting it would be truncation wearing a continuation's
    clothes. Driven through the composition so the assertion covers the stage trail and the
    transport as well as the raised condition.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)

    def tiny(channel: ChannelId) -> Mapping[str, Any]:
        return {**FIXTURE_CAPABILITY, "maximum_body_characters": 20}

    result, transport, trail, _ = _drive(capabilities=tiny)

    assert isinstance(result.refusal, ChannelRefusal)
    assert result.refusal.stage is ChannelStage.RENDERED
    assert result.delivery is None
    assert transport.sends == 0
    assert trail.stages[-1] is ChannelStage.RENDERED


# --------------------------------------------------------------------------- #
# What the six outcomes mean on this path, and anti-vacuity                    #
# --------------------------------------------------------------------------- #


def test_two_of_the_six_outcomes_are_unreachable_through_the_composition() -> None:
    """`DeliveryOutcome` is total; the composed path reaches four of its six members.

    `WITHHELD` is unreachable because a withhold arrives here as a `ChannelRefusal` with
    `delivery is None` rather than as a delivery outcome, and `DUPLICATE_SUPPRESSED` is unreachable
    because nothing in the composition suppresses. Both absences are named in the source, so this
    node fails the moment either becomes reachable — which is when the table in this file's
    docstring stops being true.
    """
    assert len(DeliveryOutcome) == 6
    for unreachable in (DeliveryOutcome.WITHHELD, DeliveryOutcome.DUPLICATE_SUPPRESSED):
        assert unreachable.value not in _COMPOSITION_SOURCE, (
            f"{unreachable.value} is now produced by the composition; the condition table in "
            "this module's docstring is stale"
        )
    for reachable in (
        DeliveryOutcome.DELIVERED,
        DeliveryOutcome.RATE_LIMITED,
        DeliveryOutcome.ATTEMPTS_EXHAUSTED,
        DeliveryOutcome.INDETERMINATE,
    ):
        assert outcome_reason_code(reachable) is not None


def test_the_instruments_this_file_uses_can_all_report_a_failure() -> None:
    """Anti-vacuity. Every counter and every code assertion above must be able to say more.

    Three instruments carry the weight here: the send counter, the recorded delivery code, and the
    stage trail. A counter stuck at one, a code that is a constant, or a trail that is always the
    same six stages would make most of this file pass for the wrong reason. So each is driven to a
    second value, in one node, and the values must actually differ.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)

    shared = RecordingDeliveryPort()
    _drive(delivery=shared)
    _drive(delivery=shared)
    assert shared.sends == 2, "the send counter cannot exceed one, so counting proves nothing"

    codes: set[str] = set()
    for port in (
        RecordingDeliveryPort(),
        RecordingDeliveryPort(outcomes=(DeliveryOutcome.RATE_LIMITED,)),
        RecordingDeliveryPort(raises=True),
        RecordingDeliveryPort(indeterminate_from=0),
    ):
        _, _, trail, _ = _drive(delivery=port)
        codes.add(_delivered_code(trail))
    assert len(codes) == 4, f"the recorded delivery code is not outcome-dependent: {sorted(codes)}"

    def tiny(channel: ChannelId) -> Mapping[str, Any]:
        return {**FIXTURE_CAPABILITY, "maximum_body_characters": 20}

    _, _, short, _ = _drive(capabilities=tiny)
    _, _, full, _ = _drive()
    assert short.stages != full.stages, "the stage trail is a constant, so asserting it is vacuous"
    assert len(short.stages) == 5
    assert len(full.stages) == 6
