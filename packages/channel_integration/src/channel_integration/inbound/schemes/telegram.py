"""Telegram verification scheme — T035 (`D-24` undeclared; FR-010 — FR-012).

A shared secret token presented in its own header, compared in **constant time**.

This scheme is weaker than the other three by construction, and the weakness is recorded
rather than smoothed over: a bearer token proves the sender knows a secret, it does **not**
bind the body. So integrity of the payload rests on transport security alone, and a message
whose body was altered in flight cannot be detected by this scheme.

Two consequences, both stated rather than mitigated by invention:

* no signed timestamp, so no replay window is evaluable for this channel;
* no body binding, so `D-24` must be provisioned with that in mind — which is the platform
  owner's decision to record, not this feature's to compensate for.

**No bot, token or credential is created here.** `D-24` is undeclared.
"""

from __future__ import annotations

import hmac

from ...contracts.audit import DetailClass
from . import VerificationMaterial, VerificationOutcome
from ._hmac import header_value

__all__ = ["TelegramScheme"]

_TOKEN_HEADER = "x-telegram-bot-api-secret-token"


class TelegramScheme:
    """Constant-time comparison of a shared secret token."""

    name = "telegram-secret-token"
    provides_signed_timestamp = False

    def verify(
        self,
        body: bytes,
        headers: tuple[tuple[str, str], ...],
        material: VerificationMaterial,
    ) -> VerificationOutcome:
        presented = header_value(headers, _TOKEN_HEADER)
        if presented is None or not presented.strip():
            return VerificationOutcome.failed(DetailClass.SIGNATURE_ABSENT)

        candidate = presented.strip()
        if hmac.compare_digest(material.active, candidate):
            return VerificationOutcome.verified()
        for retired in material.retired:
            if hmac.compare_digest(retired, candidate):
                return VerificationOutcome.failed(DetailClass.SIGNATURE_RETIRED_MATERIAL)
        return VerificationOutcome.failed(DetailClass.SIGNATURE_MISMATCH)

    def signed_timestamp(self, headers: tuple[tuple[str, str], ...]) -> int | None:
        return None
