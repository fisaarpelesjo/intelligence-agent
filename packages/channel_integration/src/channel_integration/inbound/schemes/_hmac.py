"""Shared HMAC mechanics for the schemes that use them — Phase B (FR-012; SC-004).

Three of the four schemes are HMAC-over-a-basestring; what differs is **which** basestring
and which header carries the digest. That difference is the scheme; the comparison is not,
and duplicating a constant-time comparison four times is how one copy eventually becomes
`==`.

Two rules live here and nowhere else:

* comparison is `hmac.compare_digest`, always, over the hex digests;
* retired material is tried **after** the active material and reports its own detail class,
  so a rotation is legible instead of looking like a mismatch (`FR-074`).
"""

from __future__ import annotations

import hashlib
import hmac

from ...contracts.audit import DetailClass
from . import VerificationMaterial, VerificationOutcome

__all__ = ["header_value", "hexdigest", "verify_hexdigest"]


def header_value(headers: tuple[tuple[str, str], ...], name: str) -> str | None:
    """One header value by case-insensitive name, or ``None``.

    Header **names** are consumed; values reach no log, trace, audit event or refusal.
    """
    lowered = name.lower()
    for key, value in headers:
        if key.lower() == lowered:
            return value
    return None


def hexdigest(secret: str, basestring: bytes) -> str:
    """SHA-256 HMAC of ``basestring`` under ``secret``, as lowercase hex."""
    return hmac.new(secret.encode("utf-8"), basestring, hashlib.sha256).hexdigest()


def verify_hexdigest(
    presented: str | None,
    basestring: bytes,
    material: VerificationMaterial,
) -> VerificationOutcome:
    """Compare a presented hex digest against the material, in constant time.

    Absent, malformed, mismatched and retired-material cases each get their own detail
    class for the operator, and all four return the **same** governed code to the sender.
    """
    if presented is None or not presented.strip():
        return VerificationOutcome.failed(DetailClass.SIGNATURE_ABSENT)

    candidate = presented.strip()
    if len(candidate) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in candidate):
        return VerificationOutcome.failed(DetailClass.SIGNATURE_MALFORMED)

    expected = hexdigest(material.active, basestring)
    if hmac.compare_digest(expected, candidate.lower()):
        return VerificationOutcome.verified()

    for retired in material.retired:
        if hmac.compare_digest(hexdigest(retired, basestring), candidate.lower()):
            # Correct signature, withdrawn key. Refused, and named as such: a rotation that
            # silently kept accepting the old key would not be a rotation.
            return VerificationOutcome.failed(DetailClass.SIGNATURE_RETIRED_MATERIAL)

    return VerificationOutcome.failed(DetailClass.SIGNATURE_MISMATCH)
