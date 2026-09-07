"""The pure inbound conversion — T041 (ADR 0020; FR-105 — FR-107; SC-002, SC-050, SC-061).

```
convert(raw, material, descriptor, bounds, kind, external, resolver, pseudonymiser, at)
    -> ChannelEnvelope | ChannelRefusal
```

**Pure.** No socket, no listener, no framework object, no ambient configuration, no environment
read, **no clock**. The instant arrives as a parameter and every collaborator is injected, which
is what lets a real listener, a simulator, a test and the CLI drive the same function and get
the same answer (`FR-105`).

**Total.** Every input yields an envelope or a governed refusal. No exception escapes as a
transport error, and there is no "unhandled" input — which is why the return type is a union and
not an optional.

**Steps 1 to 7, in order** (`contracts/inbound-conversion.md` §3). Step 8 — idempotency and
submission — is Phase C and D; this function stops at the envelope, so nothing here can reach the
interaction port even by accident.

**A transport's claim is ignored.** There is no parameter through which a caller says "already
verified", and `RawChannelRequest` has no field for it. Verification runs here, over the received
bytes, every time (`FR-107`).

**No refusal names a governed limit**, at any step. The sender is unauthenticated throughout this
function, so the structural ceiling refuses without a number and the `D-26` bounds are never
quoted back (`contracts/inbound-conversion.md` §3).
"""

from __future__ import annotations

from datetime import datetime

from ..contracts._base import ChannelViolation, PrincipalRef, TenantId
from ..contracts.audit import ChannelStage, DetailClass
from ..contracts.descriptor import ChannelDescriptor
from ..contracts.envelope import ChannelEnvelope
from ..contracts.identity import ExternalIdentity
from ..contracts.kinds import MessageKind
from ..contracts.raw import RawChannelRequest
from ..contracts.reason_codes import ChannelReasonCode
from ..contracts.refusal import ChannelRefusal, refusal_from_violation
from ..governance.bounds import TransportBounds
from ..identity.pseudonymise import PseudonymPort
from ..identity.resolve import ChannelIdentityResolver, resolve_identity
from ..identity.scope import (
    derive_conversation_ref,
    derive_correlation_id,
    require_scoped_conversation,
    require_scoped_correlation,
)
from ..identity.tenant import require_consistent_tenant
from .envelope import assemble_envelope, validate_wire_shape
from .kind import require_textual
from .normalise import normalise_question
from .parse import parse_structure
from .schemes import VerificationMaterial
from .verify import verify_authenticity

__all__ = ["CONVERSION_STAGES", "convert"]

#: Which audit stage each step belongs to, so a refusal is recorded where it happened.
#: Steps 1 to 3 are `RECEIVED` and `VERIFIED`; steps 4 to 6 stay `VERIFIED`, because the message
#: is authentic by then and what follows is shape; step 7 is `IDENTIFIED`.
CONVERSION_STAGES = (ChannelStage.RECEIVED, ChannelStage.VERIFIED, ChannelStage.IDENTIFIED)


def _detail_class_of(error: ChannelViolation) -> DetailClass:
    """The operator-facing class a refusal carries, when it carries one."""
    return getattr(error, "detail_class", DetailClass.NONE)


def convert(
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
) -> ChannelEnvelope | ChannelRefusal:
    """Steps 1 to 7. Returns the canonical envelope, or the governed refusal."""
    stage = ChannelStage.RECEIVED
    try:
        if not isinstance(raw, RawChannelRequest):
            # A caller handing us something other than the canonical request is malformed
            # input, not a programming error to raise through: the operation is total.
            raise ChannelViolation(
                ChannelReasonCode.CHANNEL_PAYLOAD_MALFORMED,
                "the inbound request is not a canonical RawChannelRequest",
            )

        # --- step 1: structural parse. Decides nothing about content. -------------------
        payload = parse_structure(raw)

        # --- steps 2 and 3: authenticity, integrity, replay tolerance --------------------
        stage = ChannelStage.VERIFIED
        verify_authenticity(raw, descriptor, material, bounds, at)

        # --- step 4: message kind. TEXT, or refuse naming the kind. ----------------------
        require_textual(kind)

        # --- step 5: the payload's own shape, **before** any cost surface ----------------
        #     An undeclared field, an absent required field or an unparseable date refuses here.
        #     `T052` measures that each of those costs **zero** registry reads and zero
        #     derivations — which is why the shape check cannot live inside assembly at the end.
        wire = validate_wire_shape(payload)

        # --- step 6: declared normalisation. Ambiguity refuses rather than guessing. ------
        normalised = normalise_question(wire.text)

        # --- step 7: identity, tenant, scope --------------------------------------------
        stage = ChannelStage.IDENTIFIED
        binding = resolve_identity(resolver, descriptor.channel, external)
        tenant = require_consistent_tenant(TenantId(wire.tenant_declared), binding)
        principal_ref: PrincipalRef = binding.principal_ref

        expected_conversation = derive_conversation_ref(
            pseudonymiser, tenant, descriptor.channel, principal_ref, wire.message_id
        )
        expected_correlation = derive_correlation_id(
            pseudonymiser, tenant, descriptor.channel, principal_ref, wire.message_id
        )
        conversation_id = require_scoped_conversation(
            wire.conversation_presented, expected_conversation
        )
        correlation_id = require_scoped_correlation(
            wire.correlation_presented, expected_correlation
        )

        # --- the canonical envelope, from the validated shape and the resolved values -----
        return assemble_envelope(
            payload,
            channel=descriptor.channel,
            tenant=tenant,
            principal_ref=principal_ref,
            conversation_id=conversation_id,
            correlation_id=correlation_id,
            text=normalised.text,
        )
    except ChannelViolation as violation:
        return refusal_from_violation(
            violation,
            stage,
            _detail_class_of(violation),
            **_wording_arguments(violation, descriptor, kind),
        )


def _wording_arguments(
    violation: ChannelViolation, descriptor: ChannelDescriptor, kind: MessageKind
) -> dict[str, str]:
    """The allowlisted arguments the governed wording for this code requires.

    Two names are allowlisted in the whole registry — ``channel`` and ``message_kind`` — so this
    mapping is the entire surface through which a refusal's text is parameterised, and neither
    name can carry content.
    """
    needs_channel = {
        ChannelReasonCode.CHANNEL_NOT_CONFIGURED,
        ChannelReasonCode.CHANNEL_CREDENTIAL_UNAVAILABLE,
        ChannelReasonCode.CHANNEL_RATE_LIMIT_EXCEEDED,
        ChannelReasonCode.CHANNEL_DELIVERY_FAILED,
        ChannelReasonCode.CHANNEL_DELIVERY_ATTEMPTS_EXHAUSTED,
    }
    if violation.code in needs_channel:
        return {"channel": descriptor.channel.value}
    if violation.code is ChannelReasonCode.CHANNEL_MESSAGE_KIND_UNSUPPORTED:
        return {"message_kind": kind.value}
    return {}
