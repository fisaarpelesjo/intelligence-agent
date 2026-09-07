"""Pseudonymisation, and the key material nobody has declared — T045 (`D-31`; FR-077; SC-037).

Every record this feature emits carries a **pseudonymous stable reference** to an external
identity, never the phone number, member id, chat id, handle, display name or email.

Stable, so a journey is joinable across the six audit stages. Non-reversible, so the trail is
not a directory of everyone who ever asked a question. That pair requires **keyed** material,
and nothing upstream provides it: `D-31`, undeclared (`research.md` `R-13`).

Two substitutes were considered and both rejected:

* an **unkeyed hash** of a phone number is reversible by brute force over the number space —
  a directory with extra steps;
* a **per-process salt** breaks stability, so the same person becomes a new identity on every
  restart and the trail stops being joinable, defeating `FR-084`.

So while `D-31` is undeclared no reference is constructible, and every flow that needs one
refuses with ``CHANNEL_AUDIT_UNAVAILABLE`` before delivery (`FR-083`). The port below is the
only way material ever arrives: injected, never read from a file, an environment variable or a
constant in this repository.

**The same port derives scoped conversation references** (`identity.scope`). That is
deliberate: a conversation reference derived from an external identity is pseudonymisation by
another name, and letting it use a weaker mechanism would put the strong rule beside a hole.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Protocol, runtime_checkable

from ..contracts._base import ChannelViolation
from ..contracts.reason_codes import ChannelReasonCode

__all__ = ["KeyedPseudonymiser", "PseudonymPort", "unavailable_pseudonymiser"]


@runtime_checkable
class PseudonymPort(Protocol):
    """Derives stable, non-reversible references under `D-31` material."""

    #: Which key version produced a reference, so a rotation is legible: two references under
    #: different versions are different references and nothing treats them as one identity.
    key_version: str

    def derive(self, label: str, *parts: str) -> str:
        """A reference for ``parts``, scoped by ``label``. Refuses when unavailable."""
        ...


class KeyedPseudonymiser:
    """HMAC-SHA-256 over the labelled parts, hex-encoded.

    ``label`` separates domains so a reference derived for an audit actor cannot collide with
    one derived for a conversation scope, even given identical parts. The parts are joined with
    a separator that cannot appear in them after escaping, so `("a|b", "c")` and `("a", "b|c")`
    do not produce the same reference — an ambiguity that would silently merge two identities.
    """

    __slots__ = ("_key", "key_version")

    def __init__(self, key: bytes, key_version: str) -> None:
        if len(key) < 32:
            raise ValueError("pseudonymisation key material must be at least 32 bytes")
        if not key_version.strip():
            raise ValueError("pseudonymisation key material must declare a version")
        self._key = key
        self.key_version = key_version

    def derive(self, label: str, *parts: str) -> str:
        escaped = "|".join(part.replace("\\", "\\\\").replace("|", "\\|") for part in parts)
        message = f"{label}\x1f{escaped}".encode()
        return hmac.new(self._key, message, hashlib.sha256).hexdigest()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"KeyedPseudonymiser(key_version={self.key_version!r}, key=<redacted>)"


class _Unavailable:
    """The shipped state: no material, so no reference, so the flow refuses.

    A port that refuses rather than a ``None`` a caller might forget to check. Every call site
    obtains a reference the same way, and the absence of `D-31` surfaces as a governed refusal
    instead of a ``NoneType`` reaching an audit event.
    """

    key_version = "undeclared"

    def derive(self, label: str, *parts: str) -> str:
        raise ChannelViolation(
            ChannelReasonCode.CHANNEL_AUDIT_UNAVAILABLE,
            "no pseudonymisation key material is declared (D-31)",
        )


def unavailable_pseudonymiser() -> PseudonymPort:
    """The production port while `D-31` is undeclared.

    A function rather than a singleton so nothing can mutate a shared instance into something
    that answers.
    """
    return _Unavailable()
