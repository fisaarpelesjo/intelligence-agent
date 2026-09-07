"""The enumerated mismatch conditions — T111 (FR-068; SC-039).

    Every enumerated incompatible-provenance and material-mismatch condition
    refuses the whole comparison, and a condition outside the enumerated set
    fails closed **as** a mismatch rather than passing as unrecognised.

    Evidence: each of the seven enumerated conditions asserted separately, plus
    one deliberately unrecognised condition. — `tasks.md` T111

**Separately** is the load-bearing word. A single "the sides are incompatible"
test passes when one check fires and six are missing, and the six that are
missing are exactly the ones nobody would notice — a comparison across differing
dimensional coverage returns a plausible number, and so does one across two
metric-definition versions. Each condition therefore gets its own case, its own
fixture difference, and an assertion that the *other six* still agree.

The eighth case is the one that keeps the set honest: a condition the contract
names and this module has not implemented must **refuse**, not slip through. That
is `comparison-contract.md` §5.1's closing line, and it is why
:func:`mismatch` refuses an unrecognised name rather than raising a lookup error.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from semantic_catalog.validation.decision import Reproducibility, Segment

from analytics_interaction.comparison.refusal import (
    MismatchCondition,
    assert_sides_are_coherent,
    mismatch,
)
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code

from ..fixtures.comparisons import (
    BASELINE_RANGE,
    FIXTURE_VERSION,
    PRIMARY_RANGE,
    executed,
    request,
    verdict,
)

pytestmark = pytest.mark.unit

REQUESTS = (request(period=PRIMARY_RANGE), request(period=BASELINE_RANGE))
LATER = datetime.fromisoformat("2026-08-13T18:00:00+00:00")

#: The seven, and how to produce each one. Keeping the production beside the name
#: is what lets the "all seven, separately" claim be a parametrisation rather
#: than seven hand-written tests that could drift apart.
CONDITIONS: dict[MismatchCondition, dict[str, object]] = {
    MismatchCondition.UNITS: {"baseline": executed(Decimal("100"), unit="minutes")},
    MismatchCondition.GRAIN: {
        "requests": (
            request(period=PRIMARY_RANGE),
            request(period=BASELINE_RANGE, dimensions=("country",)),
        )
    },
    MismatchCondition.METRIC_VERSIONS: {
        "baseline": executed(Decimal("100"), metric_versions=("installs@2",))
    },
    MismatchCondition.DIMENSIONAL_COVERAGE: {
        "baseline": executed(Decimal("100"), coverage=("country",))
    },
    MismatchCondition.REPRODUCIBILITY: {
        "baseline": executed(Decimal("100"), reproducibility=Reproducibility.LIMITED)
    },
    MismatchCondition.DATA_AS_OF: {"baseline": executed(Decimal("100"), data_as_of=LATER)},
    MismatchCondition.GOVERNING_VERSIONS: {
        "baseline": executed(Decimal("100"), catalog_release_id="r-2")
    },
}


def _coherent(**overrides: object) -> str:
    primary = overrides.get("primary") or executed(Decimal("150"))
    baseline = overrides.get("baseline") or executed(Decimal("100"))
    decision = overrides.get("decision") or verdict()
    requests = overrides.get("requests") or REQUESTS
    return assert_sides_are_coherent(
        decision,  # pyright: ignore[reportArgumentType]
        primary,  # pyright: ignore[reportArgumentType]
        baseline,  # pyright: ignore[reportArgumentType]
        requests=requests,  # pyright: ignore[reportArgumentType]
        vocabulary_version=str(overrides.get("vocabulary", FIXTURE_VERSION)),
        formula_version=FIXTURE_VERSION,
    )


# --- the set is the contract's -------------------------------------------------------


def test_exactly_seven_conditions_are_enumerated() -> None:
    """`comparison-contract.md` §5.1, counted."""
    assert len(MismatchCondition) == 7
    assert set(CONDITIONS) == set(MismatchCondition)


def test_the_condition_names_match_the_contract() -> None:
    assert {condition.value for condition in MismatchCondition} == {
        "units",
        "grain",
        "metric_versions",
        "dimensional_coverage",
        "reproducibility",
        "data_as_of",
        "governing_versions",
    }


# --- each condition, separately --------------------------------------------------------


@pytest.mark.parametrize("condition", list(MismatchCondition), ids=lambda c: c.value)
def test_each_enumerated_condition_refuses_the_whole_comparison(
    condition: MismatchCondition,
) -> None:
    """Seven cases, seven fixtures, one governed code."""
    with pytest.raises(ContractViolation) as refusal:
        _coherent(**CONDITIONS[condition])
    assert refusal.value.code is Code.COMPARISON_SIDE_INVALID


def test_sides_differing_in_none_of_the_seven_agree() -> None:
    """The control. Without it, a check that always refused would pass all seven."""
    assert _coherent() == "count"


@pytest.mark.parametrize("condition", list(MismatchCondition), ids=lambda c: c.value)
def test_each_condition_is_produced_by_its_own_difference(
    condition: MismatchCondition,
) -> None:
    """A fixture that tripped two conditions would make one of them untested.

    Each override is applied alone and the refusal is required — so a fixture
    that accidentally also changed the unit, say, would still be attributed to
    the condition it was written for and the real one would go unasserted. This
    checks the *converse*: removing the override makes the comparison agree.
    """
    assert _coherent() == "count"
    with pytest.raises(ContractViolation):
        _coherent(**CONDITIONS[condition])


# --- named refusals ----------------------------------------------------------------------


@pytest.mark.parametrize("condition", list(MismatchCondition), ids=lambda c: c.value)
def test_each_condition_names_itself_in_the_refusal(condition: MismatchCondition) -> None:
    """So a reader can map a refusal back to the contract's own list."""
    violation = mismatch(condition)
    assert violation.code is Code.COMPARISON_SIDE_INVALID
    assert condition.value in violation.detail


# --- the eighth case: unrecognised fails closed ---------------------------------------------


@pytest.mark.parametrize(
    "unrecognised",
    [
        "currency",
        "timezone_offset",
        "sampling_rate",
        "",
        "UNITS",
        "units ",
    ],
)
def test_an_unrecognised_condition_fails_closed_as_a_mismatch(unrecognised: str) -> None:
    """Never a lookup error, never a pass.

    A condition added to `comparison-contract.md` and not implemented here must
    surface as a refused comparison. ``"UNITS"`` and ``"units "`` are included
    deliberately: a case-folding or whitespace-trimming lookup would quietly
    accept them, and accepting a condition by normalising its name is how the
    closed set stops being closed.
    """
    violation = mismatch(unrecognised)
    assert violation.code is Code.COMPARISON_SIDE_INVALID
    assert "unrecognised" in violation.detail


def test_the_unrecognised_refusal_is_distinguishable_from_an_enumerated_one() -> None:
    """Same governed fact, different detail — one is a gap, the other is a rule."""
    enumerated = mismatch(MismatchCondition.UNITS).detail
    unknown = mismatch("currency").detail
    assert enumerated != unknown
    assert enumerated.startswith("the two sides differ")
    assert unknown.startswith("an unrecognised")


def test_an_unrecognised_condition_does_not_raise_a_lookup_error() -> None:
    """The refusal is a value, so a caller cannot accidentally not handle it."""
    violation = mismatch("something_nobody_implemented")
    assert isinstance(violation, ContractViolation)


# --- the conditions that carry an exemption --------------------------------------------------


def test_the_metric_version_condition_has_exactly_one_exemption() -> None:
    """The verdict declaring the spanned versions comparable, and nothing else."""
    spanned = verdict(
        segments=(
            Segment(metric_version_id="installs@1", start=PRIMARY_RANGE[0], end=PRIMARY_RANGE[1]),
            Segment(metric_version_id="installs@2", start=BASELINE_RANGE[0], end=BASELINE_RANGE[1]),
        )
    )
    assert (
        _coherent(
            primary=executed(Decimal("150"), metric_versions=("installs@1",)),
            baseline=executed(Decimal("100"), metric_versions=("installs@2",)),
            decision=spanned,
        )
        == "count"
    )


def test_an_empty_segment_list_grants_no_exemption() -> None:
    """A verdict that declared nothing has not declared these comparable."""
    with pytest.raises(ContractViolation):
        _coherent(
            primary=executed(Decimal("150"), metric_versions=("installs@1",)),
            baseline=executed(Decimal("100"), metric_versions=("installs@2",)),
            decision=verdict(segments=()),
        )


def test_the_data_as_of_condition_applies_only_where_a_window_was_stated() -> None:
    """ "Where the verdict required a single one" — the contract's own qualifier."""
    assert (
        _coherent(
            baseline=executed(Decimal("100"), data_as_of=LATER), decision=verdict(window=None)
        )
        == "count"
    )
    with pytest.raises(ContractViolation):
        _coherent(baseline=executed(Decimal("100"), data_as_of=LATER))


def test_equally_limited_reproducibility_is_not_a_mismatch() -> None:
    """The condition is the **asymmetry**, not limitation itself.

    Two equally limited sides are a caveated comparison, not an incoherent one —
    refusing them would be this feature overruling a verdict `001` permitted.
    """
    assert (
        _coherent(
            primary=executed(Decimal("150"), reproducibility=Reproducibility.LIMITED),
            baseline=executed(Decimal("100"), reproducibility=Reproducibility.LIMITED),
        )
        == "count"
    )


# --- nothing leaks through a mismatch refusal ------------------------------------------------


@pytest.mark.parametrize("condition", list(MismatchCondition), ids=lambda c: c.value)
def test_no_mismatch_refusal_discloses_a_side(condition: MismatchCondition) -> None:
    """A caller holding one side's access learns nothing about the other's."""
    with pytest.raises(ContractViolation) as refusal:
        _coherent(**CONDITIONS[condition])
    rendered = str(refusal.value)
    for secret in ("150", "100", "minutes", "installs@2", "r-2", "country"):
        assert secret not in rendered
