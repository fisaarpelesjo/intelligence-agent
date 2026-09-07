"""WhatsApp verification scheme — T033 (`D-22` undeclared; FR-010, FR-012).

HMAC-SHA-256 over the **raw body**, presented in a versioned header as ``sha256=<hex>``.

**No credential, endpoint, number or application is created here.** `D-22` is undeclared, so
no material exists; this module describes how a message *would* be verified and refuses
before that when material is absent (`inbound.verify`).

**No signed timestamp.** The scheme does not provide one, so the replay window cannot be
evaluated for this channel, and that limit is stated rather than simulated: inventing a
timestamp from the receiving clock would make an unauthenticated payload look fresh
(`inbound.verify`, `R-5`).
"""

from __future__ import annotations

from ...contracts.audit import DetailClass
from . import VerificationMaterial, VerificationOutcome
from ._hmac import header_value, verify_hexdigest

__all__ = ["WhatsAppScheme"]

_SIGNATURE_HEADER = "x-hub-signature-256"
_PREFIX = "sha256="


class WhatsAppScheme:
    """HMAC-SHA-256 over the raw body, versioned header prefix."""

    name = "whatsapp-hmac-sha256"
    provides_signed_timestamp = False

    def verify(
        self,
        body: bytes,
        headers: tuple[tuple[str, str], ...],
        material: VerificationMaterial,
    ) -> VerificationOutcome:
        presented = header_value(headers, _SIGNATURE_HEADER)
        if presented is None or not presented.strip():
            return VerificationOutcome.failed(DetailClass.SIGNATURE_ABSENT)
        if not presented.startswith(_PREFIX):
            # A digest without its version prefix is malformed, not merely wrong: the prefix
            # is what says which algorithm produced it.
            return VerificationOutcome.failed(DetailClass.SIGNATURE_MALFORMED)
        return verify_hexdigest(presented[len(_PREFIX) :], body, material)

    def signed_timestamp(self, headers: tuple[tuple[str, str], ...]) -> int | None:
        return None
