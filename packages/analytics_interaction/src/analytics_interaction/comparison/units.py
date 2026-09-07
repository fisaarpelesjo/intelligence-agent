"""Units are carried, never converted — T107 (FR-068; SC-039).

**Two sides with differing declared units are a material mismatch and refuse.**

There is no conversion table in this module and there is deliberately no place to
put one. Not minutes to hours, not cents to reais, not a rate to a count. A unit
conversion is a modelling decision — which currency, which day boundary, which
rate on which date — and every one of those is `001`'s to declare on the metric,
not this feature's to apply on the way past.

The failure a conversion would cause is quiet. Converting seconds to minutes and
comparing produces a number that is *arithmetically* right and *semantically*
somebody else's decision, and the reader cannot see it happened. Refusing is
visible.

**Comparison is exact string equality**, on the unit `002` declared on the metric
column. Not case-insensitive, not whitespace-normalised, not alias-aware:
``"BRL"`` and ``"brl"`` are two strings, and deciding they mean the same thing is
a normalisation rule nobody governed. If a deployment finds that too strict, the
fix is a governed alias in the catalog, not a ``.lower()`` here.

The **result** unit is a third value: the formula's declared ``unit_rule`` from
`D-18`. A ratio's unit is not either operand's unit, and a percentage's is
neither — which is exactly why `D-18` declares it per formula rather than this
feature deriving it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..contracts._base import ContractViolation
from ..contracts.reason_codes import InterpretationReasonCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from analytics_query.contracts.result import AnalyticsResult

    from ..governance.schemas import ComparisonFormula

__all__ = [
    "assert_units_agree",
    "declared_unit",
    "result_unit",
]


def declared_unit(result: AnalyticsResult) -> str:
    """The unit `002` declared on this side's metric column.

    Read from the **metric** column specifically. A result carries dimension
    columns too, and each declares a unit; taking the first column's would pick a
    dimension's unit whenever the shape put one first, and the comparison would
    then be checking that two sides' *dimensions* agreed.

    Exactly one metric column, or refuse. Zero means the side carries no metric
    to compare; more than one means the side answers two questions and picking
    either would be this feature choosing which one the comparison is about.
    """
    metrics = tuple(column for column in result.columns if column.is_metric)
    if len(metrics) != 1:
        raise ContractViolation(
            InterpretationReasonCode.COMPARISON_SIDE_INVALID,
            "a comparison side must carry exactly one metric column",
        )
    return metrics[0].unit


def assert_units_agree(primary: AnalyticsResult, baseline: AnalyticsResult) -> str:
    """The shared unit, or refuse. **Never converted, never reconciled.**

    Returns the unit rather than ``None`` so a caller cannot pass the check and
    then read the unit off whichever side it happened to have — which is how two
    call sites end up disagreeing about which side is authoritative.
    """
    left = declared_unit(primary)
    right = declared_unit(baseline)
    if left != right:
        # The detail names neither unit. A refusal that printed them would
        # disclose the two sides' declared metric shapes to a caller who may hold
        # access to only one of them.
        raise ContractViolation(
            InterpretationReasonCode.COMPARISON_SIDE_INVALID,
            "the two sides declare different units; this is a material mismatch "
            "and no conversion is applied",
        )
    return left


def result_unit(formula: ComparisonFormula) -> str:
    """The unit of the derived figure, taken from `D-18`.

    A function rather than an attribute read, so the one place this value comes
    from is named — and so nothing downstream can be tempted to reach for an
    operand's unit instead when the formula's rule is inconvenient.
    """
    return formula.unit_rule
