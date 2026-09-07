"""The ordered inbound sequence — T069 (`contracts/inbound-conversion.md` §3; FR-105 to FR-107).

Eight steps are specified. Seven exist; the eighth — idempotency and submission — is Phase C and D,
and this test says so rather than implying coverage it does not have.

Ordering is not a style preference here. It is the mechanism by which an unauthenticated stranger
causes no cost: if identity resolution ran before signature verification, a stranger's request would
read the registry. So each refusal is asserted **at its required step**, and the instrument is the
step *after* it: a refusal at step N must show none of step N+1's effects.

Three orderings are asserted separately, because each has its own failure mode:

* **parse before verify** — verification over a re-serialised parse would verify a body the sender
  never signed;
* **verify before everything** — the counted-zero property (`T052`) depends on it;
* **shape before identity** — an undeclared field is a payload defect, and diagnosing it must not
  cost a registry read. This one was a real defect: the shape check originally lived inside envelope
  assembly, at the end, and `T052` caught it.

The whole sequence runs with **no transport present**: bytes, headers, an instant and injected
collaborators. That is what makes the same function drivable by a listener, a simulator, the CLI and
this test with identical results (`FR-105`).
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from channel_integration.contracts.audit import ChannelStage, DetailClass
from channel_integration.contracts.descriptor import ChannelId
from channel_integration.contracts.envelope import ChannelEnvelope
from channel_integration.contracts.kinds import MessageKind
from channel_integration.contracts.reason_codes import ChannelReasonCode
from channel_integration.contracts.refusal import ChannelRefusal
from channel_integration.inbound.convert import CONVERSION_STAGES, convert

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
    FIXTURE_PRINCIPAL,
    FIXTURE_TENANT,
    CountingIdentityResolver,
    CountingPseudonymiser,
    active_binding,
    fixture_pseudonymiser,
)

pytestmark = pytest.mark.integration

_CHANNEL = ChannelId.SLACK


class _Run:
    """One conversion, with the observable effects of each cost surface recorded."""

    def __init__(
        self,
        outcome: ChannelEnvelope | ChannelRefusal,
        resolver_calls: int,
        derivations: int,
    ) -> None:
        self.outcome = outcome
        self.resolver_calls = resolver_calls
        self.derivations = derivations

    @property
    def refusal(self) -> ChannelRefusal:
        assert isinstance(self.outcome, ChannelRefusal), "this case was expected to refuse"
        return self.outcome

    @property
    def envelope(self) -> ChannelEnvelope:
        assert isinstance(self.outcome, ChannelEnvelope), "this case was expected to succeed"
        return self.outcome


def _run(
    *,
    payload: dict[str, object] | None = None,
    body: bytes | None = None,
    headers_filter: str | None = None,
    tamper: bool = False,
    late: bool = False,
    kind: MessageKind = MessageKind.TEXT,
    bindings: tuple[object, ...] | None = None,
    channel: ChannelId = _CHANNEL,
) -> _Run:
    raw = signed_request(channel, payload=payload or wire_payload(), body=body)
    if headers_filter is not None:
        raw = raw.model_copy(
            update={
                "headers": tuple(
                    (name, value)
                    for name, value in raw.headers
                    if headers_filter not in name.lower()
                )
            }
        )
    if tamper:
        raw = raw.model_copy(update={"body": raw.body.replace(b"julho", b"agosto")})

    bounds = bounds_for(channel)
    at = AT + timedelta(seconds=bounds.replay_tolerance_seconds + 60) if late else AT
    resolver = CountingIdentityResolver(
        *(bindings if bindings is not None else (active_binding(channel=channel),))  # type: ignore[arg-type]
    )
    pseudonymiser = CountingPseudonymiser()
    outcome = convert(
        raw,
        descriptor=descriptor_for(channel),
        material=FIXTURE_MATERIAL,
        bounds=bounds,
        kind=kind,
        external=FIXTURE_EXTERNAL,
        resolver=resolver,
        pseudonymiser=pseudonymiser,
        at=at,
    )
    return _Run(outcome, resolver.calls, pseudonymiser.calls)


# --- the seven steps that exist, each refusing where it must ----------------------------


def test_step_1_a_structural_defect_refuses_at_received() -> None:
    """Before anything is known about the sender, so the refusal names no governed limit."""
    run = _run(body=b"{not json")
    assert run.refusal.stage is ChannelStage.RECEIVED
    assert run.refusal.code is ChannelReasonCode.CHANNEL_PAYLOAD_MALFORMED
    assert run.resolver_calls == 0 and run.derivations == 0


def test_step_1_the_ceiling_refuses_without_naming_a_number() -> None:
    oversized = b'{"text":"' + b"a" * 70_000 + b'"}'
    run = _run(body=oversized)
    assert run.refusal.stage is ChannelStage.RECEIVED
    for number in ("64", "65536", "70000", "32768", "kb", "KB"):
        assert number not in run.refusal.sender_text()


def test_steps_2_and_3_an_unverifiable_request_refuses_at_verified() -> None:
    absent = _run(headers_filter="signature")
    assert absent.refusal.stage is ChannelStage.VERIFIED
    assert absent.refusal.code is ChannelReasonCode.CHANNEL_SIGNATURE_INVALID
    assert absent.refusal.detail_class is DetailClass.SIGNATURE_ABSENT

    tampered = _run(tamper=True)
    assert tampered.refusal.code is ChannelReasonCode.CHANNEL_SIGNATURE_INVALID
    assert tampered.refusal.detail_class is DetailClass.SIGNATURE_MISMATCH
    assert tampered.resolver_calls == 0


def test_step_3_a_stale_request_refuses_on_the_injected_instant() -> None:
    run = _run(late=True)
    assert run.refusal.code is ChannelReasonCode.CHANNEL_TIMESTAMP_OUTSIDE_TOLERANCE
    assert run.refusal.stage is ChannelStage.VERIFIED


def test_step_4_a_non_textual_kind_refuses_after_verification_not_before() -> None:
    """Ordering detail worth asserting: the kind refusal names the kind, so it must be authentic.

    Naming an unsupported kind to an **unverified** sender would be a small disclosure to anyone who
    can post bytes. Refusing it after verification keeps the naming safe.
    """
    run = _run(kind=MessageKind.AUDIO)
    assert run.refusal.code is ChannelReasonCode.CHANNEL_MESSAGE_KIND_UNSUPPORTED
    assert run.refusal.stage is ChannelStage.VERIFIED
    assert MessageKind.AUDIO.value in run.refusal.sender_text()
    assert run.resolver_calls == 0


def test_step_5_an_undeclared_field_refuses_before_the_registry_is_read() -> None:
    """The defect `T052` caught, kept caught."""
    run = _run(payload=wire_payload(access_tags=["admin"]))
    assert run.refusal.code is ChannelReasonCode.CHANNEL_ENVELOPE_FIELD_UNKNOWN
    assert run.refusal.stage is ChannelStage.VERIFIED
    assert run.resolver_calls == 0, "diagnosing a payload defect must cost no registry read"
    assert run.derivations == 0


def test_step_5_an_absent_required_field_refuses_at_the_same_step() -> None:
    payload = wire_payload()
    del payload["reference_date"]
    run = _run(payload=payload)
    assert run.refusal.code is ChannelReasonCode.CHANNEL_ENVELOPE_INCOMPLETE
    assert run.resolver_calls == 0


def test_step_6_ambiguous_normalisation_refuses_before_identity() -> None:
    run = _run(payload=wire_payload(text="quantas @bot instalações em julho?"))
    assert run.refusal.code is ChannelReasonCode.CHANNEL_NORMALISATION_AMBIGUOUS
    assert run.resolver_calls == 0


def test_step_7_an_unmapped_identity_refuses_at_identified() -> None:
    run = _run(bindings=())
    assert run.refusal.stage is ChannelStage.IDENTIFIED
    assert run.refusal.code is ChannelReasonCode.CHANNEL_IDENTITY_UNMAPPED
    assert run.resolver_calls == 1, "the registry is read exactly once"
    assert run.derivations == 0, "nothing is derived for an identity that does not resolve"


def test_step_7_a_tenant_disagreement_refuses_after_the_binding_resolves() -> None:
    run = _run(payload=wire_payload(tenant="tenant-b"))
    assert run.refusal.code is ChannelReasonCode.CHANNEL_TENANT_MISMATCH
    assert run.refusal.stage is ChannelStage.IDENTIFIED
    assert run.resolver_calls == 1
    assert run.derivations == 0


def test_step_7_a_crossed_scope_reference_refuses() -> None:
    run = _run(payload=wire_payload(conversation_id="somebody-elses-conversation"))
    assert run.refusal.code is ChannelReasonCode.CHANNEL_SCOPE_MISMATCH
    assert run.refusal.stage is ChannelStage.IDENTIFIED
    assert run.derivations >= 1, "the comparison requires the derivation to have happened"


# --- ordering, asserted as ordering ------------------------------------------------------


def test_the_declared_stage_sequence_is_the_one_conversion_uses() -> None:
    assert CONVERSION_STAGES == (
        ChannelStage.RECEIVED,
        ChannelStage.VERIFIED,
        ChannelStage.IDENTIFIED,
    )


def test_verification_precedes_identity_for_every_channel() -> None:
    """The counted-zero ordering, per channel rather than for one."""
    for channel in ChannelId:
        run = _run(channel=channel, headers_filter="signature")
        if channel is ChannelId.TELEGRAM:
            run = _run(channel=channel, headers_filter="secret-token")
        assert run.refusal.stage is ChannelStage.VERIFIED, channel
        assert run.resolver_calls == 0, channel


def test_verification_runs_over_the_received_bytes_not_a_reserialised_parse() -> None:
    """A body that parses to the same document but differs in bytes must still verify.

    Whitespace is the cheapest demonstration: re-serialising would normalise it and the signature
    would be computed over something the sender never signed.
    """
    payload = wire_payload()
    spaced = signed_request(_CHANNEL, body=b'{ "spaced" : "body" }')
    assert b" " in spaced.body
    run = _run(payload=payload, body=b'{ "spaced" : "body" }')
    # It refuses on shape, not on signature: the signature over these exact bytes was valid.
    assert run.refusal.code is ChannelReasonCode.CHANNEL_ENVELOPE_FIELD_UNKNOWN


def test_a_shape_defect_and_an_identity_defect_are_distinguishable_by_cost() -> None:
    """The ordering property in one assertion: same refusal shape, different cost."""
    shape = _run(payload=wire_payload(access_tags=["admin"]))
    identity = _run(bindings=())
    assert shape.resolver_calls == 0
    assert identity.resolver_calls == 1


# --- the successful path, and what step 8 is not ----------------------------------------


def test_the_whole_sequence_produces_a_canonical_envelope_with_no_transport_present() -> None:
    run = _run()
    envelope = run.envelope
    assert envelope.channel is _CHANNEL
    assert str(envelope.tenant) == str(FIXTURE_TENANT)
    assert str(envelope.principal_ref) == str(FIXTURE_PRINCIPAL)
    assert envelope.language == "pt-BR"
    assert envelope.as_of is None, "an absent as-of pin is never filled from the reference date"
    assert envelope.text == "quantas instalações tivemos na Google Play em julho?"
    assert run.resolver_calls == 1
    assert run.derivations == 2


def test_the_sequence_is_deterministic_across_repeats() -> None:
    """`FR-105`: same bytes, same instant, same collaborators, same answer."""
    first = _run().envelope.model_dump()
    second = _run().envelope.model_dump()
    assert first == second


def test_the_derived_references_match_an_independent_derivation() -> None:
    """The envelope's scope references are reproducible outside the flow, from the same inputs."""
    from channel_integration.identity.scope import (
        derive_conversation_ref,
        derive_correlation_id,
    )

    envelope = _run().envelope
    port = fixture_pseudonymiser()
    assert str(envelope.conversation_id) == str(
        derive_conversation_ref(
            port, FIXTURE_TENANT, _CHANNEL, FIXTURE_PRINCIPAL, "provider-message-1"
        )
    )
    assert str(envelope.correlation_id) == str(
        derive_correlation_id(
            port, FIXTURE_TENANT, _CHANNEL, FIXTURE_PRINCIPAL, "provider-message-1"
        )
    )


def test_step_8_is_absent_and_the_absence_is_the_point() -> None:
    """Idempotency and submission are Phase C and D. Nothing here can reach the interaction port.

    Asserted so this file cannot be read as covering the eighth step: `T098` covers idempotency and
    `T119` covers submission, and until they exist the sequence stops at the envelope.
    """
    import inspect
    from pathlib import Path

    parameters = set(inspect.signature(convert).parameters)
    for forbidden in ("port", "interaction", "idempotency", "store", "sink", "submit"):
        assert not any(forbidden in name for name in parameters)
    source = Path(inspect.getfile(convert)).read_text(encoding="utf-8")
    assert "InteractionPort" not in source
