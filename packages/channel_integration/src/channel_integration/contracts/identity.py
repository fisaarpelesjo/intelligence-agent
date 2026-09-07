"""External identity and its governed binding — T009 (FR-019, FR-077; SC-010, SC-037).

Three types, and the distinction between them is the privacy boundary:

* ``ExternalIdentity`` — the raw provider-side identifier. **Opaque, redacted in
  ``repr`` and ``str``, never logged, audited, persisted or rendered.**
* ``ExternalIdentityRef`` — the pseudonymous stable reference that appears in
  records. Derived under `D-31` key material, which is **undeclared**, so no
  reference is constructible today and every flow needing one refuses with
  ``CHANNEL_AUDIT_UNAVAILABLE`` (`research.md` `R-13`).
* ``ChannelIdentityBinding`` — one governed mapping from an external identity to
  exactly one principal within one tenant.

**Resolution returns one binding or one refusal.** Ambiguity, revocation, expiry
and multiplicity all collapse to ``CHANNEL_IDENTITY_UNMAPPED``: distinguishing them
describes the registry's shape to an unauthenticated caller, and "revoked" in
particular confirms the identity once existed (ADR 0018).

The resolver itself is Phase B (T042). This module declares only what a binding
*is*, so the contract exists before anything reads it.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from ._base import ChannelModel, PrincipalRef, TenantId
from .descriptor import ChannelId

__all__ = [
    "BindingStatus",
    "ChannelIdentityBinding",
    "ExternalIdentity",
    "ExternalIdentityRef",
]


class ExternalIdentity:
    """A raw provider-side identifier, held opaquely.

    Not a model and not a string subclass, deliberately: the value must not be
    serialisable by accident, formattable into a log line, or comparable to a plain
    string. ``repr`` and ``str`` are redacted, so an exception traceback, a debug
    print, a pydantic error and an f-string all yield the same non-disclosing text.

    Equality is by value so a registry lookup works; hashing follows equality so a
    binding can be keyed. Neither exposes the value.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        if not value or not value.strip():
            raise ValueError("an external identity may not be blank")
        self._value = value

    def reveal(self) -> str:
        """The raw identifier, for a verification or registry lookup only.

        Named ``reveal`` rather than ``value`` so that every disclosure is visible
        at the call site and greppable in review. No module in this feature may
        call it on a path that reaches a log, a trace, an audit event, an
        idempotency record or an outbound payload.
        """
        return self._value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ExternalIdentity) and other._value == self._value

    def __hash__(self) -> int:
        return hash(("ExternalIdentity", self._value))

    def __repr__(self) -> str:
        return "ExternalIdentity(<redacted>)"

    def __str__(self) -> str:
        return "<redacted>"


class ExternalIdentityRef(ChannelModel):
    """The pseudonymous stable reference that may appear in a record.

    Stable so a journey is joinable across the six audit stages; non-reversible so
    the audit trail is not a directory of everyone who ever asked a question. That
    combination requires keyed material — `D-31` — and an unkeyed hash of a phone
    number is reversible by brute force over the number space while a per-process
    salt breaks stability. Neither is a substitute, so while `D-31` is undeclared
    **no instance of this type is constructible on the request path** and the flow
    refuses (`R-13`).

    ``key_version`` is required so a rotation is legible: two references derived
    under different key versions are different references, and nothing silently
    treats them as one identity.
    """

    value: str = Field(min_length=16)
    key_version: str = Field(min_length=1)


class BindingStatus(StrEnum):
    """Anything but ``ACTIVE`` refuses, under one collapsed code."""

    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class ChannelIdentityBinding(ChannelModel):
    """One governed mapping: external identity → principal, within a tenant.

    Resolved from the `D-27` registry, **never** created, inferred, defaulted or
    accepted from a message (`FR-018`). This feature declares the shape; the
    registry's content and its administration belong to `D-27` and to whoever owns
    it (`NG-5`).
    """

    channel: ChannelId
    tenant: TenantId
    #: Exactly one principal. A binding to several refuses rather than choosing
    #: (`R-7`), and the collapsed code discloses nothing about why.
    principal_ref: PrincipalRef
    status: BindingStatus
    #: The `D-27` registry version this binding was read under, so a resolution is
    #: attributable to a governance state rather than to "the registry, at some
    #: point".
    binding_version: str = Field(min_length=1)

    @property
    def usable(self) -> bool:
        """Is this binding usable for a submission?

        A property rather than a status comparison at each call site, so the one
        rule has one home and a fourth status could not be silently treated as
        acceptable by a call site that forgot to check it.
        """
        return self.status is BindingStatus.ACTIVE
