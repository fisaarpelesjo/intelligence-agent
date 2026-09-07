"""Step 7c — scoped references — T044 (FR-026, FR-027; SC-013).

A `conversation_id` or a `correlation_id` presented by a different principal, tenant or channel
must refuse — **without state**, because this feature keeps none (`FR-030`).

The mechanism is derivation rather than lookup. A scoped reference is
``derive(label, tenant, channel, principal_ref, provider_reference)``, so the reference *is*
its own proof of scope: recompute it from the resolved principal and compare. A caller
presenting someone else's reference produces a mismatch, and no record of who was issued what
is needed to detect it.

Three properties this buys, and one limit it does not hide:

* a crossed reference refuses (`CHANNEL_SCOPE_MISMATCH`) and the response **discloses nothing**
  about whether the referenced conversation exists — the same refusal covers a reference that
  never existed;
* a provider conversation id never reaches the envelope in raw form, so a chat id is not
  carried as an identifier (`FR-077`);
* derivation uses the `D-31` port, because deriving from an external identity **is**
  pseudonymisation; while `D-31` is undeclared no scoped reference is constructible and the
  flow refuses with ``CHANNEL_AUDIT_UNAVAILABLE``.

**The limit, stated:** this proves a reference belongs to the scope presenting it. It does not
prove the reference was ever issued, and it cannot — that needs the governed store `NG-4`
declares and does not build. A caller who can compute the derivation for their **own** scope can
mint their own conversation reference, which grants them exactly what they already have: a
conversation with themselves.
"""

from __future__ import annotations

from ..contracts._base import (
    ChannelViolation,
    ConversationRef,
    CorrelationId,
    PrincipalRef,
    TenantId,
)
from ..contracts.descriptor import ChannelId
from ..contracts.reason_codes import ChannelReasonCode
from .pseudonymise import PseudonymPort

__all__ = [
    "CONVERSATION_LABEL",
    "CORRELATION_LABEL",
    "derive_conversation_ref",
    "derive_correlation_id",
    "require_scoped_conversation",
    "require_scoped_correlation",
]

#: Domain separators. Two references over identical parts must not collide across purposes.
CONVERSATION_LABEL = "conversation"
CORRELATION_LABEL = "correlation"


def derive_conversation_ref(
    pseudonymiser: PseudonymPort,
    tenant: TenantId,
    channel: ChannelId,
    principal_ref: PrincipalRef,
    provider_reference: str,
) -> ConversationRef:
    """The scoped conversation reference for this exchange."""
    return ConversationRef(
        pseudonymiser.derive(
            CONVERSATION_LABEL, str(tenant), channel.value, str(principal_ref), provider_reference
        )
    )


def derive_correlation_id(
    pseudonymiser: PseudonymPort,
    tenant: TenantId,
    channel: ChannelId,
    principal_ref: PrincipalRef,
    provider_message_id: str,
) -> CorrelationId:
    """The scoped correlation id for this exchange.

    Derived from the provider's message id, so one inbound message correlates to exactly one
    trail and a second message cannot land inside the first one's story.
    """
    return CorrelationId(
        pseudonymiser.derive(
            CORRELATION_LABEL, str(tenant), channel.value, str(principal_ref), provider_message_id
        )
    )


def require_scoped_conversation(
    presented: str | None, expected: ConversationRef
) -> ConversationRef:
    """``expected`` when the caller presented nothing or presented it correctly.

    A first message presents nothing and the derived reference is used. A caller that *does*
    present one — the generic API/webhook path — must present the reference its own scope
    derives, and anything else refuses.
    """
    if presented is None:
        return expected
    if presented != str(expected):
        raise ChannelViolation(
            ChannelReasonCode.CHANNEL_SCOPE_MISMATCH,
            "the presented conversation reference does not belong to this scope",
        )
    return expected


def require_scoped_correlation(presented: str | None, expected: CorrelationId) -> CorrelationId:
    """``expected`` when the caller presented nothing or presented it correctly."""
    if presented is None:
        return expected
    if presented != str(expected):
        raise ChannelViolation(
            ChannelReasonCode.CHANNEL_SCOPE_MISMATCH,
            "the presented correlation id does not belong to this scope",
        )
    return expected
