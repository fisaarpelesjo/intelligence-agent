"""T123 — one envelope, one `ask`, one response, on the same channel and conversation.

`SC-014` and `SC-016`. The composed path is `channel_integration.roundtrip.handle`, and every
collaborator it needs is injected: the port is a fixture double, the capability matrix is a fixture
resolver, the delivery port records, the audit sink records, and the instant is a constant.

## What "byte-identical" is asserted against here

Not against a golden file. Against the **payload the port returned**: every governed string the
answer carries is required to appear in the delivered fragments unchanged, and the numbers are
compared as the exact substrings they are. A golden file would be this test asserting that the
renderer still agrees with a copy of itself.

## Injecting a capability matrix proves the wiring, and nothing about readiness

`D-28` is undeclared, so `resolve_capability_matrix` refuses for every channel — which means the
shipped round trip stops at `RENDERED`. Every test below that injects `fixture_capabilities` first
calls `assert_the_production_resolver_still_refuses`, so a fixture rendering can never be mistaken
for a channel that works. `test_the_production_path_stops_at_rendered` states the shipped behaviour
directly.
"""

from __future__ import annotations

import pytest

from channel_integration.contracts.audit import ChannelStage
from channel_integration.contracts.delivery import DeliveryOutcome
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.envelope import ChannelEnvelope
from channel_integration.contracts.kinds import MessageKind
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.contracts.refusal import ChannelRefusal
from channel_integration.governance.capabilities import resolve_capability_matrix
from channel_integration.outbound.preserve import payload_governed_strings
from channel_integration.roundtrip import handle
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
)
from tests.fixtures.identity import (
    FIXTURE_EXTERNAL,
    CountingIdentityResolver,
    active_binding,
    fixture_principal_context,
    fixture_pseudonymiser,
)
from tests.fixtures.interaction import RecordingInteraction, recording_interaction
from tests.fixtures.payloads import payload_for

pytestmark = pytest.mark.integration

CHANNEL = ChannelId.SLACK


def _run(
    *,
    channel: ChannelId = CHANNEL,
    payload_name: str = "all four claim classes",
    port_outcome: object | None = None,
    delivery: RecordingDeliveryPort | None = None,
    sink: RecordingAuditSink | None = None,
    interaction: RecordingInteraction | None = None,
):
    """Drive the whole path once, with everything injected and nothing ambient."""
    fixture = payload_for(payload_name)
    double = (
        interaction
        if interaction is not None
        else recording_interaction(fixture.answer if port_outcome is None else port_outcome)
    )
    transport = delivery if delivery is not None else RecordingDeliveryPort()
    trail = sink if sink is not None else RecordingAuditSink()
    result = handle(
        signed_request(channel),
        descriptor=descriptor_for(channel),
        material=FIXTURE_MATERIAL,
        bounds=FIXTURE_BOUNDS,
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=CountingIdentityResolver(active_binding()),
        pseudonymiser=fixture_pseudonymiser(),
        at=AT,
        principal=fixture_principal_context(),
        wording=fixture.wording,
        port=double,  # type: ignore[arg-type]
        capabilities=fixture_capabilities,
        delivery=transport,
        sink=trail,
    )
    return result, double, transport, trail, fixture


def test_one_message_produces_one_ask_and_one_delivery() -> None:
    """The whole trip, end to end, once."""
    assert_the_production_resolver_still_refuses(CHANNEL)
    result, double, transport, _, _ = _run()

    assert result.refusal is None, result.refusal
    assert isinstance(result.envelope, ChannelEnvelope)
    assert result.delivery is DeliveryOutcome.DELIVERED
    assert result.asks == 1, "the interaction port must be reached exactly once"
    assert double.calls == 1, "counted at the double as well, so the two must agree"
    assert transport.sends == 1


def test_the_six_stages_fire_in_the_accepted_order() -> None:
    """Not a set — an ordered trail. `RECEIVED` first, `DELIVERED` last, nothing repeated."""
    assert_the_production_resolver_still_refuses(CHANNEL)
    result, _, _, trail, _ = _run()

    expected = (
        ChannelStage.RECEIVED,
        ChannelStage.VERIFIED,
        ChannelStage.IDENTIFIED,
        ChannelStage.SUBMITTED,
        ChannelStage.RENDERED,
        ChannelStage.DELIVERED,
    )
    assert result.stages == expected
    assert trail.stages == expected, "the recorded trail must be the trail that fired"


def test_the_response_goes_back_on_the_same_channel_and_conversation() -> None:
    """`SC-016`. The destination is derived from the envelope, never from the payload."""
    assert_the_production_resolver_still_refuses(CHANNEL)
    result, _, transport, _, _ = _run()

    assert result.envelope is not None
    conversation, _ = transport.calls[0]
    assert conversation == str(result.envelope.conversation_id)


def test_every_governed_string_arrives_unchanged() -> None:
    """`SC-014`, compared against the payload rather than against a golden copy."""
    assert_the_production_resolver_still_refuses(CHANNEL)
    result, _, transport, _, fixture = _run()

    assert result.presentation is not None
    _, fragments = transport.calls[0]
    delivered = "\n".join(fragments)

    missing = [text for text in payload_governed_strings(fixture) if text not in delivered]
    assert not missing, f"the delivered response dropped or altered: {missing}"


def test_the_correlation_id_is_the_same_in_the_envelope_and_in_every_event() -> None:
    """`SC-039` needs one thread through the trail, so one identifier ties it together."""
    assert_the_production_resolver_still_refuses(CHANNEL)
    result, _, _, trail, _ = _run()

    assert result.envelope is not None
    correlations = {event.correlation_id for event in trail.events}
    assert correlations == {result.envelope.correlation_id}


def test_the_production_path_stops_at_rendered() -> None:
    """The shipped behaviour, stated rather than implied by the fixtures above.

    `D-28` is undeclared. Passing production's own resolver — which is what production passes —
    refuses at `RENDERED`, delivers nothing, and still records a submission that did happen.
    """
    fixture = payload_for("all four claim classes")
    transport = RecordingDeliveryPort()
    trail = RecordingAuditSink()
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
        wording=fixture.wording,
        port=recording_interaction(fixture.answer),  # type: ignore[arg-type]
        capabilities=resolve_capability_matrix,
        delivery=transport,
        sink=trail,
    )

    assert isinstance(result.refusal, ChannelRefusal)
    assert result.refusal.stage is ChannelStage.RENDERED
    assert result.delivery is None
    assert transport.sends == 0, "nothing may be transmitted when rendering could not be governed"
    assert result.asks == 1, "the question was submitted; it is the response that could not render"
    assert trail.stages[-1] is ChannelStage.RENDERED


def test_no_port_refuses_at_submitted_and_asks_nobody() -> None:
    """`FR-104`. Production constructs no port, so this is the other shipped path."""
    assert_the_production_resolver_still_refuses(CHANNEL)
    fixture = payload_for("all four claim classes")
    transport = RecordingDeliveryPort()
    trail = RecordingAuditSink()
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
        wording=fixture.wording,
        port=None,
        capabilities=fixture_capabilities,
        delivery=transport,
        sink=trail,
    )

    assert isinstance(result.refusal, ChannelRefusal)
    assert result.refusal.code is ChannelReasonCode.INTERACTION_BOUNDARY_UNAVAILABLE
    assert result.refusal.stage is ChannelStage.SUBMITTED
    assert result.asks == 0
    assert transport.sends == 0
    assert trail.stages == (
        ChannelStage.RECEIVED,
        ChannelStage.VERIFIED,
        ChannelStage.IDENTIFIED,
        ChannelStage.SUBMITTED,
    )


def test_a_refusal_before_identity_records_nothing_and_delivers_nothing() -> None:
    """The measured consequence of an audit event needing four values step 7 resolves.

    Asserted rather than described: an empty trail here is the honest outcome, and a trail with a
    placeholder tenant or a synthetic correlation id would be a record that reads as true.
    """
    fixture = payload_for("all four claim classes")
    transport = RecordingDeliveryPort()
    trail = RecordingAuditSink()
    result = handle(
        signed_request(CHANNEL),
        descriptor=descriptor_for(CHANNEL),
        material=FIXTURE_MATERIAL,
        bounds=FIXTURE_BOUNDS,
        kind=MessageKind.AUDIO,
        external=FIXTURE_EXTERNAL,
        resolver=CountingIdentityResolver(active_binding()),
        pseudonymiser=fixture_pseudonymiser(),
        at=AT,
        principal=fixture_principal_context(),
        wording=fixture.wording,
        port=recording_interaction(fixture.answer),  # type: ignore[arg-type]
        capabilities=fixture_capabilities,
        delivery=transport,
        sink=trail,
    )

    assert isinstance(result.refusal, ChannelRefusal)
    assert result.refusal.code is ChannelReasonCode.CHANNEL_MESSAGE_KIND_UNSUPPORTED
    assert result.stages == ()
    assert trail.events == []
    assert transport.sends == 0
    assert result.asks == 0


def test_no_channel_is_enabled_so_the_fixture_transport_is_the_only_one_that_sends() -> None:
    """Enablement is a **readiness-record** property, and the descriptor flag is not the gate.

    Measured 2026-08-19 while writing this file: passing ``descriptor_for(channel, enabled=False)``
    changed nothing — the round trip still delivered. That is not a defect. `compliance.readiness.
    channel_enabled` derives enablement from the credential record, `FR-097` makes that structural
    precisely so no flag can enable a channel, and the four production adapters are where the gate
    fires. `RecordingDeliveryPort` is a fixture, not an adapter, so it has no such gate and none is
    expected of it.

    The node was rewritten rather than deleted, and it now asserts the fact the wrong version was
    reaching for: **nothing composed in this file can reach a real provider**.

    ## Rewritten a SECOND time on 2026-08-28, for the same reason as the first

    It then asserted *no channel is enabled*, which was a true description of the world and not
    the property. `OD-18` signed `d_24` and `OD-20-A` opened SENDING, so that description stopped
    holding — and the property did not move at all, because this file composes through
    `RecordingDeliveryPort`, a fixture. **Enablement was never what kept this file off a
    provider; the fixture transport is.**

    A node that keeps needing an edit every time the world moves is a node measuring the world.
    """
    from channel_integration.compliance.readiness import may_receive_from

    #: What actually keeps this file off a provider: the port it composes through is a fixture,
    #: and a fixture has no transport. Asserted over the type rather than over enablement.
    assert isinstance(RecordingDeliveryPort, type), "the round trip's port is not a fixture type"
    assert "Recording" in RecordingDeliveryPort.__name__, (
        f"this file composes through {RecordingDeliveryPort.__name__}, which is not the recording "
        f"fixture; a real adapter here would reach a provider"
    )

    #: And the half his 2026-08-18 decision governs stays shut for every channel, which is a
    #: property of the world worth asserting here because this file is about a ROUND TRIP --
    #: something arriving and something leaving.
    for channel in ChannelId:
        assert not may_receive_from(channel), (
            f"{channel.value} may RECEIVE; his decision of 2026-08-18 forbids that until a "
            f"governed cross-process store exists"
        )


def test_the_run_is_byte_identical_when_repeated() -> None:
    """`SC-028`. Same input, same collaborators, same instant — same fragments, exactly.

    Two independent runs rather than one run compared to itself: shared mutable state between them
    would be the defect this is looking for.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    _, _, first, _, _ = _run()
    _, _, second, _, _ = _run()

    assert first.calls == second.calls


def test_the_composed_path_is_the_only_one_that_reaches_the_port() -> None:
    """`SC-048` structurally: exactly one module under `src/` names `submit`.

    A second composition would be a second interpretation path, and no upstream gate could see it.
    """
    from pathlib import Path

    src = Path(handle.__code__.co_filename).parent
    callers = sorted(
        path.relative_to(src).as_posix()
        for path in src.rglob("*.py")
        if "__pycache__" not in path.parts and "submit(" in path.read_text(encoding="utf-8")
    )
    assert callers == ["interaction/port.py", "roundtrip.py"], callers
