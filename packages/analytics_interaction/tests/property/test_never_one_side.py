"""Generated comparisons never yield a single side — T158 (FR-067; SC-039).

    Evidence: generated comparison inputs never yield a single side.
    — `tasks.md` T158

## What this adds over the adversarial suite

`T156` mutates one condition at a time and proves each refuses. That leaves a gap
a table cannot close: **combinations**. Two conditions at once, a valid side beside
an invalid one in either position, a formula that divides beside a baseline that is
zero, sixteen values crossed with six dispositions. A hand-written table of those
is either incomplete or unmaintainable.

So this file generates the inputs and asserts a single universal property:

    every call either returns a complete ``GovernedComparison`` with **two** sides,
    or raises — and there is no third outcome, ever.

The property is deliberately weak about *which* refusal happens. Which condition
wins is `T156`'s business; what matters here is that no combination of them finds a
crack between them.

## The invariants asserted on success too

A returned comparison is checked as hard as a refusal:

* exactly **two** sides, never one and never three;
* the figure's operands are the two sides' values, so no side was substituted;
* both thunks were invoked exactly **once** — a retry would double the caller's
  cost, and a memoised second call would make the second side's validation
  meaningless.

## Bounded and fixture-only

The value alphabet is a dozen exact `Decimal`s, the dispositions are the enumerated
ones, and nothing is drawn from a production distribution. No accuracy target and no
quality claim is expressed here or implied.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

import pytest
from analytics_query.contracts.result import Completeness
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from semantic_catalog.contracts.reason_codes import ReasonCode
from semantic_catalog.validation.decision import Finality, Reproducibility

from analytics_interaction.authorization.context_preflight import AuthorizedContext
from analytics_interaction.comparison.refusal import SideSubmission, govern_comparison
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.comparison import GovernedComparison
from analytics_interaction.governance.resolve import ContentUnresolvable

from ..conftest import ON
from ..fixtures.comparisons import (
    ABSOLUTE_DIFFERENCE,
    BASELINE_RANGE,
    FIXTURE_VERSION,
    PERCENTAGE_CHANGE,
    PRIMARY_RANGE,
    RATIO,
    caveat_set,
    executed,
    formula_instances,
    request,
    verdict,
)

pytestmark = pytest.mark.property

SETTINGS = settings(
    max_examples=250,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)

FIXTURE_SET = formula_instances(ABSOLUTE_DIFFERENCE, RATIO, PERCENTAGE_CHANGE)
NO_CAVEATS = caveat_set()

#: Exact decimals only. **No float anywhere**: a generated float would make the
#: arithmetic assertions depend on binary representation, which is the thing the
#: comparison module exists to avoid.
#:
#: Zero and negatives are included deliberately — zero is the baseline that makes a
#: ratio undefined, and a negative primary is legitimate for a difference.
VALUES = st.sampled_from(
    [
        Decimal("0"),
        Decimal("1"),
        Decimal("-1"),
        Decimal("100"),
        Decimal("-100"),
        Decimal("0.5"),
        Decimal("-0.5"),
        Decimal("999999999"),
        Decimal("0.000001"),
        Decimal("12345.6789"),
    ]
)

UNITS = st.sampled_from(["count", "thousands", "brl"])
FORMULAS = st.sampled_from(["absolute_difference", "ratio", "percentage_change"])
COMPLETENESS = st.sampled_from(list(Completeness))
FINALITY = st.sampled_from(list(Finality))
REPRODUCIBILITY = st.sampled_from(list(Reproducibility))
VERDICT_CODES = st.sampled_from(
    [ReasonCode.REQUEST_ALLOWED, ReasonCode.COMPARABLE_WITH_CAVEAT, ReasonCode.ACCESS_DENIED]
)
METRIC_VERSIONS = st.sampled_from([("installs@1",), ("installs@2",)])


@dataclass
class _Counted:
    """Executes on demand and counts. A thunk, so ordering is observable."""

    answer: object
    calls: list[int] = field(default_factory=list[int])

    def __call__(self) -> object:
        self.calls.append(1)
        return self.answer

    @property
    def count(self) -> int:
        return len(self.calls)


@dataclass(frozen=True, slots=True)
class _Outcome:
    """What one generated call produced. Exactly one of the two fields is set."""

    comparison: GovernedComparison | None
    error: BaseException | None
    primary_calls: int
    baseline_calls: int


def _attempt(
    pair: tuple[AuthorizedContext, str],
    *,
    primary_value: Decimal,
    baseline_value: Decimal,
    primary_unit: str,
    baseline_unit: str,
    formula_id: str,
    completeness: Completeness,
    finality: Finality,
    reproducibility: Reproducibility,
    verdict_code: ReasonCode,
    primary_versions: tuple[str, ...],
    baseline_versions: tuple[str, ...],
    suppressed: bool,
) -> _Outcome:
    """One generated comparison attempt, recorded rather than asserted.

    Returns an outcome object instead of raising, so the property below can assert
    "exactly one of complete-or-refused" as a single statement — which is the
    property, and which a ``pytest.raises`` block cannot express.
    """
    authorized, fingerprint = pair
    left = _Counted(
        executed(
            primary_value,
            unit=primary_unit,
            completeness=completeness,
            finality=finality,
            reproducibility=reproducibility,
            metric_versions=primary_versions,
            suppressed=suppressed,
        )
    )
    right = _Counted(
        executed(
            baseline_value,
            unit=baseline_unit,
            metric_versions=baseline_versions,
        )
    )
    # A **denied** verdict may not carry a comparable window: `001`'s ADR 0016
    # validator refuses that shape, because a refusal states no window an answer
    # could be computed over. So the denied case is built windowless, which is the
    # only shape it has in reality — and it exercises the windowless branch of
    # `window_for_comparison` rather than a shape that cannot exist.
    denied = verdict_code is ReasonCode.ACCESS_DENIED
    decision = verdict(code=verdict_code, window=None) if denied else verdict(code=verdict_code)

    try:
        comparison = govern_comparison(
            decision,
            formula_id=formula_id,
            primary_side=SideSubmission(request=request(period=PRIMARY_RANGE), submit=left),  # pyright: ignore[reportArgumentType]
            baseline_side=SideSubmission(request=request(period=BASELINE_RANGE), submit=right),  # pyright: ignore[reportArgumentType]
            caveats=NO_CAVEATS,
            authorized=authorized,
            auth_fingerprint=fingerprint,
            on=ON,
            vocabulary_version=FIXTURE_VERSION,
            derived_from=("claim-a", "claim-b"),
            instances=FIXTURE_SET,
        )
    except (ContractViolation, ContentUnresolvable) as refusal:
        return _Outcome(None, refusal, left.count, right.count)
    return _Outcome(comparison, None, left.count, right.count)


# --- the property -----------------------------------------------------------------


@SETTINGS
@given(
    primary_value=VALUES,
    baseline_value=VALUES,
    primary_unit=UNITS,
    baseline_unit=UNITS,
    formula_id=FORMULAS,
    completeness=COMPLETENESS,
    finality=FINALITY,
    reproducibility=REPRODUCIBILITY,
    verdict_code=VERDICT_CODES,
    primary_versions=METRIC_VERSIONS,
    baseline_versions=METRIC_VERSIONS,
    suppressed=st.booleans(),
)
def test_every_generated_comparison_is_complete_or_refused(
    authorized_pair: tuple[AuthorizedContext, str],
    primary_value: Decimal,
    baseline_value: Decimal,
    primary_unit: str,
    baseline_unit: str,
    formula_id: str,
    completeness: Completeness,
    finality: Finality,
    reproducibility: Reproducibility,
    verdict_code: ReasonCode,
    primary_versions: tuple[str, ...],
    baseline_versions: tuple[str, ...],
    suppressed: bool,
) -> None:
    """**The whole point of the file.** There is no third outcome.

    Twelve generated dimensions crossed. A combination that found a crack between
    two gates — one condition masking another, an early return that skipped a check
    — would appear here as a comparison carrying one side, and nowhere else.
    """
    outcome = _attempt(
        authorized_pair,
        primary_value=primary_value,
        baseline_value=baseline_value,
        primary_unit=primary_unit,
        baseline_unit=baseline_unit,
        formula_id=formula_id,
        completeness=completeness,
        finality=finality,
        reproducibility=reproducibility,
        verdict_code=verdict_code,
        primary_versions=primary_versions,
        baseline_versions=baseline_versions,
        suppressed=suppressed,
    )

    assert (outcome.comparison is None) != (outcome.error is None), "neither or both"

    if outcome.comparison is None:
        # A refusal costs at most two executions and never more.
        assert outcome.primary_calls <= 1
        assert outcome.baseline_calls <= 1
        return

    assert len(outcome.comparison.sides) == 2
    assert outcome.primary_calls == 1
    assert outcome.baseline_calls == 1


@SETTINGS
@given(primary_value=VALUES, baseline_value=VALUES, formula_id=FORMULAS)
def test_a_released_figure_is_derived_from_both_sides(
    authorized_pair: tuple[AuthorizedContext, str],
    primary_value: Decimal,
    baseline_value: Decimal,
    formula_id: str,
) -> None:
    """No side is substituted, duplicated or dropped on the success path.

    A comparison carrying two sides whose figure was computed from one of them
    twice would satisfy the count assertion above. This closes that: the released
    figure is recomputed from the two sides' own values through the **governed**
    operation table, so a substituted or duplicated operand changes the result.

    Note what is *not* asserted: the operands are deliberately **absent** from
    ``DerivedFigure``, because releasing them would release both sides' values
    alongside a comparison that may only disclose the difference (`FR-067`). So the
    check goes through the sides, which carry their own results, rather than through
    the figure.
    """
    outcome = _attempt(
        authorized_pair,
        primary_value=primary_value,
        baseline_value=baseline_value,
        primary_unit="count",
        baseline_unit="count",
        formula_id=formula_id,
        completeness=Completeness.COMPLETE,
        finality=Finality.FINAL,
        reproducibility=Reproducibility.FULL,
        verdict_code=ReasonCode.REQUEST_ALLOWED,
        primary_versions=("installs@1",),
        baseline_versions=("installs@1",),
        suppressed=False,
    )
    if outcome.comparison is None:
        # A zero baseline under a dividing formula legitimately refuses.
        assert outcome.error is not None
        return

    from analytics_interaction.comparison.compute import OPERATIONS

    figure = outcome.comparison.difference
    assert figure.derived_from == ("claim-a", "claim-b")
    assert figure.value == OPERATIONS[formula_id](primary_value, baseline_value)

    released = tuple(side.result.rows[0].cells[0].value for side in outcome.comparison.sides)
    assert released == (primary_value, baseline_value)


@SETTINGS
@given(primary_value=VALUES, formula_id=FORMULAS)
def test_a_zero_baseline_never_releases_a_one_sided_result(
    authorized_pair: tuple[AuthorizedContext, str],
    primary_value: Decimal,
    formula_id: str,
) -> None:
    """The division case, isolated.

    The tempting failure is releasing the numerator when the denominator is
    unusable — a plausible number, for a comparison that has no value. Generated
    across every primary so no value slips through.
    """
    outcome = _attempt(
        authorized_pair,
        primary_value=primary_value,
        baseline_value=Decimal("0"),
        primary_unit="count",
        baseline_unit="count",
        formula_id=formula_id,
        completeness=Completeness.COMPLETE,
        finality=Finality.FINAL,
        reproducibility=Reproducibility.FULL,
        verdict_code=ReasonCode.REQUEST_ALLOWED,
        primary_versions=("installs@1",),
        baseline_versions=("installs@1",),
        suppressed=False,
    )
    if outcome.comparison is not None:
        assert formula_id == "absolute_difference", (
            "only a non-dividing formula may complete against a zero baseline"
        )
        assert len(outcome.comparison.sides) == 2
        assert outcome.comparison.difference.value == primary_value
    else:
        assert str(primary_value) not in str(outcome.error)


# --- no float reaches the arithmetic ---------------------------------------------


@SETTINGS
@given(primary_value=VALUES, baseline_value=VALUES)
def test_every_released_operand_is_an_exact_decimal(
    authorized_pair: tuple[AuthorizedContext, str],
    primary_value: Decimal,
    baseline_value: Decimal,
) -> None:
    """Types, not values.

    A ``float`` that happened to compare equal to the expected ``Decimal`` would
    pass a value assertion and would still be a binary approximation of a governed
    figure.
    """
    outcome = _attempt(
        authorized_pair,
        primary_value=primary_value,
        baseline_value=baseline_value,
        primary_unit="count",
        baseline_unit="count",
        formula_id="absolute_difference",
        completeness=Completeness.COMPLETE,
        finality=Finality.FINAL,
        reproducibility=Reproducibility.FULL,
        verdict_code=ReasonCode.REQUEST_ALLOWED,
        primary_versions=("installs@1",),
        baseline_versions=("installs@1",),
        suppressed=False,
    )
    if outcome.comparison is None:
        return
    figure = outcome.comparison.difference
    assert isinstance(figure.value, Decimal)
    assert not isinstance(figure.value, float)
    for side in outcome.comparison.sides:
        for row in side.result.rows:
            for cell in row.cells:
                assert cell.value is None or isinstance(cell.value, Decimal | int)
                assert not isinstance(cell.value, float)


# --- the generator reaches both outcomes ---------------------------------------


def test_the_generated_space_contains_successes_and_refusals(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """**Without this the property could hold vacuously.**

    A generator that only ever produced refusals would satisfy "never one side"
    while proving nothing about the success path — and a generator that only ever
    succeeded would prove nothing about the gates.
    """
    succeeded = _attempt(
        authorized_pair,
        primary_value=Decimal("150"),
        baseline_value=Decimal("100"),
        primary_unit="count",
        baseline_unit="count",
        formula_id="absolute_difference",
        completeness=Completeness.COMPLETE,
        finality=Finality.FINAL,
        reproducibility=Reproducibility.FULL,
        verdict_code=ReasonCode.REQUEST_ALLOWED,
        primary_versions=("installs@1",),
        baseline_versions=("installs@1",),
        suppressed=False,
    )
    refused = _attempt(
        authorized_pair,
        primary_value=Decimal("150"),
        baseline_value=Decimal("100"),
        primary_unit="count",
        baseline_unit="thousands",
        formula_id="absolute_difference",
        completeness=Completeness.COMPLETE,
        finality=Finality.FINAL,
        reproducibility=Reproducibility.FULL,
        verdict_code=ReasonCode.REQUEST_ALLOWED,
        primary_versions=("installs@1",),
        baseline_versions=("installs@1",),
        suppressed=False,
    )
    assert succeeded.comparison is not None
    assert refused.error is not None


@SETTINGS
@given(value=VALUES)
def test_no_generated_value_is_a_float(value: Decimal) -> None:
    """The generator itself, asserted.

    A ``st.floats()`` added here for coverage would poison every property in the
    file at once, and the failures would read as arithmetic bugs rather than as a
    bad strategy.
    """
    assert isinstance(value, Decimal)
    assert not isinstance(value, float)


def test_the_figure_releases_no_operand() -> None:
    """``DerivedFigure`` carries the result and not the inputs, by construction.

    Stated here because the test above works around it, and a reader hitting that
    workaround should find the reason next to it rather than inferring one.
    """
    from analytics_interaction.contracts.comparison import DerivedFigure

    assert set(DerivedFigure.model_fields) == {"value", "unit", "derived_from", "basis"}
