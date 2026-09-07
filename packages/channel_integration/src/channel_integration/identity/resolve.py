"""Step 7a — identity binding resolution — T042 (FR-017 — FR-020; SC-010, SC-011).

**Exactly one `ACTIVE` binding, or refuse.** Five conditions collapse into
``CHANNEL_IDENTITY_UNMAPPED``: no binding, revoked, expired, ambiguous, and one external
identity bound to several principals. Distinguishing them describes the registry's shape to an
unauthenticated caller, and "revoked" in particular confirms the identity once existed
(ADR 0018). The operator still learns which, through the detail class.

**No cache, no index, no memoisation.** A cache would be a local authorization decision with a
staleness window — `FR-021` forbids one — and a revoked binding must stop working
*immediately*, not at the end of a TTL (`R-7`). This module holds no module-level state, and
`T028`'s scan plus `T105`'s concurrency suite are what keep that true.

**This resolves who is asking. It never decides what they may see.** Metric-level access stays
with `001`'s gate, `002`'s preflight and `003`'s authorization-context preflight. Nothing here
mints an identity, creates or infers an access tag, elevates a scope, or accepts an identity,
tenant, scope or tag asserted by a message (`FR-018`).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..contracts.audit import DetailClass
from ..contracts.descriptor import ChannelId
from ..contracts.identity import BindingStatus, ChannelIdentityBinding, ExternalIdentity
from ..contracts.reason_codes import ChannelReasonCode
from ..inbound.verify import VerificationFailure

__all__ = ["ChannelIdentityResolver", "IdentityRefused", "resolve_identity"]

#: Reuses the verification failure shape: a refusal that also carries the operator-facing
#: detail class. Named separately so a reader sees which boundary refused.
IdentityRefused = VerificationFailure

_STATUS_DETAIL = {
    BindingStatus.REVOKED: DetailClass.BINDING_REVOKED,
    BindingStatus.EXPIRED: DetailClass.BINDING_EXPIRED,
}


@runtime_checkable
class ChannelIdentityResolver(Protocol):
    """The `D-27` registry, as this feature reaches it.

    Returns **every** binding the registry holds for the pair, including revoked and expired
    ones. Filtering inside the registry would hide the difference between "no binding" and
    "a binding that no longer applies" — a difference the operator needs even though the
    sender may not have it.
    """

    def bindings_for(
        self, channel: ChannelId, external: ExternalIdentity
    ) -> tuple[ChannelIdentityBinding, ...]:
        """Every binding for ``(channel, external)``, unfiltered."""
        ...


def resolve_identity(
    resolver: ChannelIdentityResolver, channel: ChannelId, external: ExternalIdentity
) -> ChannelIdentityBinding:
    """The one usable binding, or refuse with the collapsed code."""
    bindings = resolver.bindings_for(channel, external)

    if not bindings:
        raise IdentityRefused(
            ChannelReasonCode.CHANNEL_IDENTITY_UNMAPPED,
            "no governed binding",
            DetailClass.BINDING_ABSENT,
        )

    usable = tuple(binding for binding in bindings if binding.usable)

    if len(usable) > 1:
        raise IdentityRefused(
            ChannelReasonCode.CHANNEL_IDENTITY_UNMAPPED,
            "more than one usable binding",
            DetailClass.BINDING_AMBIGUOUS,
        )

    if not usable:
        # Every binding exists but none applies. The **worst** status is reported to the
        # operator so a revoked binding is not hidden behind an expired one.
        statuses = {binding.status for binding in bindings}
        detail = (
            DetailClass.BINDING_REVOKED
            if BindingStatus.REVOKED in statuses
            else _STATUS_DETAIL.get(BindingStatus.EXPIRED, DetailClass.BINDING_ABSENT)
        )
        raise IdentityRefused(
            ChannelReasonCode.CHANNEL_IDENTITY_UNMAPPED,
            "no usable binding",
            detail,
        )

    binding = usable[0]
    if binding.channel is not channel:
        # A binding for another channel is not this channel's binding, whatever the registry
        # returned. Reported as absent, because saying otherwise would describe the registry.
        raise IdentityRefused(
            ChannelReasonCode.CHANNEL_IDENTITY_UNMAPPED,
            "the binding belongs to another channel",
            DetailClass.BINDING_ABSENT,
        )
    return binding
