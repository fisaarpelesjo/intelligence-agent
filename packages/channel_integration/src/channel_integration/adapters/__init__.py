"""Provider-facing adapters — Phase C (ADR 0020; FR-008, FR-071; SC-033).

The **only** place in this package where a provider artifact may exist. Each adapter implements
`delivery.ports.DeliveryPort` and nothing else: it takes a rendered presentation and a governed
destination, resolves the provider address and the credential material inside itself, sends, and
reports one of the six outcomes.

Three things never cross back into the core: a provider exception, a provider object, and a
provider's own error text (`FR-061`). `T103`'s import gate proves the core cannot reach a provider
SDK, so it cannot break those rules by accident.

**All four are unconstructible today.** `D-22` to `D-25` are undeclared, so no application, bot,
number, token, endpoint or client registry exists — and none is created here. Construction refuses
with ``CHANNEL_NOT_CONFIGURED`` or ``CHANNEL_CREDENTIAL_UNAVAILABLE``, which is the lock rather than
a gap.
"""

from __future__ import annotations

__all__: tuple[str, ...] = ()
