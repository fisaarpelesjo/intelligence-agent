"""Degenerate thresholds are refused at construction — T022.

**This file previously locked a falsehood in place, and that is why it is written
this way now.** It asserted that a *negative* threshold produced `NEVER_FIRABLE`,
while its own docstring said the same threshold was *"crossed by everything"*.
Both cannot be true: ``abs(x) >= -5`` holds for every ``x``, so such a rule fires
on **everything**. One pathology hides a KPI and the other floods an operator, and
the run published the wrong one as fact.

A test that asserts a mistake makes the mistake load-bearing. The fix is at the
root — `Rule` refuses a threshold that is not strictly positive — so the three
degenerate cases die before a comparison is ever attempted:

| threshold | comparison | what the rule would do |
|---|---|---|
| `NaN` | always false | permanently silent, **looking healthy** |
| negative | always true | permanently firing, **looking like detection** |
| zero | true at `0` | reports *"nothing moved"* **as an anomaly** |

The third is the one this feature exists to prevent, and the second and third were
found by review rather than by design.
"""

from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from anomaly_investigation.contracts import (
    AggregationClass,
    AnomalyReasonCode,
    DetectionMethod,
    Rule,
)
from anomaly_investigation.detect import ThresholdOutcome, ThresholdVerdict, assess_threshold
from anomaly_investigation.detect import threshold as threshold_module

pytestmark = pytest.mark.unit


def _rule(*, threshold: str) -> Rule:
    return Rule(
        rule_id="trials_drop",
        metric="trials",
        method=DetectionMethod.PERCENTAGE_CHANGE,
        aggregation_class=AggregationClass.COUNT,
        formula_id="period_over_period",
        threshold=Decimal(threshold),
        tolerance=Decimal("0.01"),
        period="july_2026",
        baseline_period="june_2026",
    )


# --------------------------------------------------------------------------- #
# The three degenerate thresholds, refused where the NaN already was
# --------------------------------------------------------------------------- #


def test_a_negative_threshold_is_refused_at_construction() -> None:
    """It is not *uncrossable* — it is **crossed by everything**.

    Reporting it as never-firable sent an operator to look for a rule that was
    hiding a KPI, when the rule was about to flood them.
    """
    with pytest.raises(ValidationError):
        _rule(threshold="-5")


def test_a_zero_threshold_is_refused_at_construction() -> None:
    """`abs(0) >= 0` is true, so a zero threshold fires on **no movement at all**.

    *"Nothing moved"* reported as an anomaly is the single inference this feature
    exists never to produce. A rule that wants to fire on any movement declares
    the smallest unit that matters to it — a governed decision — rather than
    declaring zero and firing on silence.
    """
    with pytest.raises(ValidationError):
        _rule(threshold="0")


def test_a_non_finite_threshold_is_refused_at_construction() -> None:
    """The mirror case, and the one that was already closed: every comparison
    against `NaN` is false, so the rule is permanently silent while looking
    healthy."""
    with pytest.raises(ValidationError):
        _rule(threshold="NaN")


def test_the_smallest_positive_threshold_is_accepted() -> None:
    """The refusals above would be vacuous over a field nothing satisfies.

    And this is the honest form of *"any movement"*: a stated unit, not a zero.
    """
    rule = _rule(threshold="0.0001")
    assert rule.threshold == Decimal("0.0001")


# --------------------------------------------------------------------------- #
# What survives: quiet is quiet, and a movement is a movement
# --------------------------------------------------------------------------- #


def test_a_rule_that_did_not_cross_is_quiet_and_carries_no_reason() -> None:
    outcome = assess_threshold(
        _rule(threshold="10"), observed=Decimal("1"), observed_class=AggregationClass.COUNT
    )
    assert outcome.verdict is ThresholdVerdict.DID_NOT_CROSS
    assert outcome.reason_code is None


def test_no_movement_at_all_is_quiet_rather_than_an_anomaly() -> None:
    """With the zero threshold gone, `observed=0` can only ever be silence."""
    outcome = assess_threshold(
        _rule(threshold="0.0001"), observed=Decimal("0"), observed_class=AggregationClass.COUNT
    )
    assert outcome.verdict is ThresholdVerdict.DID_NOT_CROSS


def test_a_non_finite_movement_is_refused_rather_than_compared() -> None:
    """The threshold is guarded at construction; **the observation is not**, because
    it arrives from upstream at runtime. So this side is checked here."""
    outcome = assess_threshold(
        _rule(threshold="10"), observed=Decimal("NaN"), observed_class=AggregationClass.COUNT
    )
    assert outcome.verdict is ThresholdVerdict.REFUSED
    assert outcome.reason_code is AnomalyReasonCode.ANOMALY_FIGURE_UNAVAILABLE


# --------------------------------------------------------------------------- #
# The vocabulary with no reachable producer, asserted as such
# --------------------------------------------------------------------------- #


def test_no_code_path_produces_never_firable() -> None:
    """**The debt, asserted over the code rather than over a sample of inputs.**

    An earlier version of this test swept twelve input combinations and claimed
    *"this test fails the day a producer appears"*. **Twelve samples cannot carry
    that sentence:** a producer branching on aggregation class, on metric bounds
    from the catalog, or on any input outside those twelve would pass underneath
    it, and the test would stay green while asserting there was none. The same
    sentence had reached the authoritative reason-code table, which is governed
    text — so a producer appearing unseen would have made **the table** assert
    something false in silence.

    That is the defect this repository already names: *a promise that survives its
    own falsification is worse than no promise, because the next reader builds on
    it.*

    So this reads the module's syntax tree, the way `004`'s `test_reactive_only.py`
    does. **It fails by construction the day somebody writes the branch**, with no
    dependence on the right input being in a sample.

    **Both spellings are checked, and the second was a finding against the first
    version of this scan.** A producer written with string literals —
    `verdict="never_firable"` — is accepted by the contract, because both enums are
    `StrEnum` and pydantic converts. It contains no `Attribute`, so a scan looking
    only for named access sees nothing. Measured, not imagined.

    `NEVER_FIRABLE` is still constructible by hand — the contract keeps guarding
    its shape, and the test below proves it. What no longer exists is a path in
    `assess_threshold` that returns one.
    """
    source = Path(threshold_module.__file__ or "").read_text(encoding="utf-8")
    tree = ast.parse(source)

    returned: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        for inner in ast.walk(node.value):
            named = isinstance(inner, ast.Attribute) and inner.attr == "NEVER_FIRABLE"
            # **The literal spelling, and it is the one that escaped.** Both enums
            # are `StrEnum`, so pydantic accepts `verdict="never_firable"` and
            # returns a real `ThresholdVerdict`. A producer written entirely with
            # strings works and contains no `Attribute` at all.
            spelled = (
                isinstance(inner, ast.Constant)
                and inner.value == ThresholdVerdict.NEVER_FIRABLE.value
            )
            if named or spelled:
                returned.append(ast.unparse(node.value)[:60])

    assert not returned, f"a producer of NEVER_FIRABLE appeared: {returned}"

    # The walk reached something, so the emptiness above is measured rather than
    # vacuous -- the lesson `test_the_walk_reaches_the_package` applies here too.
    assert "def assess_threshold" in source
    assert any(isinstance(n, ast.Return) for n in ast.walk(tree))


def test_the_uncrossable_reason_code_has_no_producer_either() -> None:
    """The reason code travels with the verdict, so it is checked the same way.

    Asserting only the verdict would leave the governed word free to appear
    somewhere else in the module.
    """
    source = Path(threshold_module.__file__ or "").read_text(encoding="utf-8")
    tree = ast.parse(source)
    code = AnomalyReasonCode.ANOMALY_RULE_THRESHOLD_UNCROSSABLE
    mentions = [
        ast.unparse(node)
        for node in ast.walk(tree)
        if (isinstance(node, ast.Attribute) and node.attr == code.name)
        or (isinstance(node, ast.Constant) and node.value == code.value)
    ]
    assert not mentions, f"the uncrossable code reappeared in code: {mentions}"


def test_the_outcome_still_refuses_a_never_firable_without_a_reason() -> None:
    """The contract keeps guarding the shape even with no producer.

    Deleting the guard because nothing reaches it today would leave the next
    producer unguarded.
    """
    with pytest.raises(ValidationError):
        ThresholdOutcome(rule_id="r", verdict=ThresholdVerdict.NEVER_FIRABLE)
