"""T124 — the composed path fails closed, and the refusal discloses nothing (`SC-003`, `SC-053`).

`SC-003`: 100% of the inbound authenticity corpus is refused with a governed code and zero are
processed. `SC-053`: while a channel's credential record is undeclared, 100% of messages for that
channel refuse and zero partial, degraded or sandbox modes are reachable.

## Why this drives `roundtrip.handle` rather than `convert`

`tests/integration/test_inbound_sequence.py` (T069) already asserts, step by step, that `convert`
refuses each of these conditions at its required stage with its own code, and
`tests/security/test_disclosure_symmetry.py` (T063) already asserts that the identity collapse and
three signature modes are byte-identical for a sender. `tests/adversarial/test_signature_attacks.py`
already walks replay, cross-channel and retired-material attacks — also against `convert`. Repeating
any of that here would be coverage theatre, and none of those nodes is duplicated below.

What no existing file measures is the **whole composed path**. A refusal is only fail-closed if
nothing downstream of it happens either, and "downstream" only exists once conversion, submission,
rendering and delivery are wired together. So every node below drives
`channel_integration.roundtrip.handle` and asserts the three zero-counts that `convert` cannot even
express: **zero `ask`**, **zero send**, and — for the pre-identity refusals, which is all seven of
them — **zero audit events**.

The empty trail is not an oversight being tolerated. `roundtrip.py` records the measurement:
`audit.emit.build_event` requires a tenant, a principal reference, a correlation id and a message
key, and none of the four is resolved before step 7. A refusal at steps 1 to 7 therefore emits
nothing and returns `stages == ()`. Inventing a placeholder tenant or a synthetic correlation id to
have something to write would make the record false in exactly the field an operator would trust,
so the honest outcome is asserted instead of the comfortable one.

## The fixture capability resolver is injected **so that "zero send" has teeth**

Injecting it is what makes the assertion falsifiable, and that is the whole reason it is here.
`D-28` is undeclared, so production's `resolve_capability_matrix` refuses for every channel and the
shipped round trip stops at `RENDERED` — which means that if this file passed production's resolver,
`transport.sends == 0` would hold for **every** input, defect or not, and would prove nothing about
refusing. With `fixture_capabilities` injected, a message that wrongly got past its refusal really
would render and really would be transmitted, so a zero send count is a measurement rather than a
consequence of an undeclared decision. `_run` calls `assert_the_production_resolver_still_refuses`
on every single run — inside the helper rather than in each node, so it cannot be forgotten — and
`test_the_harness_delivers_when_nothing_is_wrong` is the anti-vacuity anchor that proves the harness
can in fact ask, render and send.

## The "disabled channel" member: the task's wording implies a flag, the measurement refutes it

`T124` names "the disabled channel" alongside the authenticity corpus, which reads as though
`ChannelDescriptor.enabled=False` were a refusal condition inside the composed path. **It is not.**
Measured 2026-08-19 while writing this file: `handle` with `descriptor_for(channel, enabled=False)`
converts, submits, renders and delivers — byte-identically to the enabled descriptor, same stages,
same fragments. `convert` never reads the flag and neither does `handle`.

That is not a defect. Enablement is a **readiness-record** property:
`compliance.readiness.channel_enabled` derives it from the credential record, `FR-097` makes that
structural precisely so that no flag, file or environment variable can enable a channel, and the
gate lives in the four production adapter builders. So this file asserts the true thing in two
nodes — that `channel_enabled` is `False` for all four channels and that each production builder
refuses with `CHANNEL_NOT_CONFIGURED`, **while holding a resolver that does yield material**, which
is what separates "gated by readiness" from "happens to have no key". `RecordingDeliveryPort` is a
fixture, not an adapter, and no such gate is expected of it.

## Disclosing nothing, asserted as a sweep rather than as an adjective

`ChannelRefusal.sender_text()` returns the stored pt-BR wording alone. Every member of the corpus is
swept against a forbidden-term set assembled from the things that could actually leak here: the
seven `D-26` bound values and the two governed policy strings, the tenant, the principal reference
and the external identity, every `ChannelReasonCode`, `DetailClass` and `ChannelStage` value, the
fixture secret and the retired key, the provider header names and scheme names, the sender's own
question text, the developer-facing `ChannelViolation.detail` strings copied verbatim from `src`,
and the vocabulary of an error. Plus a blanket rule that no digit appears at all, which is the
sharpest available statement of "names no governed limit".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from channel_integration.adapters.generic.delivery import build_generic_delivery
from channel_integration.adapters.slack.delivery import build_slack_delivery
from channel_integration.adapters.telegram.delivery import build_telegram_delivery
from channel_integration.adapters.whatsapp.delivery import build_whatsapp_delivery
from channel_integration.compliance.readiness import channel_enabled
from channel_integration.contracts._base import ChannelViolation
from channel_integration.contracts.audit import ChannelStage, DetailClass
from channel_integration.contracts.delivery import DeliveryOutcome
from channel_integration.contracts.descriptor import ChannelDescriptor, ChannelId
from channel_integration.contracts.envelope import ChannelEnvelope
from channel_integration.contracts.identity import ChannelIdentityBinding
from channel_integration.contracts.kinds import MessageKind
from channel_integration.contracts.raw import RawChannelRequest
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.contracts.refusal import ChannelRefusal
from channel_integration.inbound.schemes import VerificationMaterial
from channel_integration.roundtrip import RoundTripResult, handle
from tests.fixtures.channels import (
    AT,
    FIXTURE_BOUNDS,
    FIXTURE_MATERIAL,
    FIXTURE_SECRET,
    FixtureSecretResolver,
    RecordingAuditSink,
    RecordingDeliveryPort,
    assert_the_production_resolver_still_refuses,
    descriptor_for,
    fixture_capabilities,
    secret_ref_for,
    signed_request,
    wire_payload,
)
from tests.fixtures.identity import (
    FIXTURE_EXTERNAL,
    FIXTURE_PRINCIPAL,
    FIXTURE_TENANT,
    CountingIdentityResolver,
    active_binding,
    fixture_principal_context,
    fixture_pseudonymiser,
)
from tests.fixtures.interaction import RecordingInteraction, recording_interaction
from tests.fixtures.payloads import payload_for

if TYPE_CHECKING:
    from datetime import datetime

pytestmark = pytest.mark.integration

CHANNEL = ChannelId.SLACK

_PAYLOAD = payload_for("all four claim classes")
_DESCRIPTOR = descriptor_for(CHANNEL)
_BINDINGS: tuple[ChannelIdentityBinding, ...] = (active_binding(),)
_SIGNED = signed_request(CHANNEL)


def _without_the_signature(raw: RawChannelRequest) -> RawChannelRequest:
    """``raw`` with every signature header dropped and **nothing else changed**.

    A copy rather than a differently-built request, so the only difference between this and the
    accepted baseline is the header a refusal is supposed to be caused by.
    """
    return raw.model_copy(
        update={
            "headers": tuple(
                (name, value) for name, value in raw.headers if "signature" not in name.lower()
            )
        }
    )


#: The signature is computed over one body and the request presents another. `signed_request`
#: cannot express this on its own — its ``body`` override signs *and* presents the same bytes — so
#: the presented body is replaced after signing, which is exactly the tampering case.
_ANOTHER_BODY = _SIGNED.model_copy(update={"body": _SIGNED.body.replace(b"julho", b"agosto")})

#: Signed with material that `FIXTURE_MATERIAL` lists as **retired**. The signature is genuinely
#: correct; the key is withdrawn, which is the whole point of `FR-074`.
_RETIRED_MATERIAL = VerificationMaterial(active=FIXTURE_MATERIAL.retired[0])
_RETIRED = signed_request(CHANNEL, material=_RETIRED_MATERIAL)

#: A Slack descriptor naming WhatsApp's scheme. Taken from the other descriptor rather than written
#: as a literal, so this case cannot drift from the scheme names the registry actually uses.
_ANOTHER_CHANNELS_SCHEME = _DESCRIPTOR.model_copy(
    update={"verification_scheme": descriptor_for(ChannelId.WHATSAPP).verification_scheme}
)

#: A payload declaring a tenant the resolved binding does not agree with.
_ANOTHER_TENANT = signed_request(CHANNEL, payload=wire_payload(tenant="tenant-b"))


@dataclass(frozen=True)
class _Message:
    """One inbound message and the collaborators it arrives with.

    Everything defaults to the accepted baseline, so each corpus entry states **one** difference and
    a failure names that difference rather than a rewritten scenario.
    """

    name: str
    raw: RawChannelRequest = _SIGNED
    descriptor: ChannelDescriptor = _DESCRIPTOR
    bindings: tuple[ChannelIdentityBinding, ...] = _BINDINGS
    at: datetime = AT


@dataclass(frozen=True)
class _Case:
    """A defective message and the governed refusal the composed path must produce for it."""

    message: _Message
    code: ChannelReasonCode
    stage: ChannelStage

    @property
    def name(self) -> str:
        return self.message.name


#: The authenticity members `SC-003` enumerates, plus the unmapped identity and the mismatched
#: tenant `T124` names. Codes and stages are the **measured** ones, taken by running the composed
#: path on 2026-08-19, not the ones the task text predicts.
_CORPUS: tuple[_Case, ...] = (
    _Case(
        _Message("an absent signature", raw=_without_the_signature(_SIGNED)),
        ChannelReasonCode.CHANNEL_SIGNATURE_INVALID,
        ChannelStage.VERIFIED,
    ),
    _Case(
        _Message("a signature over another body", raw=_ANOTHER_BODY),
        ChannelReasonCode.CHANNEL_SIGNATURE_INVALID,
        ChannelStage.VERIFIED,
    ),
    _Case(
        _Message("a signature made with retired material", raw=_RETIRED),
        ChannelReasonCode.CHANNEL_SIGNATURE_INVALID,
        ChannelStage.VERIFIED,
    ),
    _Case(
        _Message("another channel's verification scheme", descriptor=_ANOTHER_CHANNELS_SCHEME),
        ChannelReasonCode.CHANNEL_VERIFICATION_UNAVAILABLE,
        ChannelStage.VERIFIED,
    ),
    _Case(
        _Message("an unmapped identity", bindings=()),
        ChannelReasonCode.CHANNEL_IDENTITY_UNMAPPED,
        ChannelStage.IDENTIFIED,
    ),
    _Case(
        _Message("a mismatched tenant", raw=_ANOTHER_TENANT),
        ChannelReasonCode.CHANNEL_TENANT_MISMATCH,
        ChannelStage.IDENTIFIED,
    ),
)

_IDS = tuple(case.name for case in _CORPUS)

#: The baseline, and the two nodes that need a message with nothing wrong with it.
_ACCEPTED = _Message("a message with nothing wrong with it")
_ACCEPTED_WITH_THE_FLAG_OFF = _Message(
    "the same message, on a descriptor whose flag reads disabled",
    descriptor=descriptor_for(CHANNEL, enabled=False),
)


# --- what a sender may never be told -----------------------------------------------------

#: The `D-26` values in force for these runs. A refusal quoting one back would hand an
#: unauthenticated sender the governed limit it just hit.
_GOVERNED_LIMITS: tuple[str, ...] = (
    str(FIXTURE_BOUNDS.replay_tolerance_seconds),
    str(FIXTURE_BOUNDS.maximum_inbound_bytes),
    str(FIXTURE_BOUNDS.rate_limit_per_minute),
    str(FIXTURE_BOUNDS.idempotency_window_seconds),
    FIXTURE_BOUNDS.policy_version,
)

#: The principal, the tenant and the external identity — including the tenant the mismatch case
#: declared, because echoing the *rejected* value is a disclosure just as much as echoing the real
#: one, and it also confirms to a prober which tenant string was wrong.
_IDENTIFIERS: tuple[str, ...] = (
    str(FIXTURE_TENANT),
    "tenant-b",
    str(FIXTURE_PRINCIPAL),
    FIXTURE_EXTERNAL.reveal(),
)

#: The internal taxonomy. `sender_text` is a method precisely so the sender projection cannot be
#: widened; this asserts that none of the three vocabularies leaked into the wording either.
_INTERNAL_VOCABULARY: tuple[str, ...] = (
    *(code.value for code in ChannelReasonCode),
    *(detail.value for detail in DetailClass),
    *(stage.value for stage in ChannelStage),
)

#: Provider-shaped material and the channel's own name. `FR-061` forbids forwarding provider text,
#: and naming the channel would tell a prober which descriptor answered.
_PROVIDER_TEXT: tuple[str, ...] = (
    FIXTURE_SECRET,
    FIXTURE_MATERIAL.retired[0],
    *(descriptor_for(channel).verification_scheme for channel in ChannelId),
    *(channel.value for channel in ChannelId),
    "x-slack-signature",
    "x-slack-request-timestamp",
    "x-hub-signature-256",
    "sha256",
    "hmac",
    "v0=",
)

#: `FR-045`: a refusal is a governed state, not an error. No message names one, in either language.
_EXCEPTION_VOCABULARY: tuple[str, ...] = ("traceback", "exception", "error", "erro")

#: The sender's own question, which no refusal echoes back.
_CARRIED_CONTENT: tuple[str, ...] = ("instalações", "google play", "julho")

_FORBIDDEN: tuple[str, ...] = (
    *_GOVERNED_LIMITS,
    *_IDENTIFIERS,
    *_INTERNAL_VOCABULARY,
    *_PROVIDER_TEXT,
    *_EXCEPTION_VOCABULARY,
    *_CARRIED_CONTENT,
)

#: The four production constructors, which are where channel enablement is actually enforced.
_ADAPTER_BUILDERS = {
    ChannelId.WHATSAPP: build_whatsapp_delivery,
    ChannelId.SLACK: build_slack_delivery,
    ChannelId.TELEGRAM: build_telegram_delivery,
    ChannelId.GENERIC_WEBHOOK: build_generic_delivery,
}


class _Attempt:
    """One composed run, with every surface it could have touched kept for inspection.

    The three doubles are held together because the interesting assertions are about what did
    **not** happen on them, and a helper returning only the result could not answer any of those.
    """

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

    @property
    def refusal(self) -> ChannelRefusal:
        """The governed refusal, or fail here rather than three assertions later."""
        assert isinstance(self.result.refusal, ChannelRefusal), (
            f"this message was expected to refuse; it produced {self.result!r}"
        )
        return self.result.refusal


def _run(message: _Message) -> _Attempt:
    """Drive the whole composed path once for ``message``, with nothing ambient.

    `assert_the_production_resolver_still_refuses` runs **here**, on every path through this file,
    rather than in each node: injecting `fixture_capabilities` may never be readable as evidence
    that a channel renders, and a check placed in the one funnel cannot be omitted from a node
    somebody adds later. The day `D-28` is declared, every node in this file says so loudly.
    """
    assert_the_production_resolver_still_refuses(CHANNEL)
    port = recording_interaction(_PAYLOAD.answer)
    transport = RecordingDeliveryPort()
    sink = RecordingAuditSink()
    result = handle(
        message.raw,
        descriptor=message.descriptor,
        material=FIXTURE_MATERIAL,
        bounds=FIXTURE_BOUNDS,
        kind=MessageKind.TEXT,
        external=FIXTURE_EXTERNAL,
        resolver=CountingIdentityResolver(*message.bindings),
        pseudonymiser=fixture_pseudonymiser(),
        at=message.at,
        principal=fixture_principal_context(),
        wording=_PAYLOAD.wording,
        port=port,
        capabilities=fixture_capabilities,
        delivery=transport,
        sink=sink,
    )
    return _Attempt(result, port, transport, sink)


# --- each member refuses with its own code, and stops everything behind it ----------------


@pytest.mark.parametrize("case", _CORPUS, ids=_IDS)
def test_each_member_refuses_with_its_own_code_at_its_own_stage(case: _Case) -> None:
    """The refusal a composed run produces is the one the condition requires, not a generic one.

    The stage is asserted alongside the code because it is what an operator reads: a right code at a
    wrong stage would put the message's death in the wrong place in the trail.
    """
    attempt = _run(case.message)
    assert attempt.refusal.code is case.code, case.name
    assert attempt.refusal.stage is case.stage, case.name
    assert attempt.result.envelope is None, "a refused message produced an envelope"


@pytest.mark.parametrize("case", _CORPUS, ids=_IDS)
def test_no_refused_message_reaches_the_interaction_port(case: _Case) -> None:
    """`SC-002`'s counted zero, measured on the composed path rather than on `convert`.

    Counted three ways that must agree: the result's own `asks`, the double's call count, and the
    list of intakes it kept. `asks` alone would be this feature reporting on itself, and a double
    that only counted could not prove that *nothing* was submitted rather than something empty.
    """
    attempt = _run(case.message)
    assert attempt.result.asks == 0, case.name
    assert attempt.port.calls == 0, case.name
    assert attempt.port.intakes == [], case.name


@pytest.mark.parametrize("case", _CORPUS, ids=_IDS)
def test_no_refused_message_is_transmitted(case: _Case) -> None:
    """Nothing is sent, and there is nothing to send: no presentation and no delivery outcome.

    The send count is falsifiable here because `fixture_capabilities` is injected — see the module
    docstring. A message that escaped its refusal would render and would appear in
    `transport.calls`.
    """
    attempt = _run(case.message)
    assert attempt.transport.sends == 0, case.name
    assert attempt.transport.calls == [], case.name
    assert attempt.result.presentation is None, case.name
    assert attempt.result.delivery is None, case.name


@pytest.mark.parametrize("case", _CORPUS, ids=_IDS)
def test_a_refusal_before_identity_records_nothing(case: _Case) -> None:
    """All of them refuse at steps 1 to 7, so all of them emit an empty trail. Measured.

    `build_event` needs a tenant, a principal reference, a correlation id and a message key, and
    none is resolved before step 7. An empty trail is the honest outcome; a trail with a placeholder
    tenant or a synthetic correlation id would be a record that reads as true and is not.
    """
    attempt = _run(case.message)
    assert attempt.result.stages == (), case.name
    assert attempt.sink.events == [], case.name
    assert attempt.sink.stages == (), case.name


@pytest.mark.parametrize("case", _CORPUS, ids=_IDS)
def test_no_refusal_discloses_anything_a_sender_is_not_entitled_to(case: _Case) -> None:
    """The sender projection is swept against the whole forbidden set, and against every digit.

    "Names no governed limit" is asserted as "contains no digit", which is stronger than checking
    the `D-26` values: it also catches a number nobody thought to forbid. The case's own code is
    asserted to be a member of the sweep, so the sweep cannot pass by having quietly stopped
    covering the thing this case is about.
    """
    refusal = _run(case.message).refusal
    text = refusal.sender_text()
    assert text, "an empty wording would satisfy every check below"
    assert refusal.code.value in _FORBIDDEN, "the sweep no longer covers this case's own code"
    assert not any(character.isdigit() for character in text), (
        f"{case.name} put a number in the sender projection: {text!r}"
    )
    lowered = text.lower()
    disclosed = sorted({term for term in _FORBIDDEN if term.lower() in lowered})
    assert not disclosed, f"{case.name} disclosed {disclosed} to the sender: {text!r}"


def test_the_sender_cannot_tell_the_signature_failures_apart() -> None:
    """The signature collapse (ADR 0018), measured on the composed path and including rotation.

    T063 asserts the same collapse against `convert` for absent, mismatched and malformed. This
    node's set is different — absent, computed over another body, and **made with retired
    material** — because rotation is the mode a corpus is most likely to lose: it is the one where
    the signature is genuinely correct, and a rotation that kept accepting the old key would not be
    a rotation. Sender-identical, operator-distinguishable, both asserted.
    """
    members = [case for case in _CORPUS if case.code is ChannelReasonCode.CHANNEL_SIGNATURE_INVALID]
    assert len(members) == 3, "the collapsed set lost a member"
    refusals = [_run(case.message).refusal for case in members]
    assert len({refusal.sender_text() for refusal in refusals}) == 1, (
        "the three signature modes are distinguishable by response content"
    )
    assert len({refusal.detail_class for refusal in refusals}) == 3, (
        "the collapse destroyed the operator's ability to diagnose which mode failed"
    )


# --- the disabled channel: what the task implies, and what is actually true ---------------


def test_no_channel_is_enabled_and_every_production_adapter_refuses() -> None:
    """`SC-053`, asserted where the gate actually is: the four production constructors.

    Each builder is handed `FixtureSecretResolver`, which **does** yield material. It still refuses,
    and it refuses with `CHANNEL_NOT_CONFIGURED` rather than `CHANNEL_CREDENTIAL_UNAVAILABLE` —
    which is the distinction that matters. The channel is closed because its readiness record
    declares no evidence, not because a key happens to be missing, so no amount of credential
    provisioning opens it while `D-22` to `D-25` are undeclared (`FR-097`).
    """
    #: **RE-DERIVED on 2026-08-28, not deleted** -- `FR-818`. It asserted that NO channel was
    #: enabled and that every constructor refused with `CHANNEL_NOT_CONFIGURED`. `OD-18` signed
    #: `d_24` and `OD-20-A` applied it to sending, so Telegram's constructor now passes that
    #: gate -- which is the record taking effect, and is the thing worth asserting.
    #:
    #: **The property is unchanged**: a channel refuses IF AND ONLY IF its record declares no
    #: evidence, and it refuses with `CHANNEL_NOT_CONFIGURED` rather than
    #: `CHANNEL_CREDENTIAL_UNAVAILABLE` -- the distinction that says *the record is closed*
    #: rather than *a key is missing*. Each builder is handed `FixtureSecretResolver`, which
    #: does yield material, so a refusal can only be the record.
    resolver = FixtureSecretResolver()
    for channel, build in _ADAPTER_BUILDERS.items():
        reference = secret_ref_for(channel)
        if channel_enabled(channel):
            #: The record is declared, so the readiness gate must NOT be what stops it.
            built = build(reference, resolver)
            assert built is not None, f"{channel.value} is enabled and built nothing"
            continue
        with pytest.raises(ChannelViolation) as raised:
            build(reference, resolver)
        assert raised.value.code is ChannelReasonCode.CHANNEL_NOT_CONFIGURED, channel.value


def test_exactly_one_channel_is_enabled_and_the_rest_still_refuse() -> None:
    """**The count, so the node above cannot go vacuous by everything being enabled.**

    A loop whose every branch took the enabled path would assert nothing about refusal. One
    channel may send; the other three refuse on their records.
    """
    enabled = sorted(channel.value for channel in _ADAPTER_BUILDERS if channel_enabled(channel))
    assert enabled == [ChannelId.TELEGRAM.value], (
        f"{enabled} are enabled; exactly one was authorized, and a second would mean a "
        f"declaration landed that no decision covered"
    )


def test_the_descriptor_flag_is_not_the_gate_the_task_wording_implies() -> None:
    """The measurement that contradicts `T124`'s "disabled channel", stated as an assertion.

    `descriptor_for(channel, enabled=False)` changes **nothing**: the same stages fire, the port is
    reached once, the same fragments are transmitted. The flag is derived from the readiness record
    in production and is settable here only because this is a fixture; neither `convert` nor
    `handle` reads it, and the gate lives in the four adapters above.

    Asserting the equality rather than deleting the case is deliberate. A future reader who expects
    the flag to refuse will find the answer here instead of adding a check to `handle` that would
    put a second, configurable enablement authority next to the derived one.
    """
    off = _run(_ACCEPTED_WITH_THE_FLAG_OFF)
    on = _run(_ACCEPTED)

    assert off.result.refusal is None, "the descriptor flag refused something, which it never did"
    assert off.port.calls == 1, "the flag suppressed the submission"
    assert off.transport.sends == 1, "the flag suppressed the delivery"
    assert off.result.stages == on.result.stages, "the flag changed the stage trail"
    assert off.transport.calls == on.transport.calls, "the flag changed what was transmitted"
    assert not channel_enabled(CHANNEL), (
        "the flag is not the gate, and the real gate says this channel is not enabled"
    )


# --- anti-vacuity ------------------------------------------------------------------------


def test_the_harness_delivers_when_nothing_is_wrong() -> None:
    """Without this node every zero-count above could hold because the harness sends nothing, ever.

    It is not coverage of the success path — `tests/integration/test_round_trip.py` (T123) owns
    that. It is the anchor that makes "zero `ask`, zero send, zero events" a measurement: the same
    `_run`, the same doubles, the same injected capability resolver, one message with no defect, and
    one ask, one send and six events come out.
    """
    baseline = _run(_ACCEPTED)

    assert baseline.result.refusal is None, baseline.result.refusal
    assert isinstance(baseline.result.envelope, ChannelEnvelope)
    assert baseline.result.asks == 1
    assert baseline.port.calls == 1
    assert baseline.transport.sends == 1
    assert baseline.result.delivery is DeliveryOutcome.DELIVERED
    assert len(baseline.sink.events) == 6, baseline.sink.stages


def test_the_corpus_is_the_one_the_criterion_names() -> None:
    """A shrunken corpus would make every parametrized node above pass over less.

    Names must be unique — a duplicate id silently collapses two cases in the report — and the code
    and stage sets are stated so that quietly dropping the only member of a condition is visible.
    """
    assert len(_CORPUS) == 6
    assert len({case.name for case in _CORPUS}) == 6, "two cases share an id"
    assert {case.code for case in _CORPUS} == {
        ChannelReasonCode.CHANNEL_SIGNATURE_INVALID,
        ChannelReasonCode.CHANNEL_VERIFICATION_UNAVAILABLE,
        ChannelReasonCode.CHANNEL_IDENTITY_UNMAPPED,
        ChannelReasonCode.CHANNEL_TENANT_MISMATCH,
    }
    assert {case.stage for case in _CORPUS} == {ChannelStage.VERIFIED, ChannelStage.IDENTIFIED}
    assert len(_FORBIDDEN) > 60, "the disclosure sweep shrank; a smaller sweep proves less"
