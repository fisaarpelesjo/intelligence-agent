"""The isolation user story, through the composed round trip — T127 [US4] (`SC-013`).

`FR-026` to `FR-030`. Four crossings are driven end to end through
`channel_integration.roundtrip.handle`: a conversation reference from another scope, a message
declaring another tenant, a clarification contract bound to another conversation's correlation id,
and interleaved traffic from two principals in two tenants sharing one set of recording doubles.

## What this file adds, and what it deliberately does not repeat

`tests/integration/test_isolation.py` (`T105`) already drives the same crossings through `convert`
and asserts the derivation algebra — same principal on two channels, two principals in one tenant,
a crossed correlation id — and `tests/integration/test_inbound_sequence.py` (`T069`) already
asserts each refusal **at its step** with the resolver and derivation counts behind it. Neither is
restated here.

The value this file adds is the **composed** path, which those two cannot see: the port, the
renderer, the transport and the audit sink now exist below step 7, so a crossed reference has
somewhere to leak *to*. So every assertion below is about the collaborators past the envelope —
`port.calls`, `delivery.calls`, `sink.events` — and the property is that a crossed reference costs
**zero** upstream calls, zero sends and zero recorded events, while the uncrossed traffic that runs
beside it through the *same* doubles is unaffected.

## "Concurrent traffic" is interleaved, and there are no threads. On purpose.

`tests/integration/test_reactive_only.py::test_no_scheduler_timer_or_background_task_exists`
forbids `threading`, `asyncio`, `concurrent`, `sched`, `multiprocessing` and `signal` anywhere
under `src`. That scan is scoped to `src` and would not have stopped this file from importing
`threading` — and this file does not, for two independent reasons.

First, a threaded version of this test would be a **race**, and a race can pass by luck. An
explicit interleaving makes the worst ordering the ordering under test, every run.

Second, and this is the measured part: what concurrency threatens is *shared state*, and the
composed path has none to threaten. Every scoped reference is derived from
`(tenant, channel, principal_ref, provider_reference)` by `identity/scope.py` rather than looked up,
`identity/tenant.py` compares the declared tenant against the binding's rather than caching one, and
`handle` itself holds no module-level container — its only mutable value is the `stages` list, which
is local to the call and copied into a tuple before it is returned. So two flows at the same instant
have nothing to contend over, and the honest instrument is two independent `handle` calls sharing
the **same** recording doubles, run alternately, with the doubles asserted to have kept the two
apart. Sharing the doubles is what makes the interleaving mean something: a single double that
merged, reordered or leaked between flows would show it in `intakes`, `calls` and `events`.

## Two measurements that contradicted what was assumed while writing this

1. **A crossed reference emits nothing at all.** The expectation was a loud audit record of a
   cross-tenant probe. Measured 2026-08-19: `handle` returns `stages == ()` and the sink stays
   empty, because `audit.emit.build_event` needs a correlation id, and step 7c is exactly where the
   crossed reference refuses — the correlation id is never derived, so no compliant event is
   constructible. Nothing is invented to have something to write. This file asserts the silence
   rather than an imagined record, and states the operational consequence plainly: at this layer a
   crossed reference leaves no trail, and detecting the probe is a transport-side concern.
2. **A crossed *principal context* does record.** When the composition itself is handed one sender's
   authorization context together with another sender's envelope, `intake_from_envelope` refuses on
   the principal disagreement — but by then the envelope exists, so three stages have already fired
   and `SUBMITTED` is recorded as the step that did not complete. Four events, not zero. The
   asymmetry is real and is asserted as such: the sender's crossing is invisible here, the
   composition's own crossing is not.

Every node that injects `fixture_capabilities` first calls
`assert_the_production_resolver_still_refuses`, inside `_run`, so no assertion below can be read as
evidence that any channel renders: `D-28` is undeclared and the shipped round trip stops at
`RENDERED`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from analytics_interaction.contracts.clarification import ClarificationContract

from channel_integration.contracts._base import PrincipalRef, TenantId
from channel_integration.contracts.audit import ChannelStage
from channel_integration.contracts.delivery import DeliveryOutcome
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.envelope import ChannelEnvelope
from channel_integration.contracts.identity import ExternalIdentity
from channel_integration.contracts.kinds import MessageKind
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.contracts.refusal import ChannelRefusal
from channel_integration.identity.scope import derive_conversation_ref, derive_correlation_id
from channel_integration.roundtrip import RoundTripResult, handle
from tests.fixtures.channels import (
    AT,
    FIXTURE_MATERIAL,
    RecordingAuditSink,
    RecordingDeliveryPort,
    assert_the_production_resolver_still_refuses,
    bounds_for,
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
from tests.fixtures.interaction import RecordingInteraction, recording_interaction
from tests.fixtures.payloads import payload_for

pytestmark = pytest.mark.integration

_TENANT_A = TenantId("tenant-a")
_TENANT_B = TenantId("tenant-b")
_PRINCIPAL_A = PrincipalRef("principal-ref-a")
_PRINCIPAL_B = PrincipalRef("principal-ref-b")

#: The corpus entry every flow answers with. One entry for every sender, deliberately: if the two
#: senders received *different* answers, "the responses did not cross" could hold because the
#: payloads differ rather than because the routing is sound. Identical payloads make the
#: conversation reference the only thing that can tell one delivery from the other.
_PAYLOAD = "all four claim classes"

#: The question every fixture request carries, read from the fixture rather than restated, so the
#: disclosure check below looks for the text that was actually sent.
_QUESTION = str(wire_payload()["text"])


class _Sender:
    """One sender's whole scope, and the references that scope derives.

    Holds the four values `identity/scope.py` derives from — channel, tenant, principal reference
    and the provider's message id — so no test restates a scope in two places and no assertion can
    end up comparing a reference with itself.
    """

    __slots__ = ("channel", "external", "message_id", "principal_ref", "tenant")

    def __init__(
        self,
        channel: ChannelId,
        tenant: TenantId,
        principal_ref: PrincipalRef,
        message_id: str,
    ) -> None:
        self.channel = channel
        self.tenant = tenant
        self.principal_ref = principal_ref
        self.message_id = message_id
        #: Synthetic and distinct per sender. Never a handle, chat id or address (`FR-077`).
        self.external = ExternalIdentity(f"fixture-external-{principal_ref}-{channel.value}")

    @property
    def conversation(self) -> str:
        """The conversation reference this scope derives, computed independently of the flow."""
        return str(
            derive_conversation_ref(
                fixture_pseudonymiser(),
                self.tenant,
                self.channel,
                self.principal_ref,
                self.message_id,
            )
        )

    @property
    def correlation(self) -> str:
        """The correlation id this scope derives, computed independently of the flow."""
        return str(
            derive_correlation_id(
                fixture_pseudonymiser(),
                self.tenant,
                self.channel,
                self.principal_ref,
                self.message_id,
            )
        )

    def with_message(self, message_id: str) -> _Sender:
        """The same sender's next inbound message. One message, one correlation (`FR-027`)."""
        return _Sender(self.channel, self.tenant, self.principal_ref, message_id)


_A = _Sender(ChannelId.SLACK, _TENANT_A, _PRINCIPAL_A, "provider-message-a1")
_B = _Sender(ChannelId.SLACK, _TENANT_B, _PRINCIPAL_B, "provider-message-b1")


def _run(
    who: _Sender,
    *,
    port: RecordingInteraction | None,
    delivery: RecordingDeliveryPort,
    sink: RecordingAuditSink,
    conversation_presented: str | None = None,
    correlation_presented: str | None = None,
    tenant_declared: TenantId | None = None,
    context_principal: PrincipalRef | None = None,
    kind: MessageKind = MessageKind.TEXT,
) -> RoundTripResult:
    """One whole round trip for ``who``, over doubles the caller may share between senders.

    The doubles are parameters rather than locals precisely so two senders can be given the same
    ones: a shared recorder is the instrument that would reveal a crossing, and a per-call recorder
    could not.
    """
    assert_the_production_resolver_still_refuses(who.channel)
    overrides: dict[str, object] = {
        "tenant": str(tenant_declared if tenant_declared is not None else who.tenant),
        "message_id": who.message_id,
    }
    if conversation_presented is not None:
        overrides["conversation_id"] = conversation_presented
    if correlation_presented is not None:
        overrides["correlation_id"] = correlation_presented

    fixture = payload_for(_PAYLOAD)
    return handle(
        signed_request(who.channel, payload=wire_payload(**overrides)),
        descriptor=descriptor_for(who.channel),
        material=FIXTURE_MATERIAL,
        bounds=bounds_for(who.channel),
        kind=kind,
        external=who.external,
        resolver=CountingIdentityResolver(
            active_binding(channel=who.channel, tenant=who.tenant, principal_ref=who.principal_ref)
        ),
        pseudonymiser=fixture_pseudonymiser(),
        at=AT,
        principal=fixture_principal_context(
            principal_ref=str(
                context_principal if context_principal is not None else who.principal_ref
            )
        ),
        wording=fixture.wording,
        port=port,
        capabilities=fixture_capabilities,
        delivery=delivery,
        sink=sink,
    )


def _clarification_bound_to(correlation: str) -> ClarificationContract:
    """A sealed contract naming ``correlation``, built through ``model_validate``.

    Every nested value is handed over as a plain mapping so `003`'s own models validate it. `Seal`
    and `CandidateRef`'s `LocalizedRef` are construction-only shapes and naming `Seal` here would
    add an upstream import the allowlist does not carry — the same reasoning
    `fixture_principal_context` records about `PrincipalType`, and the reason
    `intake_from_envelope` hands the declared language to `003` as a string.

    The contract is a **carrier**, and this feature never reads it: `roundtrip.py` measured that
    only an `AnalyticsAnswer` renders, so a clarification is held on ``upstream`` unread. What makes
    it interesting for isolation is the one field an attacker would reuse — its correlation id.
    """
    return ClarificationContract.model_validate(
        {
            "contract_version": 1,
            "correlation_id": correlation,
            "interpretation_id": "fixture-interpretation-1",
            "auth_fingerprint": "fixture-auth-fingerprint-1",
            "unresolved": "metric",
            "candidates": (
                {
                    "identifier": "fixture-candidate-1",
                    "slot": "metric",
                    "distinguishing": {
                        "code": "candidate.distinguishing",
                        "language": "pt-BR",
                        "content_version": "fixture-vocabulary-1",
                    },
                },
            ),
            "rounds_consumed": 0,
            "round_bound": 2,
            "issued_at": datetime(2026, 8, 17, 12, 0, tzinfo=UTC),
            "expires_at": datetime(2026, 8, 17, 12, 30, tzinfo=UTC),
            "nonce": "fixture-nonce-not-a-credential",
            "catalog_release": "fixture-catalog-release-1",
            "policy_version": "fixture-policy-1",
            "vocabulary_version": "fixture-vocabulary-1",
            "seal": {
                "key_id": "fixture-key-1",
                "algorithm": "fixture-seal-algorithm",
                "value": "fixture-seal-not-a-real-seal",
            },
        }
    )


def test_interleaved_traffic_from_two_principals_never_crosses() -> None:
    """`SC-013` on the composed path: four `handle` calls, alternating senders, shared doubles.

    The instrument is the sharing. One interaction double, one delivery port and one audit sink
    serve tenant A's principal and tenant B's principal alternately, so any merge, reorder or leak
    between the two flows would be visible in `intakes`, `calls` or `events` rather than hidden
    behind per-flow recorders that cannot contradict each other.

    Four things are asserted, and each has its own failure mode: the submitted intakes stay in the
    order they were submitted, each intake carries its own sender's principal, each delivery went to
    its own sender's derived conversation, and the audit trail partitions by correlation with no
    correlation carrying two tenants.
    """
    port = recording_interaction(payload_for(_PAYLOAD).answer)
    delivery = RecordingDeliveryPort()
    sink = RecordingAuditSink()

    order = (_A, _B, _A.with_message("provider-message-a2"), _B.with_message("provider-message-b2"))
    results = [_run(who, port=port, delivery=delivery, sink=sink) for who in order]

    for who, result in zip(order, results, strict=True):
        assert result.refusal is None, (who.principal_ref, result.refusal)
        assert isinstance(result.envelope, ChannelEnvelope)
        assert result.delivery is DeliveryOutcome.DELIVERED
        assert result.asks == 1
        assert str(result.envelope.tenant) == str(who.tenant)
        assert str(result.envelope.principal_ref) == str(who.principal_ref)
        assert str(result.envelope.conversation_id) == who.conversation

    assert port.calls == 4, "one ask per inbound message, and the double counted them all"
    submitted = [intake.principal.principal_ref for intake in port.intakes]
    assert submitted == [str(who.principal_ref) for who in order], (
        "the shared double saw the intakes in a different order or under a different principal"
    )

    destinations = [conversation for conversation, _ in delivery.calls]
    assert destinations == [who.conversation for who in order]
    assert len(set(destinations)) == 4, "two distinct scopes were answered on one conversation"

    by_correlation: dict[str, set[str]] = {}
    for event in sink.events:
        by_correlation.setdefault(str(event.correlation_id), set()).add(str(event.tenant))
    assert len(by_correlation) == 4, "the four flows did not produce four distinct trails"
    for correlation, tenants in by_correlation.items():
        assert len(tenants) == 1, f"{correlation} carries two tenants: {sorted(tenants)}"


def test_a_crossed_conversation_reference_costs_zero_upstream_calls() -> None:
    """The composed property `T105` could not measure: a crossing reaches **nothing** downstream.

    A's reference presented by B refuses at step 7c, and every collaborator past the envelope is
    asserted untouched — the port was not asked, the transport did not send, and the trail stayed
    exactly as A left it. Asserted against a port that has *already served A once*, so "zero" is a
    statement about the crossing rather than about a double nobody ever reached.

    The empty trail is the measurement recorded in this module's docstring: `stages == ()` and no
    new event, because no correlation id exists to record one against.
    """
    port = recording_interaction(payload_for(_PAYLOAD).answer)
    delivery = RecordingDeliveryPort()
    sink = RecordingAuditSink()

    _run(_A, port=port, delivery=delivery, sink=sink)
    asks_after_a, sends_after_a, events_after_a = port.calls, delivery.sends, len(sink.events)
    assert (asks_after_a, sends_after_a) == (1, 1), "the uncrossed flow did not run"

    crossed = _run(
        _B, port=port, delivery=delivery, sink=sink, conversation_presented=_A.conversation
    )

    assert isinstance(crossed.refusal, ChannelRefusal)
    assert crossed.refusal.code is ChannelReasonCode.CHANNEL_SCOPE_MISMATCH
    assert crossed.refusal.stage is ChannelStage.IDENTIFIED
    assert crossed.envelope is None, "a crossed reference must never become an envelope"
    assert crossed.stages == ()
    assert crossed.asks == 0
    assert port.calls == asks_after_a, "the crossing reached the interaction port"
    assert delivery.sends == sends_after_a, "the crossing reached the transport"
    assert len(sink.events) == events_after_a, "the crossing wrote to the trail"
    assert port.intakes[0].principal.principal_ref == str(_PRINCIPAL_A), (
        "A's intake was altered by B's crossed message"
    )


def test_a_cross_tenant_message_never_reaches_the_port_or_the_trail() -> None:
    """`FR-028` composed: declaring another tenant refuses before submission, at zero cost.

    The wire declares tenant A while the resolved binding says tenant B. `identity/tenant.py`
    compares the two rather than deriving one, which is what makes this a check instead of a
    tautology — and the composed consequence asserted here is that the disagreement is settled
    before any upstream call, send or event exists.
    """
    port = recording_interaction(payload_for(_PAYLOAD).answer)
    delivery = RecordingDeliveryPort()
    sink = RecordingAuditSink()

    result = _run(_B, port=port, delivery=delivery, sink=sink, tenant_declared=_TENANT_A)

    assert isinstance(result.refusal, ChannelRefusal)
    assert result.refusal.code is ChannelReasonCode.CHANNEL_TENANT_MISMATCH
    assert result.refusal.stage is ChannelStage.IDENTIFIED
    assert result.stages == ()
    assert result.asks == 0
    assert port.calls == 0
    assert port.intakes == []
    assert delivery.sends == 0
    assert sink.events == []


def test_a_clarification_bound_to_one_conversation_cannot_be_replayed_into_another() -> None:
    """`FR-030`, `FR-042`: the carrier is transported unread, and its correlation is still scoped.

    Two properties in one node, because they are the same story. First, when the port answers A
    with a clarification, `handle` carries it on ``upstream`` — the identical object, unread and
    unmodified, with `delivery is None` and `asks == 1`, exactly as `roundtrip.py` measured: only an
    `AnalyticsAnswer` renders, and nothing here writes a second renderer.

    Second, the one field of that contract an attacker would reuse is its correlation id. Presenting
    it from B's scope refuses at step 7c and costs the port nothing — so a sealed contract handed to
    one conversation buys no entry into another, and it buys it through derivation rather than
    through a record of who was issued what, because this feature keeps no such record.
    """
    contract = _clarification_bound_to(_A.correlation)
    port = recording_interaction(contract)
    delivery = RecordingDeliveryPort()
    sink = RecordingAuditSink()

    carried = _run(_A, port=port, delivery=delivery, sink=sink)

    assert carried.refusal is None
    assert carried.upstream is contract, "the clarification was not carried as the object received"
    assert carried.presentation is None
    assert carried.delivery is None
    assert delivery.sends == 0, "a clarification is not an answer and must render nothing"
    assert carried.asks == 1
    assert carried.stages == (
        ChannelStage.RECEIVED,
        ChannelStage.VERIFIED,
        ChannelStage.IDENTIFIED,
        ChannelStage.SUBMITTED,
    )
    assert contract.correlation_id == _A.correlation, (
        "the carried contract was rewritten in transit"
    )

    replayed = _run(
        _B,
        port=port,
        delivery=delivery,
        sink=sink,
        correlation_presented=str(contract.correlation_id),
    )

    assert isinstance(replayed.refusal, ChannelRefusal)
    assert replayed.refusal.code is ChannelReasonCode.CHANNEL_SCOPE_MISMATCH
    assert replayed.asks == 0
    assert port.calls == 1, "the replayed contract bought a second upstream call"
    assert delivery.sends == 0


def test_a_principal_context_from_another_sender_is_refused_before_the_port() -> None:
    """The crossing the *composition* can make, rather than the one the sender makes.

    `intake_from_envelope` compares the supplied authorization context's principal against the
    envelope's, because the two are statements about the same principal arriving by different
    routes — the binding resolved one, the caller resolved the other. Handing A's context with B's
    envelope means the question is about to be asked on somebody else's behalf, and it refuses.

    The asymmetry recorded in the module docstring is asserted here: unlike the sender's crossing,
    this one **does** record. The envelope exists by then, so three stages have fired and
    `SUBMITTED` is written as the step that did not complete — four events, not zero — and `asks` is
    still zero, because `submit` checks before it builds anything the port could see.
    """
    port = recording_interaction(payload_for(_PAYLOAD).answer)
    delivery = RecordingDeliveryPort()
    sink = RecordingAuditSink()

    result = _run(_B, port=port, delivery=delivery, sink=sink, context_principal=_PRINCIPAL_A)

    assert isinstance(result.refusal, ChannelRefusal)
    assert result.refusal.code is ChannelReasonCode.CHANNEL_IDENTITY_UNMAPPED
    assert result.refusal.stage is ChannelStage.SUBMITTED
    assert result.asks == 0
    assert port.calls == 0
    assert port.intakes == []
    assert delivery.sends == 0
    assert sink.stages == (
        ChannelStage.RECEIVED,
        ChannelStage.VERIFIED,
        ChannelStage.IDENTIFIED,
        ChannelStage.SUBMITTED,
    )


def test_no_refusal_discloses_anything_about_the_other_conversation() -> None:
    """`FR-026`: the sender projection carries the governed wording and nothing that identifies A.

    `ChannelRefusal.sender_text` returns `message_pt_br` alone — the detail class, the stage and the
    code taxonomy stay out by construction — and this node holds the composed path to that by
    searching the transmitted text for every value that belongs to the other conversation.

    The crossed and the invented reference are additionally required to be **textually identical**.
    Otherwise the difference between the two answers tells a prober which conversations are real,
    which is the disclosure the scope check exists to close rather than to relocate.
    """
    port = recording_interaction(payload_for(_PAYLOAD).answer)
    delivery = RecordingDeliveryPort()
    sink = RecordingAuditSink()

    crossed = _run(
        _B, port=port, delivery=delivery, sink=sink, conversation_presented=_A.conversation
    )
    invented = _run(
        _B, port=port, delivery=delivery, sink=sink, conversation_presented="never-issued-anywhere"
    )
    correlated = _run(
        _B, port=port, delivery=delivery, sink=sink, correlation_presented=_A.correlation
    )
    tenanted = _run(_B, port=port, delivery=delivery, sink=sink, tenant_declared=_TENANT_A)

    needles = (
        _A.conversation,
        _A.correlation,
        _A.message_id,
        str(_PRINCIPAL_A),
        str(_TENANT_A),
        str(_A.external),
        _QUESTION,
    )
    for label, result in (
        ("crossed conversation", crossed),
        ("invented conversation", invented),
        ("crossed correlation", correlated),
        ("declared tenant", tenanted),
    ):
        assert isinstance(result.refusal, ChannelRefusal), label
        text = result.refusal.sender_text()
        leaked = [needle for needle in needles if needle in text]
        assert not leaked, f"the {label} refusal discloses {leaked}"

    assert isinstance(crossed.refusal, ChannelRefusal)
    assert isinstance(invented.refusal, ChannelRefusal)
    assert crossed.refusal.sender_text() == invented.refusal.sender_text()
    assert crossed.refusal.code is invented.refusal.code


def test_the_instrument_can_fail() -> None:
    """Anti-vacuity, in three parts, because each zero above could be zero for a boring reason.

    A test asserting "the port was not reached" proves nothing if the harness never reaches the port
    at all; one asserting "A's reference is absent from B's refusal" proves nothing if that
    reference is a string the system never produces; and one asserting "the two flows did not cross"
    proves nothing if the two scopes derive the same reference anyway.

    So this node measures the positive of each: the same `_run` over the same doubles does move
    every counter when nothing is crossed, A's conversation reference genuinely appears in A's own
    delivery destination, and the two senders' references genuinely differ.
    """
    port = recording_interaction(payload_for(_PAYLOAD).answer)
    delivery = RecordingDeliveryPort()
    sink = RecordingAuditSink()

    assert port.calls == 0
    assert delivery.sends == 0
    assert sink.events == []

    result = _run(_A, port=port, delivery=delivery, sink=sink)

    assert result.asks == 1
    assert port.calls == 1
    assert delivery.sends == 1
    assert len(sink.events) == 6, "the uncrossed flow did not fire the six stages"

    destination, _ = delivery.calls[0]
    assert destination == _A.conversation, (
        "A's own reference is not the string the transport received, so asserting its absence "
        "from B's refusal would be asserting the absence of something that never existed"
    )
    assert _A.conversation != _B.conversation
    assert _A.correlation != _B.correlation
