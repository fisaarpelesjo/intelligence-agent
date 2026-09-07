"""Version equality across the verdict and both sides — T109 (FR-069; SC-039).

    Evidence: a differing catalog release, policy or vocabulary version refuses.
    — `tasks.md` T109

This is the **two-evaluation seam** ADR 0015 exists for. On the two-execution
route, two governance evaluations touch one user-visible answer: `001`'s verdict
on the comparison as presented, and `002`'s own evaluation of each side. They are
never allowed to disagree silently, and the way that is enforced is version
equality across all three.

The failure a missing check would cause is specific and invisible. A catalog
release published between the verdict and the second side's execution changes
what a metric *means*; both sides still return numbers, the difference still
computes, and the answer is about two different definitions of the same word. No
value in the response would look wrong.

Three versions, three ways to differ, and each is asserted separately:

| Version | Where it lives |
|---|---|
| catalog release | the verdict, and each side's provenance |
| policy version | the verdict, and each side's provenance |
| vocabulary version | `003`'s own — the intent's, against the `D-18` set in force |

The vocabulary version has no place on `002`'s provenance, and that is correct
rather than an omission: `002` does not read `D-18`. So it is checked where it
exists — the version the intent was interpreted under, against the formula set
actually in force when the difference is computed.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

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


def _coherent(
    *,
    verdict_release: str = "r-1",
    verdict_policy: str = "pol-1",
    primary_release: str = "r-1",
    primary_policy: str = "pol-1",
    baseline_release: str = "r-1",
    baseline_policy: str = "pol-1",
    intent_vocabulary: str = FIXTURE_VERSION,
    formula_vocabulary: str = FIXTURE_VERSION,
) -> str:
    return assert_sides_are_coherent(
        verdict(catalog_release_id=verdict_release, policy_version=verdict_policy),
        executed(Decimal("150"), catalog_release_id=primary_release, policy_version=primary_policy),
        executed(
            Decimal("100"), catalog_release_id=baseline_release, policy_version=baseline_policy
        ),
        requests=REQUESTS,
        vocabulary_version=intent_vocabulary,
        formula_version=formula_vocabulary,
    )


# --- agreement -----------------------------------------------------------------------


def test_identical_versions_across_all_three_agree() -> None:
    """The baseline the refusals below are measured against."""
    assert _coherent() == "count"


# --- catalog release -------------------------------------------------------------------


@pytest.mark.parametrize("side", ["primary_release", "baseline_release"])
def test_a_side_on_a_different_catalog_release_refuses(side: str) -> None:
    """Either side. A check that only looked at the first would pass half of this."""
    with pytest.raises(ContractViolation) as refusal:
        _coherent(**{side: "r-2"})
    assert refusal.value.code is Code.COMPARISON_SIDE_INVALID


def test_a_verdict_on_a_different_catalog_release_refuses() -> None:
    """The seam runs both ways: the verdict can be the one that moved."""
    with pytest.raises(ContractViolation):
        _coherent(verdict_release="r-0")


def test_two_sides_agreeing_with_each_other_but_not_the_verdict_refuses() -> None:
    """The case a side-to-side comparison would miss entirely.

    Both sides executed against ``r-2`` while the verdict was issued on ``r-1``:
    internally consistent, and governed by a decision about a different catalog.
    """
    with pytest.raises(ContractViolation):
        _coherent(primary_release="r-2", baseline_release="r-2")


# --- policy version ----------------------------------------------------------------------


@pytest.mark.parametrize("side", ["primary_policy", "baseline_policy"])
def test_a_side_under_a_different_policy_version_refuses(side: str) -> None:
    with pytest.raises(ContractViolation):
        _coherent(**{side: "pol-2"})


def test_a_verdict_under_a_different_policy_version_refuses() -> None:
    with pytest.raises(ContractViolation):
        _coherent(verdict_policy="pol-0")


def test_both_sides_under_a_policy_the_verdict_did_not_use_refuses() -> None:
    with pytest.raises(ContractViolation):
        _coherent(primary_policy="pol-2", baseline_policy="pol-2")


# --- vocabulary version --------------------------------------------------------------------


def test_an_intent_interpreted_under_another_vocabulary_refuses() -> None:
    """`D-18` moved between interpretation and arithmetic.

    The formula the question resolved to may have had a different unit rule, a
    different zero-baseline behaviour or a different quantisation under the older
    set — so computing under the newer one answers a question nobody asked.
    """
    with pytest.raises(ContractViolation) as refusal:
        _coherent(intent_vocabulary="voc-old")
    assert refusal.value.code is Code.COMPARISON_SIDE_INVALID


def test_the_formula_set_moving_under_the_intent_refuses() -> None:
    """Symmetric: it does not matter which side of the seam moved."""
    with pytest.raises(ContractViolation):
        _coherent(formula_vocabulary="voc-new")


# --- the condition is the enumerated one --------------------------------------------------------


def test_a_version_difference_is_the_governing_versions_condition() -> None:
    """Named, so a reader can map the refusal to `comparison-contract.md` §5.1."""
    assert MismatchCondition.GOVERNING_VERSIONS in set(MismatchCondition)
    assert "governing_versions" in mismatch(MismatchCondition.GOVERNING_VERSIONS).detail


def test_the_refusal_names_no_version() -> None:
    """A caller holding one side's access learns nothing about the other's release."""
    with pytest.raises(ContractViolation) as refusal:
        _coherent(baseline_release="r-secret-9")
    assert "r-secret-9" not in str(refusal.value)
    assert "r-1" not in str(refusal.value)
