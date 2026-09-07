"""Verification schemes — T032 (ADR 0020; FR-010, FR-012; SC-004).

A scheme answers **one** question: *do this body, these headers and this material agree?*
Modelling the question rather than the algorithms is what keeps the core free of provider
specifics and lets a scheme be replaced without touching anything else (`FR-089`, `R-4`).

**The scheme is named by the descriptor, never inferred from the payload.** A payload that
selected its own verification scheme would be authentication by suggestion.

**Every failure mode returns the same code.** ``CHANNEL_SIGNATURE_INVALID`` covers absent,
malformed, wrong-body, retired-material and wrong-channel signatures, because
distinguishing them tells an attacker which half of the scheme they got right (ADR 0018).
The distinguishing detail travels as a :class:`DetailClass` for the audit trail and is never
returned to a sender.

``provides_signed_timestamp`` is part of the scheme, not of the message: Slack and the
generic client sign a timestamp, WhatsApp and Telegram do not. A message with no signed
timestamp **where the scheme provides one** is refused; where the scheme provides none, the
replay window cannot be evaluated and that limit is stated rather than faked
(`inbound.verify`).

No cryptographic dependency: `hmac`, `hashlib` and `secrets` are standard library, and
`hmac.compare_digest` is the constant-time comparison `FR-012` requires.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import Field

from ...contracts._base import ChannelModel
from ...contracts.audit import DetailClass

__all__ = [
    "VerificationMaterial",
    "VerificationOutcome",
    "VerificationScheme",
]


class VerificationMaterial(ChannelModel):
    """Key material for one channel, as a scheme receives it.

    Resolved from a `SecretRef` inside the adapter and handed to the scheme as an opaque
    value. It exists as a model so a scheme cannot be called with a bare string that a log
    line might later print; `secrets.ref` keeps the value unprintable up to this point.

    ``retired`` carries material that is no longer accepted. It is present so a rotation is
    **explicit**: a signature made with retired material refuses with its own detail class
    rather than passing because the old key was still in a list (`FR-074`).
    """

    #: The material in force. Never logged, never serialised into an event.
    active: str = Field(min_length=1, repr=False)
    #: Material that has been rotated out. A match here refuses.
    retired: tuple[str, ...] = ()


class VerificationOutcome(ChannelModel):
    """Whether a message verified, and — for an operator — which mode failed."""

    ok: bool
    detail: DetailClass = DetailClass.NONE

    @classmethod
    def verified(cls) -> VerificationOutcome:
        return cls(ok=True, detail=DetailClass.NONE)

    @classmethod
    def failed(cls, detail: DetailClass) -> VerificationOutcome:
        return cls(ok=False, detail=detail)


@runtime_checkable
class VerificationScheme(Protocol):
    """One channel's answer to *do these agree?*

    Implementations are pure: same body, headers, material and signed timestamp handling
    produce the same outcome, every time, with no clock read and no network call.
    """

    #: Stable name, matched against `ChannelDescriptor.verification_scheme`.
    name: str
    #: Does this scheme sign a timestamp the replay window can be evaluated against?
    provides_signed_timestamp: bool

    def verify(
        self,
        body: bytes,
        headers: tuple[tuple[str, str], ...],
        material: VerificationMaterial,
    ) -> VerificationOutcome:
        """Verify authenticity and integrity over the **received bytes**."""
        ...

    def signed_timestamp(self, headers: tuple[tuple[str, str], ...]) -> int | None:
        """The signed epoch second, or ``None`` when the scheme provides none."""
        ...
