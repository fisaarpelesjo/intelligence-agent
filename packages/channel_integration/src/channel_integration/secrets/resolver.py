"""The secret resolver port — T047 (FR-068, FR-071, FR-073; SC-032, SC-033).

The **only** way material ever appears, and it appears adapter-side.

`SecretRef` names material; this port turns a name into
:class:`~channel_integration.inbound.schemes.VerificationMaterial`. The core calls it exactly
once per inbound message, hands the result straight to the scheme, and keeps no reference to it
afterwards — so the window in which material exists is one function call wide.

**Absent is the shipped state, and absent refuses.** `D-22` to `D-25` are undeclared, so
:class:`UnavailableSecretResolver` is what production uses: every reference resolves to
``None``, `inbound.verify` refuses with ``CHANNEL_VERIFICATION_UNAVAILABLE``, and no
unauthenticated, sandbox or best-effort mode exists (`FR-073`).

**No fallback, no default, no generation.** A resolver that manufactured material would turn an
undeclared dependency into a working channel, which is the one thing the fail-closed posture
exists to prevent.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..inbound.schemes import VerificationMaterial
from .ref import SecretRef

__all__ = ["SecretResolver", "UnavailableSecretResolver"]


@runtime_checkable
class SecretResolver(Protocol):
    """Resolves a named reference to verification material, or to ``None``.

    ``None`` means *not available*, which is a governed state, not an error: the caller refuses
    with ``CHANNEL_VERIFICATION_UNAVAILABLE`` and the message never reaches interpretation.

    Implementations live **outside** the governed core, beside the provider they serve. No
    module the core reaches may import one (`FR-071`, asserted by `T028` and `T103`).
    """

    def material_for(self, ref: SecretRef) -> VerificationMaterial | None:
        """Material for ``ref``, or ``None`` when its record is undeclared."""
        ...


class UnavailableSecretResolver:
    """What production uses today: nothing resolves.

    Explicit rather than implicit. A missing resolver would be a ``None`` somebody could forget
    to check; a resolver that answers "unavailable" makes the fail-closed path the ordinary
    path, exercised by every test that does not inject a fixture.
    """

    def material_for(self, ref: SecretRef) -> VerificationMaterial | None:
        return None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "UnavailableSecretResolver()"
