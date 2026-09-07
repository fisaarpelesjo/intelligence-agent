"""The composed round trip — T122 (`SC-014`, `SC-016`; ADR 0017, ADR 0019).

```
handle(raw, ...) -> RoundTripResult
    convert (steps 1-7) -> submit -> render -> preserve -> deliver
```

One inbound message in, one governed outcome out, with the six audit stages firing in the accepted
order. Every collaborator is injected and there is **no clock**: the instant arrives as `at`, the
same way `convert` takes it, so a simulator, a test and a real listener drive identical code.

## Why this is a new module and not a step inside `convert`

`T122` names `inbound/convert.py` and `delivery/attempt.py`. Those are the two **endpoints** the
round trip runs between, and the wiring lives above both of them rather than inside either.

Putting submission inside `convert` was considered and rejected on a measurement, not a preference.
`convert`'s docstring states the guarantee — "this function stops at the envelope, so nothing here
can reach the interaction port even by accident" — and
`tests/integration/test_inbound_sequence.py::test_step_8_is_absent_and_the_absence_is_the_point`
asserts it: no parameter of `convert` names a port, and the string `InteractionPort` does not occur
in its source. That is a **permanent property**, not a premise that expires when Phase D arrives:
an inbound conversion that could submit is an inbound conversion whose purity nobody can check.

So step 8 stays absent from `convert`, that test needs no maintenance amendment, and the composition
that does reach the port is a separate module whose whole purpose is to be looked at.

## What cannot be recorded before identity, and what follows from that

`audit.emit.build_event` requires a tenant, a principal reference, a correlation id and a message
key. None of the four is resolved until step 7 — the tenant and the message key come from the wire
shape at step 5, the principal from the binding at step 7, and the correlation id from scope
derivation after it. **Measured 2026-08-19: no compliant audit event is constructible for a refusal
at steps 1 to 7.**

This module therefore emits **nothing** for such a refusal, and returns it with an empty stage
trail. It does not invent a placeholder tenant, a synthetic correlation id or an "unknown"
principal to have something to write: those are governed values, and authoring one to satisfy a
record would make the record false in exactly the field an operator would trust.

Nor is such a refusal **delivered**. Delivery needs a destination, `destination_for` derives one
from the envelope, and a message that never became an envelope has no verified conversation to
answer. A refusal before identity is returned to the caller that holds the transport; it is not
transmitted from here.

## Two collaborators `004` cannot construct, and does not fake

* ``principal`` — a full `PrincipalContext`. `interaction/port.py` records why: an envelope carries
  a `principal_ref` and nothing in this feature resolves the authorization scope, the granted tags
  or the policy pin. Passed in, never defaulted.
* ``wording`` — a `ResolvedWording`. The payload protocols require one, and `InteractionPort.ask`
  does not return one: `003` resolves governed wording and this feature renders what it resolved.
  Passed in for the same reason, and resolving it here would make `004` a second wording authority.

Both are positional-or-keyword with **no default**, so omitting one is a `TypeError` from the
language rather than a silent substitution.

## The capability matrix is injected, and production's still refuses

Rendering needs the channel's declared capability entry, and `governance.capabilities.
resolve_capability_matrix` is what resolves one. **`D-28` is undeclared, so that function refuses
for every channel** — measured 2026-08-19. The round trip therefore stops at `RENDERED` in
production, and that is the shipped state, not a defect of this module.

So ``capabilities`` is injected, exactly as ``material``, ``bounds``, ``resolver`` and
``pseudonymiser`` are. Production passes `resolve_capability_matrix` and gets the refusal the
undeclared decision requires. A test passes a fixture resolver and exercises the wiring past that
point — which measures the composition, and measures nothing about readiness: no flag, environment
setting or deployment mode reaches a fixture resolver, and `compliance.readiness` still reports the
`D-28` lock as unsatisfied regardless of what any test injected.

`cli/simulate.py` deliberately does the opposite and calls `render_for_channel`, so the simulator
can never report a rendering that cannot happen. Both are right: a simulator speaks to an operator
about production, and this parameter speaks to a caller about its own collaborators.

## Only an answer renders

`outbound/render.py` exposes `render_for_channel(payload: GovernedAnswerPayload, ...)`. Measured
2026-08-19, there is no rendering path for a clarification or for an upstream refusal. So when the
port returns one of those, this module **carries it and delivers nothing** — `upstream` holds the
object exactly as it arrived, unread and unmodified, which is what a byte-identical clarification
round trip requires of the transport half (`FR-042`). The absence is recorded here rather than
closed by writing a second renderer this feature was never authorized to author.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from analytics_interaction.contracts.answer import AnalyticsAnswer

from .audit.emit import ChannelAuditSink, build_event, emit
from .contracts._base import ChannelViolation
from .contracts.audit import ChannelStage, DetailClass
from .contracts.delivery import DeliveryOutcome, outcome_reason_code
from .contracts.envelope import ChannelEnvelope
from .contracts.reason_codes import ChannelReasonCode
from .contracts.refusal import ChannelRefusal, refusal_from_violation
from .delivery.attempt import deliver_once
from .governance.resolve import ContentUnresolvable
from .inbound.convert import convert
from .interaction.port import InteractionPort, submit
from .outbound.preserve import assert_preserved
from .outbound.render import render_answer

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from analytics_interaction.contracts.intake import PrincipalContext

    from .contracts.descriptor import ChannelDescriptor, ChannelId
    from .contracts.identity import ExternalIdentity
    from .contracts.kinds import MessageKind
    from .contracts.presentation import RenderedPresentation
    from .delivery.ports import DeliveryPort
    from .governance.bounds import TransportBounds
    from .identity.pseudonymise import PseudonymPort
    from .identity.resolve import ChannelIdentityResolver
    from .inbound.schemes import VerificationMaterial
    from .outbound.payload import GovernedAnswerPayload, ResolvedWording

__all__ = ["CapabilityResolver", "RoundTripResult", "handle"]


class CapabilityResolver(Protocol):
    """Resolves one channel's declared capability entry, or refuses.

    A `Protocol` over the one call rather than the concrete function, so the production resolver and
    a fixture one are the same shape and neither is reachable from the other by default.
    """

    def __call__(self, channel: ChannelId) -> Mapping[str, Any]:
        """The entry, or raise a `ChannelViolation` when the governed decision is undeclared."""
        ...


#: The three stages `convert` clears when it returns an envelope, in the accepted order. Named here
#: so the emission below reads as the sequence it is rather than as three separate calls.
_CLEARED_BY_CONVERSION = (
    ChannelStage.RECEIVED,
    ChannelStage.VERIFIED,
    ChannelStage.IDENTIFIED,
)


class _AnswerPayload:
    """An answer and its already-resolved wording, bound together for rendering.

    A local structure rather than a contract: `GovernedAnswerPayload` is a `Protocol`, both halves
    arrive from elsewhere, and this only carries them side by side. It reads neither, so nothing
    here can alter what `003` produced.
    """

    __slots__ = ("answer", "wording")

    def __init__(self, answer: AnalyticsAnswer, wording: ResolvedWording) -> None:
        self.answer = answer
        self.wording = wording


class RoundTripResult:
    """What one inbound message produced, and how far it got.

    ``stages`` is the trail that actually fired, in order — not the stages the path *would* have
    fired. An operator reading it learns where the message stopped, which is the question a trail
    exists to answer.
    """

    __slots__ = ("asks", "delivery", "envelope", "presentation", "refusal", "stages", "upstream")

    def __init__(
        self,
        *,
        envelope: ChannelEnvelope | None,
        refusal: ChannelRefusal | None,
        upstream: object | None,
        presentation: RenderedPresentation | None,
        delivery: DeliveryOutcome | None,
        stages: tuple[ChannelStage, ...],
        asks: int,
    ) -> None:
        self.envelope = envelope
        self.refusal = refusal
        #: Whatever the port returned, held unread. `None` when the port was never reached.
        self.upstream = upstream
        self.presentation = presentation
        self.delivery = delivery
        self.stages = stages
        #: How many times the interaction port was reached. **At most one per message** (`SC-048`),
        #: counted rather than asserted, because `T134` reads a number.
        self.asks = asks

    def __repr__(self) -> str:  # pragma: no cover - failure readability
        last = self.stages[-1].value if self.stages else "none"
        return f"RoundTripResult(last_stage={last}, asks={self.asks}, refused={bool(self.refusal)})"


def _refusal_for(
    violation: ChannelViolation | ContentUnresolvable, stage: ChannelStage
) -> ChannelRefusal:
    """One governed refusal, from either violation base, at ``stage``.

    `ContentUnresolvable` is not a `ChannelViolation` and `refusal_from_violation` takes one, so it
    is converted through its carried code rather than reported as a different kind of failure.
    """
    if isinstance(violation, ChannelViolation):
        return refusal_from_violation(violation, stage, _detail_class_of(violation))
    return refusal_from_violation(
        ChannelViolation(violation.code, violation.detail), stage, DetailClass.NONE
    )


def _detail_class_of(violation: ChannelViolation) -> DetailClass:
    """The operator-facing class a violation carries, when it carries one."""
    return getattr(violation, "detail_class", DetailClass.NONE)


def _record(
    sink: ChannelAuditSink,
    stage: ChannelStage,
    envelope: ChannelEnvelope,
    external: ExternalIdentity,
    pseudonymiser: PseudonymPort,
    code: ChannelReasonCode,
    detail_class: DetailClass = DetailClass.NONE,
) -> None:
    """One stage, recorded before the step it names is reported as done.

    Emission is synchronous and raises `AuditEmissionFailed` when the sink does not durably accept.
    That exception is deliberately **not** caught here: `FR-083` forbids releasing what cannot be
    recorded, and swallowing it would let a delivery proceed against a trail that never took it.
    """
    emit(
        sink,
        build_event(
            stage=stage,
            channel=envelope.channel,
            tenant=envelope.tenant,
            principal_ref=envelope.principal_ref,
            correlation_id=envelope.correlation_id,
            message_key=envelope.message_id,
            code=code,
            pseudonymiser=pseudonymiser,
            external=external,
            detail_class=detail_class,
        ),
    )


def handle(  # every collaborator is injected; see the module docstring
    raw: object,
    *,
    descriptor: ChannelDescriptor,
    material: VerificationMaterial | None,
    bounds: TransportBounds,
    kind: MessageKind,
    external: ExternalIdentity,
    resolver: ChannelIdentityResolver,
    pseudonymiser: PseudonymPort,
    at: datetime,
    principal: PrincipalContext,
    wording: ResolvedWording,
    port: InteractionPort | None,
    capabilities: CapabilityResolver,
    delivery: DeliveryPort,
    sink: ChannelAuditSink,
) -> RoundTripResult:
    """Convert, submit once, render, prove preservation, deliver. Total.

    Every governed path returns a :class:`RoundTripResult`. **Two** exceptions escape, and both are
    stated because a docstring claiming totality while two things escape is worse than no claim.

    `AuditEmissionFailed` is not an outcome — it is the record failing, and the caller must withhold
    rather than receive something that looks like a result.

    `pydantic.ValidationError` from `003`'s own contract escapes when the question violates a field
    rule this feature does not own. Measured 2026-08-19: `QuestionIntake.text` declares a maximum
    length, `004` enforces no inbound size bound below the structural ceiling `inbound/parse.py`
    declares, and neither number — nor the ceiling's own name — is restated here.
    `tests/contract/test_no_hardcoded_bounds.py` is why: it caught the first draft of this
    paragraph twice, once for quoting both numbers and once for naming the constant. So a body
    inside the structural ceiling can
    carry a question past `003`'s cap, and the failure surfaces where it is decided — three
    stages already on the record, nothing sent. This is the
    same mechanism the declared language uses (see `intake_from_envelope`): the governed set belongs
    upstream, so upstream's model decides and upstream's error is what is raised. Catching it here
    would mean choosing a `ChannelReasonCode` for an upstream field rule, which is this layer
    authoring a governed value about a limit it does not own.

    `tests/integration/test_flow_story.py` asserts both escapes, so neither can change unnoticed.
    """
    converted = convert(
        raw,
        descriptor=descriptor,
        material=material,
        bounds=bounds,
        kind=kind,
        external=external,
        resolver=resolver,
        pseudonymiser=pseudonymiser,
        at=at,
    )
    if isinstance(converted, ChannelRefusal):
        # Steps 1 to 7 refused, so no compliant event and no verified destination exist. See the
        # module docstring: nothing is emitted and nothing is transmitted.
        return RoundTripResult(
            envelope=None,
            refusal=converted,
            upstream=None,
            presentation=None,
            delivery=None,
            stages=(),
            asks=0,
        )

    envelope = converted
    stages: list[ChannelStage] = []
    for stage in _CLEARED_BY_CONVERSION:
        _record(
            sink,
            stage,
            envelope,
            external,
            pseudonymiser,
            ChannelReasonCode.CHANNEL_MESSAGE_ACCEPTED,
        )
        stages.append(stage)

    # --- step 8: the single submission. One ask, or none. ------------------------------
    try:
        upstream = submit(envelope, principal, port=port)
    except ChannelViolation as violation:
        # The boundary is unavailable, which is a governed outcome and not a transport error. It is
        # recorded at SUBMITTED because that is the step that did not complete.
        _record(
            sink,
            ChannelStage.SUBMITTED,
            envelope,
            external,
            pseudonymiser,
            violation.code,
            _detail_class_of(violation),
        )
        stages.append(ChannelStage.SUBMITTED)
        return RoundTripResult(
            envelope=envelope,
            refusal=_refusal_for(violation, ChannelStage.SUBMITTED),
            upstream=None,
            presentation=None,
            delivery=None,
            stages=tuple(stages),
            asks=0,
        )

    _record(
        sink,
        ChannelStage.SUBMITTED,
        envelope,
        external,
        pseudonymiser,
        ChannelReasonCode.CHANNEL_MESSAGE_ACCEPTED,
    )
    stages.append(ChannelStage.SUBMITTED)

    if not isinstance(upstream, AnalyticsAnswer):
        # A clarification or an upstream refusal. Carried, never rendered here — see the module
        # docstring. `asks` is one: the port was reached and it answered.
        return RoundTripResult(
            envelope=envelope,
            refusal=None,
            upstream=upstream,
            presentation=None,
            delivery=None,
            stages=tuple(stages),
            asks=1,
        )

    # --- render, then prove the rendering preserved the payload ------------------------
    payload: GovernedAnswerPayload = _AnswerPayload(upstream, wording)
    try:
        capability = capabilities(envelope.channel)
        rendered = render_answer(payload, envelope.channel, capability)
        presentation = assert_preserved(rendered, payload, capability)
    except (ChannelViolation, ContentUnresolvable) as violation:
        # Either the capability is unresolvable, the payload is not expressible on this channel, or
        # what was rendered diverged from what `003` produced. Two exception bases, because an
        # undeclared governed document raises `ContentUnresolvable`, a `ValueError` carrying the
        # document's own code rather than a `ChannelViolation` — catching one of the two would let
        # the most likely refusal on this path escape as an unhandled error and break
        # totality. All three withhold at `RENDERED`:
        # `FR-049` makes divergence a governed refusal, and delivering the divergent text — or text
        # rendered against a capability nobody declared — would be the failure itself.
        _record(
            sink,
            ChannelStage.RENDERED,
            envelope,
            external,
            pseudonymiser,
            violation.code,
            _detail_class_of(violation)
            if isinstance(violation, ChannelViolation)
            else DetailClass.NONE,
        )
        stages.append(ChannelStage.RENDERED)
        return RoundTripResult(
            envelope=envelope,
            refusal=_refusal_for(violation, ChannelStage.RENDERED),
            upstream=upstream,
            presentation=None,
            delivery=None,
            stages=tuple(stages),
            asks=1,
        )

    _record(
        sink,
        ChannelStage.RENDERED,
        envelope,
        external,
        pseudonymiser,
        ChannelReasonCode.CHANNEL_MESSAGE_ACCEPTED,
    )
    stages.append(ChannelStage.RENDERED)

    # --- deliver once. `deliver_once` is total, so this reports rather than raises. -----
    attempt = deliver_once(delivery, presentation, envelope)
    _record(
        sink,
        ChannelStage.DELIVERED,
        envelope,
        external,
        pseudonymiser,
        outcome_reason_code(attempt.outcome),
    )
    stages.append(ChannelStage.DELIVERED)

    return RoundTripResult(
        envelope=envelope,
        refusal=None,
        upstream=upstream,
        presentation=presentation,
        delivery=attempt.outcome,
        stages=tuple(stages),
        asks=1,
    )
