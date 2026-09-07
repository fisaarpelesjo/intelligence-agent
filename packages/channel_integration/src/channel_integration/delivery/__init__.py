"""The delivery boundary — Phase C (ADR 0021; FR-053 to FR-061).

Every attempt terminates in exactly one of six outcomes. There is no absent, implicit or
pending-forever state: silent abandonment, unbounded retry and fire-and-forget do not exist.

The provider side lives in `adapters/`. Nothing here imports an SDK, an endpoint or a credential,
and no provider exception, provider object or provider error text crosses back into the core.
"""

from __future__ import annotations

__all__: tuple[str, ...] = ()
