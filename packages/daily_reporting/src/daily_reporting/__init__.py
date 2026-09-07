"""`008` — the daily KPI report and the rule alert.

**Two products that never merge.** The report carries every KPI the view declares,
every day, with no threshold; the alert carries one KPI when it crosses its own `p90`.
Their entry points are separate and a node asserts neither calls the other.

**Nothing here sends anything.** Origination is governed by `ADR 0036` and belongs to
Phase E, which this package does not contain.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
