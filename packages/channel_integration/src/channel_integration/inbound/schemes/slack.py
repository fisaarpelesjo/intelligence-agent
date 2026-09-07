"""Slack verification scheme — T034 (`D-23` undeclared; FR-010 — FR-012).

HMAC-SHA-256 over a **timestamped basestring** — ``v0:<timestamp>:<body>`` — with the digest
presented as ``v0=<hex>`` and the timestamp in its own header.

This is the one scheme among the four whose basestring binds the timestamp, which is why
this channel can have a replay window evaluated at all. The timestamp is read from the
signed material's own header and is only trusted **because** it is inside the basestring: a
timestamp header that were not signed would be a value an attacker could edit freely.

**No credential, application, workspace or scope is created here.** `D-23` is undeclared.
"""

from __future__ import annotations

from ...contracts.audit import DetailClass
from . import VerificationMaterial, VerificationOutcome
from ._hmac import header_value, verify_hexdigest

__all__ = ["SlackScheme"]

_SIGNATURE_HEADER = "x-slack-signature"
_TIMESTAMP_HEADER = "x-slack-request-timestamp"
_VERSION = "v0"


class SlackScheme:
    """HMAC-SHA-256 over ``v0:<timestamp>:<body>``."""

    name = "slack-v0"
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
            # The timestamp is part of what was signed. Absent or non-numeric, the
            # basestring cannot be reconstructed at all, so this is malformed rather than a
            # mismatch.
            return VerificationOutcome.failed(DetailClass.SIGNATURE_MALFORMED)
        if not presented.startswith(f"{_VERSION}="):
            return VerificationOutcome.failed(DetailClass.SIGNATURE_MALFORMED)

        basestring = b":".join((_VERSION.encode("ascii"), timestamp.strip().encode("ascii"), body))
        return verify_hexdigest(presented[len(_VERSION) + 1 :], basestring, material)

    def signed_timestamp(self, headers: tuple[tuple[str, str], ...]) -> int | None:
        raw = header_value(headers, _TIMESTAMP_HEADER)
        if raw is None or not raw.strip().isdigit():
            return None
        return int(raw.strip())
