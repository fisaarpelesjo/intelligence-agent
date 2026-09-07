"""The governed detection rule — T006.

A rule is **configuration, and its content is the owner's decision**: which metric,
which threshold and which baseline matter to the business is not ours to choose.
This module governs the *shape* a rule must have to be executable at all.

Two of its fields exist because the upstream signatures demand them, measured in
``research.md`` § 2: ``classify_direction`` requires ``tolerance`` **with no
default**, so a rule must state its own; and ``resolve_formula`` takes a
``formula_id``, so a rule names the governed formula rather than describing an
operation.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import Field, field_validator

from ._base import AnomalyModel, GovernedName

__all__ = ["AggregationClass", "DetectionMethod", "Rule"]


class DetectionMethod(StrEnum):
    """The baseline's ``business_rules`` methods — **closed at eight**.

    Read from ``proactive_insights.detection_levels.business_rules.methods``,
    which the baseline declares ``priority: first``. A ninth method is a baseline
    change and a decision, not a task.

    ``robust_statistics`` is the baseline's *second* level and is ``enabled:
    true`` — it is out of scope here by **priority, not prohibition**.
    ``time_series_models`` is the third and is ``enabled: false``, which `FR-002`
    forbids enabling.
    """

    ABSOLUTE_CHANGE = "absolute_change"
    PERCENTAGE_CHANGE = "percentage_change"
    PREVIOUS_PERIOD = "previous_period"
    PREVIOUS_WEEK = "previous_week"
    PREVIOUS_MONTH = "previous_month"
    MINIMUM_VOLUME = "minimum_volume"
    PLATFORM_DIFFERENCE = "platform_difference"
    POST_RELEASE_CHANGE = "post_release_change"


class AggregationClass(StrEnum):
    """The three classes `004` measured as **not interchangeable**.

    A rule written for one and applied to another is refused (`FR-010`), and the
    refusal names the class it was written for (`SC-006`). Averaging across them
    is the failure this enum exists to make impossible to reach by accident.
    """

    RATIO = "ratio"
    COUNT = "count"
    SNAPSHOT = "snapshot"


class Rule(AnomalyModel):
    """One governed detection rule.

    **Identity is stable because a candidate names it.** Renaming a rule produces
    a different rule, not the same rule renamed — which matters the moment
    deduplication arrives, because the baseline's fingerprint includes
    ``rule_id``.
    """

    rule_id: GovernedName = Field(description="Stable identity. A candidate names it.")
    metric: GovernedName = Field(
        description="Resolved through `001`. An unbound metric refuses upstream (FR-001)."
    )
    method: DetectionMethod
    aggregation_class: AggregationClass = Field(
        description="The class this rule was written for. Named in a mismatch refusal."
    )
    formula_id: GovernedName = Field(
        description="Passed to `003`'s resolve_formula. The arithmetic is never ours (FR-003)."
    )
    threshold: Decimal = Field(
        gt=0,
        description=(
            "Exact and strictly positive. Never float -- the upstream comparison "
            "arithmetic is Decimal throughout."
        ),
    )
    tolerance: Decimal = Field(
        ge=0,
        description=(
            "Stated by the rule because classify_direction requires it and has no default. "
            "The detector may not silently pick one."
        ),
    )
    period: GovernedName = Field(
        description="A catalog period name. **Not a date** — this feature computes none (FR-012)."
    )
    baseline_period: GovernedName = Field(description="The catalog period compared against.")

    @field_validator("threshold")
    @classmethod
    def _threshold_is_finite(cls, value: Decimal) -> Decimal:
        """``NaN`` and infinity are refused at construction.

        A ``NaN`` threshold is never crossed and never *fails* to be crossed —
        every comparison against it is false — so a rule carrying one would be
        permanently silent while looking healthy.

        **Two more degenerate thresholds are refused by ``gt=0`` above, and both
        were found by review rather than by design.** The comparison is
        ``abs(observed) >= threshold``, so:

        * a **negative** threshold is satisfied by every observation, including
          none at all — the rule fires on everything and floods;
        * a **zero** threshold is satisfied by ``0`` — the rule reports *"nothing
          moved"* **as an anomaly**, which is the single inference this feature
          exists never to produce.

        They are the mirror of the ``NaN`` case: there the comparison is always
        false and the rule is permanently silent while looking healthy; here it is
        always true and the rule is permanently firing while looking like
        detection. **All three are refused in one place — at construction —
        because a threshold that makes the comparison degenerate is not a
        threshold.**

        A rule that should fire on *any* movement declares the smallest unit that
        matters to it, which is a governed decision. It does not declare zero and
        fire on silence.
        """
        if not value.is_finite():
            raise ValueError("threshold must be finite")
        return value
