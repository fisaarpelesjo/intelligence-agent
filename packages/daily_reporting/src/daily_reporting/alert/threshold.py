"""The alert's threshold, **computed from the series** — `T818` to `T823`.

## Why the threshold is not written down anywhere

Writing a `p90` table into source or into YAML is the **`F136`** failure: a number
correct on the day it is typed and drifting away from the data every day after, while
twenty tests keep passing. `FR-811`, `FR-812`. The evidence table in
`specs/008-daily-report-and-rule-alerts/spec.md` § 9 is **dated evidence for a reader**,
and a node asserts it appears in no file under `packages/`.

## Why the threshold is per KPI and never flat, and the reason is measured

A flat 20 % across the twenty would produce **148 alerts a year** — about three a week —
of which **38 from `Chargeback (%)` alone**, because 20 % relative sits *below that
KPI's own noise*, whose typical variation is 32,4 %. Meanwhile `LTV (US$)`, `MAU`,
`MRR`, `Revenue` and `Paid subscribers` **would never fire at all**. One number cannot
be both above one KPI's noise and below another's. `FR-813`.

## Why a short series gets no alert instead of a smaller threshold

`CAC`'s `p90` today is 158,7 % over **nineteen** weeks. **That number is the hole, not
the business.** A KPI below the minimum still appears in the report with its number and
the footnote; what refuses is the alert — `FR-814`, `FR-820`.

**And the minimum is derived too.** It is half the median comparable-week count across
the KPIs actually present, so it moves as the source's history fills instead of ageing
where it was typed. On the counts measured 2026-08-27 — seventeen KPIs at 53 to 56, and
`Semiannual (%)` at 3, `CAC (R$)` at 19, `Chargeback (qty)` at 26 — that rule excludes
exactly the three the owner named and no others. **The rule was chosen to be derivable,
and it is stated here that it reproduces a known answer**: a rule fitted to a known
answer and never said so is the thing this loop hunts, so it is said.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Final

from ..contracts import ReportReasonCode, ReportRefusal

__all__ = [
    "ALERT_PERCENTILE",
    "minimum_comparable_periods",
    "percentile",
    "refuse_unless_series_is_long_enough",
    "threshold_from",
]

#: The percentile the owner chose: a KPI speaks when it passes the variation of its own
#: worst ten per cent. `OD-14-B`.
ALERT_PERCENTILE: Final = Decimal("0.90")


def percentile(values: Sequence[Decimal], fraction: Decimal) -> Decimal:
    """Linear-interpolated percentile over ``values``, in ``Decimal`` throughout.

    No numeric library, and that is deliberate rather than frugal: a float threshold
    compared against a `Decimal` movement decides governed behaviour on a rounding
    difference nobody can see in the output.
    """
    if not values:
        raise ReportRefusal(
            ReportReasonCode.ALERT_THRESHOLD_NOT_COMPUTABLE,
            "an empty series has no percentile, and no flat threshold is substituted for one",
        )
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = fraction * Decimal(len(ordered) - 1)
    below = int(position)
    above = min(below + 1, len(ordered) - 1)
    weight = position - Decimal(below)
    return ordered[below] + (ordered[above] - ordered[below]) * weight


def threshold_from(variations: Sequence[Decimal]) -> Decimal:
    """This KPI's own alert threshold, computed from its own variation series.

    ``variations`` are magnitudes — a fall of 30 and a rise of 30 are the same size of
    movement, and a threshold built from signed values would sit below the falls and
    above the rises.
    """
    return percentile([abs(variation) for variation in variations], ALERT_PERCENTILE)


def minimum_comparable_periods(counts: Sequence[int]) -> int:
    """The minimum a KPI must reach to be alerted on, **derived from the counts given**.

    **It counted WEEKS until 2026-08-30 and counts DAYS now** — `OD-31` made the comparison
    day against day, and a name saying *weeks* over a count of days is exactly the label that
    stops matching the number. The arithmetic never depended on the unit; the name did.

    Half the median count across the KPIs present, rounded down, and never below two —
    a single comparison has no distribution to take a percentile of.
    """
    if not counts:
        raise ReportRefusal(
            ReportReasonCode.ALERT_THRESHOLD_NOT_COMPUTABLE,
            "no KPI counts were given, so no minimum can be derived from them",
        )
    ordered = sorted(counts)
    middle = len(ordered) // 2
    median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) // 2
    return max(2, median // 2)


def refuse_unless_series_is_long_enough(kpi: str, comparable_periods: int, minimum: int) -> int:
    """``comparable_periods`` back, or the refusal that leaves this KPI alert-free.

    **The report is unaffected.** This refuses an alert and nothing else, which is why
    its code says `alert` and why `FR-814` keeps the KPI on the page.
    """
    if comparable_periods < minimum:
        raise ReportRefusal(
            ReportReasonCode.ALERT_SERIES_TOO_SHORT,
            f"{kpi} has {comparable_periods} comparable periods against a derived minimum of "
            f"{minimum}; its percentile would describe the hole and not the business, so it "
            f"is reported without an alert rather than given a guessed threshold",
        )
    return comparable_periods
