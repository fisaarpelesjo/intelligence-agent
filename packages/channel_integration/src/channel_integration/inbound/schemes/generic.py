"""Generic API/webhook verification scheme — T036 (`D-25` undeclared; FR-010 — FR-012).

HMAC-SHA-256 over a timestamped basestring — ``<timestamp>.<body>`` — with the digest and the
timestamp in their own headers, and the **client identifier** in a third.

The strongest of the four by design, because this is the one scheme this repository defines
rather than inherits: it binds the body, binds the timestamp, and names the client so the
registry can select material per client instead of sharing one secret across every caller.

**No client is trusted while `D-25` is undeclared.** There is no registry, so no material
resolves, and an unregistered client is indistinguishable in response from a registered one
whose signature failed — which is the disclosure property the collapsed code exists for.

**No client, endpoint, secret or registry entry is created here.**
"""

from __future__ import annotations

from ...contracts.audit import DetailClass
from . import VerificationMaterial, VerificationOutcome
from ._hmac import header_value, verify_hexdigest

__all__ = ["GENERIC_CLIENT_HEADER", "GenericWebhookScheme"]

_SIGNATURE_HEADER = "x-signature-sha256"
_TIMESTAMP_HEADER = "x-signature-timestamp"

#: Read by the adapter to select material per client from the `D-25` registry. It is an
#: **identifier**, never an authorisation: naming a client grants nothing.
GENERIC_CLIENT_HEADER = "x-client-id"


class GenericWebhookScheme:
    """HMAC-SHA-256 over ``<timestamp>.<body>``, per registered client."""

    name = "generic-hmac-sha256"
    provides_signed_timestamp = True

    def verify(
        self,
        body: bytes,
        headers: tuple[tuple[str, str], ...],
        material: VerificationMaterial,
    ) -> VerificationOutcome:
        presented = header_value(headers, _SIGNATURE_HEADER)
        timestamp = header_value(headers, _TIMESTAMP_HEADER)
        if presented is None or not presented.strip():
            return VerificationOutcome.failed(DetailClass.SIGNATURE_ABSENT)
        if timestamp is None or not timestamp.strip().isdigit():
            return VerificationOutcome.failed(DetailClass.SIGNATURE_MALFORMED)

        basestring = b".".join((timestamp.strip().encode("ascii"), body))
        return verify_hexdigest(presented, basestring, material)

    def signed_timestamp(self, headers: tuple[tuple[str, str], ...]) -> int | None:
        raw = header_value(headers, _TIMESTAMP_HEADER)
        if raw is None or not raw.strip().isdigit():
            return None
        return int(raw.strip())
