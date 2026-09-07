"""Comparison basis and window — T135 (FR-035; SC-019, SC-020, SC-036, SC-038).

    Evidence: a recomputed window fails; a comparison assembled from two
    single-side evaluations fails. — `tasks.md` T135

A comparison answer carries **three** claims: both factual results and the
difference derived from them. That is what makes a difference checkable rather
than trustworthy — the operands are there, the formula is named, and the window
says which days both sides were read over.

## What the basis states, and where each part comes from

| Part | Source |
|---|---|
| ``formula`` | `D-18`, through the governed comparison |
| ``window_start`` / ``window_end`` | `001`'s verdict, via `002`'s reader |
| ``chosen_because`` | `001`'s governed wording, verbatim |

None of it is derived here. A window this feature assembled would be the
recomputation `FR-066` forbids, and a ``chosen_because`` it composed would tell
the reader a basis nobody governed — while looking authoritative.

## The two failures this file is written against

* **a recomputed window.** Asserted by making the verdict's window *narrower*
  than either requested range: a derivation from the requests would produce the
  requested one and look entirely plausible;
* **a comparison from two single-side evaluations.** `GovernedComparison` carries
  one verdict covering the comparison as presented. Two independent verdicts
  never combine into one, and the type gives no way to try.

Every governed formula and claim wording here is fixture-only. `D-18` ships
empty, so a production comparison answer still refuses.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from analytics_interaction.answer.assemble import assemble_answer
from analytics_interaction.answer.caveats import carry_caveats
from analytics_interaction.answer.derived import basis_for, comparison_claims
from analytics_interaction.authorization.context_preflight import AuthorizedContext
from analytics_interaction.comparison.refusal import SideSubmission, govern_comparison
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.answer import AnswerClaim, ClaimClass, ComparisonBasis
from analytics_interaction.contracts.comparison import GovernedComparison
from analytics_interaction.contracts.intent import ResolvedIntent
from analytics_interaction.governance.resolve import ContentUnresolvable

from ..conftest import ON
from ..fixtures.answers import claim_wording, ref
from ..fixtures.comparisons import (
    ABSOLUTE_DIFFERENCE,
    BASELINE_RANGE,
    FIXTURE_VERSION,
    PRIMARY_RANGE,
    RATIO,
    WINDOW_REASON,
    caveat_set,
    executed,
    formula_instances,
    verdict,
)
from ..fixtures.comparisons import (
    request as governed_request,
)

pytestmark = pytest.mark.integration

FORMULAS = formula_instances(ABSOLUTE_DIFFERENCE, RATIO)
WORDING = claim_wording()
NARROWED = (date(2026, 7, 10), date(2026, 7, 20))


def _comparison(
    pair: tuple[AuthorizedContext, str],
    *,
    window: tuple[date, date] | None = PRIMARY_RANGE,
    primary: Decimal = Decimal("150"),
    baseline: Decimal = Decimal("100"),
) -> GovernedComparison:
    authorized, fingerprint = pair
    return govern_comparison(
        verdict(window=window),
        formula_id="absolute_difference",
        primary_side=SideSubmission(
            request=governed_request(period=PRIMARY_RANGE),
            submit=lambda: executed(primary),
        ),
        baseline_side=SideSubmission(
            request=governed_request(period=BASELINE_RANGE),
            submit=lambda: executed(baseline),
        ),
        caveats=caveat_set(),
        authorized=authorized,
        auth_fingerprint=fingerprint,
        on=ON,
        vocabulary_version=FIXTURE_VERSION,
        derived_from=("claim-a", "claim-b"),
        instances=FORMULAS,
    )


def _claims(comparison: GovernedComparison) -> tuple[AnswerClaim, AnswerClaim, AnswerClaim]:
    return comparison_claims(
        comparison,
        subjects=("installs.july", "installs.june"),
        difference_subject="installs.difference",
        factual_message=ref("claim.factual"),
        difference_message=ref("claim.difference"),
    )


# --- three claims, and the difference names both operands ----------------------------


def test_a_comparison_produces_both_factual_results_and_the_difference(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """`FR-035`: a reader can trace a difference to the numbers behind it."""
    primary, baseline, difference = _claims(_comparison(authorized_pair))

    assert primary.claim_class is ClaimClass.FACTUAL_RESULT
    assert baseline.claim_class is ClaimClass.FACTUAL_RESULT
    assert difference.claim_class is ClaimClass.CALCULATED_COMPARISON
    assert primary.value == Decimal("150")
    assert baseline.value == Decimal("100")
    assert difference.value == Decimal("50")


def test_the_difference_names_the_two_factual_claims(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """``derived_from`` names subjects, so a reorder cannot break traceability."""
    primary, baseline, difference = _claims(_comparison(authorized_pair))

    assert difference.derived_from == (primary.subject, baseline.subject)
    assert difference.derived_from == ("installs.july", "installs.june")


def test_a_derived_claim_without_its_operands_is_not_constructible() -> None:
    """The contract requires both ``derived_from`` and ``basis`` for this class.

    Asserted against the contract directly rather than through the constructor,
    because ``calculated`` takes both as required arguments — which is the point:
    the untraceable shape is unreachable from the sanctioned path and refused on
    the unsanctioned one.
    """
    from analytics_interaction.contracts._base import build
    from analytics_interaction.contracts.answer import AnswerClaim

    with pytest.raises(ContractViolation):
        build(
            AnswerClaim,
            claim_class=ClaimClass.CALCULATED_COMPARISON,
            subject="installs.difference",
            value=Decimal("50"),
            unit="count",
            message=ref("claim.difference"),
        )


def test_a_non_comparison_claim_carrying_a_basis_is_not_constructible() -> None:
    """The rule runs both ways: only a comparison derives from anything."""
    from analytics_interaction.contracts._base import build
    from analytics_interaction.contracts.answer import AnswerClaim

    with pytest.raises(ContractViolation):
        build(
            AnswerClaim,
            claim_class=ClaimClass.FACTUAL_RESULT,
            subject="installs",
            value=Decimal("150"),
            unit="count",
            message=ref("claim.factual"),
            derived_from=("a", "b"),
            basis=ComparisonBasis(
                formula="absolute_difference",
                window_start=PRIMARY_RANGE[0],
                window_end=PRIMARY_RANGE[1],
                chosen_because=WINDOW_REASON,
            ),
        )


def test_a_factual_claim_carries_no_basis(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """A factual result derives from the warehouse, not from other claims.

    Letting one claim to derive would make `FR-033`'s prohibition on
    recomputation unobservable.
    """
    primary, baseline, _ = _claims(_comparison(authorized_pair))

    for claim in (primary, baseline):
        assert claim.derived_from is None
        assert claim.basis is None


# --- the basis is stated, and taken from the verdict -----------------------------------


def test_the_basis_states_formula_window_and_chosen_because(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    comparison = _comparison(authorized_pair)
    basis = basis_for(comparison)

    assert basis.formula == "absolute_difference"
    assert (basis.window_start, basis.window_end) == PRIMARY_RANGE
    assert basis.chosen_because == WINDOW_REASON


def test_the_window_is_never_recomputed_from_the_requests(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """**The failure this file is written against.**

    The verdict states a window narrower than either requested range. A
    derivation from the requests would return July, look plausible, and be a
    basis nobody governed.
    """
    comparison = _comparison(authorized_pair, window=NARROWED)
    basis = basis_for(comparison)

    assert (basis.window_start, basis.window_end) == NARROWED
    assert (basis.window_start, basis.window_end) != PRIMARY_RANGE
    assert (basis.window_start, basis.window_end) != BASELINE_RANGE


def test_the_chosen_because_is_the_catalogs_own_wording(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """Carried byte-for-byte. Composing one would look authoritative and be invented."""
    comparison = _comparison(authorized_pair)
    assert basis_for(comparison).chosen_because == comparison.window.reason
    assert len(basis_for(comparison).chosen_because) == len(WINDOW_REASON)


def test_the_derived_figure_carries_the_window_reason_as_its_basis(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """The figure states what it was computed over."""
    comparison = _comparison(authorized_pair)
    assert comparison.difference.basis == WINDOW_REASON


def test_the_difference_unit_comes_from_the_formula_not_an_operand(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """A ratio's unit is neither operand's, which is why `D-18` declares it."""
    primary, _, difference = _claims(_comparison(authorized_pair))

    assert primary.unit == "count"
    assert difference.unit == ABSOLUTE_DIFFERENCE.unit_rule
    assert difference.unit != primary.unit


# --- one verdict, covering the comparison as presented ----------------------------------


def test_the_comparison_carries_one_verdict(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """`SC-036`. Two independent single-side evaluations never combine into one.

    The type gives no way to try: ``GovernedComparison.verdict`` is a single
    decision, and there is no field a second could occupy.
    """
    comparison = _comparison(authorized_pair)

    assert "verdict" in GovernedComparison.model_fields
    assert "verdicts" not in GovernedComparison.model_fields
    assert comparison.verdict.comparable_window is not None


def test_a_comparison_has_exactly_two_sides_or_does_not_exist(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """No partial state. "Return the side that worked" is unexpressible."""
    comparison = _comparison(authorized_pair)
    assert len(comparison.sides) == 2

    annotation = str(GovernedComparison.model_fields["sides"].annotation)
    assert "SideResult, SideResult" in annotation or "tuple" in annotation


def test_a_verdict_stating_no_window_refuses_the_whole_comparison(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """`SC-038`. The requested range is what the window exists to correct."""
    with pytest.raises(ContractViolation) as refusal:
        _comparison(authorized_pair, window=None)
    assert "not a substitute" in refusal.value.detail


# --- the comparison answer, and what refuses it -------------------------------------------


def test_a_comparison_answer_assembles_from_fixture_wording(
    authorized_pair: tuple[AuthorizedContext, str], resolved_intent: ResolvedIntent
) -> None:
    """The whole path, with fixture-only `D-18` formula **and** claim wording."""
    comparison = _comparison(authorized_pair)
    answer = assemble_answer(
        resolved_intent,
        claims=_claims(comparison),
        caveats=carry_caveats(),
        provenance=tuple(side.provenance for side in comparison.sides),
        on=ON,
        wording=WORDING,
    )

    assert len(answer.claims) == 3
    assert len(answer.provenance) == 2
    assert answer.claims[2].claim_class is ClaimClass.CALCULATED_COMPARISON
    assert answer.claims[2].basis is not None


def test_missing_claim_wording_refuses_the_comparison_answer(
    authorized_pair: tuple[AuthorizedContext, str], resolved_intent: ResolvedIntent
) -> None:
    """**`D-18`'s shipped state.**

    The structured comparison remains internally valid — it was computed and it
    is complete — and the user-facing answer refuses, because the wording that
    would present it is not governed.
    """
    comparison = _comparison(authorized_pair)
    assert comparison.difference.value == Decimal("50")

    with pytest.raises(ContentUnresolvable):
        assemble_answer(
            resolved_intent,
            claims=_claims(comparison),
            caveats=carry_caveats(),
            provenance=tuple(side.provenance for side in comparison.sides),
            on=ON,
            wording=(),
        )


def test_both_sides_provenance_reaches_the_answer_unmerged(
    authorized_pair: tuple[AuthorizedContext, str], resolved_intent: ResolvedIntent
) -> None:
    """`FR-072`: one entry per side, in side order."""
    comparison = _comparison(authorized_pair)
    answer = assemble_answer(
        resolved_intent,
        claims=_claims(comparison),
        caveats=carry_caveats(),
        provenance=tuple(side.provenance for side in comparison.sides),
        on=ON,
        wording=WORDING,
    )

    assert answer.provenance[0] == comparison.sides[0].provenance
    assert answer.provenance[1] == comparison.sides[1].provenance


def test_the_comparison_answer_is_deterministic(
    authorized_pair: tuple[AuthorizedContext, str], resolved_intent: ResolvedIntent
) -> None:
    """`SC-028`, including the derived figure's last digit."""

    def build() -> object:
        comparison = _comparison(authorized_pair)
        return assemble_answer(
            resolved_intent,
            claims=_claims(comparison),
            caveats=carry_caveats(),
            provenance=tuple(side.provenance for side in comparison.sides),
            on=ON,
            wording=WORDING,
        ).model_dump_json()

    assert build() == build()
