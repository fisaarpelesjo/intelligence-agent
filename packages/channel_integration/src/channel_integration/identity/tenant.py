"""Step 7b — tenant consistency — T043 (FR-028; SC-013).

The envelope's declared tenant is compared with the resolved binding's tenant. Disagreement
refuses **before** any interaction submission.

The check exists because the tenant is carried explicitly rather than derived (`A-6`, `R-6`).
A derived tenant would make this comparison tautological — it would compare a value with
itself — and the comparison is precisely what turns "this deployment is single-tenant" from an
assumption into an assertion. When a second tenant appears, what changes is the data flowing
through here, not whether isolation holds.
"""

from __future__ import annotations

from ..contracts._base import ChannelViolation, TenantId
from ..contracts.identity import ChannelIdentityBinding
from ..contracts.reason_codes import ChannelReasonCode

__all__ = ["require_consistent_tenant"]


def require_consistent_tenant(declared: TenantId, binding: ChannelIdentityBinding) -> TenantId:
    """The agreed tenant, or refuse.

    Returns the tenant rather than ``None`` so a caller uses the **verified** value onwards
    instead of the one the payload declared. Same string either way today; different origin,
    and the origin is the point.
    """
    if declared != binding.tenant:
        raise ChannelViolation(
            ChannelReasonCode.CHANNEL_TENANT_MISMATCH,
            "the declared tenant is not the tenant of the resolved principal",
        )
    return binding.tenant
