"""Process-local idempotency — Phase C (ADR 0021; FR-063 to FR-067).

The scope is **one process, one instance, one governed window**, named that way everywhere it is
reported. No replication, sharing, synchronisation or coordination path exists here, so no
distributed deduplication is claimed — and a multi-instance configuration refuses rather than
appearing to provide one (`T083`).

Claiming more would be the expensive kind of wrong: an operator who believes duplicates are
suppressed across instances will run several and find out through a doubled answer.
"""

from __future__ import annotations

__all__: tuple[str, ...] = ()
