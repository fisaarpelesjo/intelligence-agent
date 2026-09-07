"""Governed-content resolution — T043 (FR-025, FR-071; SC-018, SC-035, SC-040).

Four conditions, asserted **independently for vocabulary and for policy**:

| Condition at evaluation time | Result |
|---|---|
| Exactly one effective, all required fields present | Resolved |
| Zero effective | ``INTERPRETATION_*_UNRESOLVABLE`` |
| More than one effective | ``INTERPRETATION_*_UNRESOLVABLE`` |
| One effective, a required field missing | ``INTERPRETATION_*_UNRESOLVABLE`` |

Independently, because vocabulary and policy are separately owned, separately
approved and carry separate codes (`DEP-3`, `DEP-4`) — a shared test would let
one of the two regress while the other kept the suite green.

The **resolved** row is tested with fixture instances rather than authored
content. That distinction is load-bearing: the fixtures prove the *mechanism*
resolves when content exists; the real governed files hold no approved instance,
so the shipped system refuses. A fixture is never evidence for `D-18` or `D-19`.

**The closed formula set is empty, so every comparison refuses.** Asserted
against the real file, because that is the property that actually holds today.
"""

from __future__ import annotations

from datetime import date

import pytest

from analytics_interaction.contracts.reason_codes import InterpretationReasonCode
from analytics_interaction.governance.policy import (
    POLICY_CODE,
    load_policies,
    refusal_for,
    resolve_policy,
)
from analytics_interaction.governance.resolve import ContentUnresolvable
from analytics_interaction.governance.schemas import (
    ClaimClassWording,
    ComparisonFormula,
    ComparisonFormulas,
    ContentApproval,
    DisclosureRule,
    InterpretationPolicy,
    PeriodExpression,
    PeriodVocabulary,
    RedactionRule,
)
from analytics_interaction.governance.vocabulary import (
    VOCABULARY_CODE,
    load_claim_classes,
    load_comparison_formulas,
    load_period_vocabulary,
    resolve_claim_classes,
    resolve_comparison_formulas,
    resolve_period_vocabulary,
)

pytestmark = pytest.mark.unit

ON = date(2026, 8, 13)

APPROVAL = ContentApproval(
    approver_role="data-governance",
    evidence_ref="FIXTURE-ONLY",
    approved_on=date(2026, 1, 1),
)


def _vocabulary(version: str, *, to: date | None = None) -> PeriodVocabulary:
    """TEST-ONLY. Never evidence for `D-18`."""
    return PeriodVocabulary(
        version=version,
        effective_from=date(2026, 1, 1),
        effective_to=to,
        approval=APPROVAL,
        expressions=(
            PeriodExpression(
                id="fixture_range",
                surface_forms=("intervalo de teste",),
                boundary_rule="fixture_anchor",
                inclusivity="fixture_inclusive",
            ),
        ),
    )


def _formulas(version: str, *, entries: bool = True) -> ComparisonFormulas:
    """TEST-ONLY. Never evidence for `D-18`."""
    return ComparisonFormulas(
        version=version,
        effective_from=date(2026, 1, 1),
        approval=APPROVAL,
        formulas=(
            (
                ComparisonFormula(
                    id="fixture_difference",
                    surface_forms=("diferença de teste",),
                    unit_rule="fixture_same_unit",
                    zero_baseline="fixture_refuse",
                ),
            )
            if entries
            else ()
        ),
    )


def _policy(version: str, *, to: date | None = None) -> InterpretationPolicy:
    """TEST-ONLY. Never evidence for `D-19`."""
    return InterpretationPolicy(
        version=version,
        effective_from=date(2026, 1, 1),
        effective_to=to,
        approval=APPROVAL,
        ambiguity_threshold=2,
        clarification_round_bound=2,
        clarification_expiry_seconds=600,
        question_length_bound=500,
        redaction_rule=RedactionRule(
            rule_id="fixture_redaction", patterns=("fixture_pattern",), on_match="refuse"
        ),
        cross_question_disclosure=DisclosureRule(
            rule_id="fixture_disclosure", window_questions=5, on_reconstruction_risk="refuse"
        ),
    )


# --- the shipped state: everything refuses ------------------------------------


def test_no_governed_document_holds_an_approved_instance() -> None:
    """**Three of the four are still empty. The fourth was authored on 2026-08-26.**

    `D-18`'s `comparison-formulas.yaml` now holds ONE instance, declaring
    `percentage_change` — the owner's decision, *"Autorizar as duas (Recomendado)"*,
    recorded in the governed channel at 17:17:40Z. `D-19` and the rest are untouched.

    The property this node protects is not *"nothing is authored"* — that was the
    shipped state, not the rule. It is that **content appears only where a decision
    put it**. So the three undecided documents are still asserted empty, one by one,
    and the fourth is asserted to hold exactly what was decided: one instance, one
    formula, `percentage_change`.

    **The formula set stays CLOSED**, which is the part `FR-071` cares about: one
    member is not "anything goes". `resolve_formula` still refuses `ratio` and
    `absolute_difference`, measured.
    """
    # OD-104 (2026-09-02): o vocabulario e as classes foram autorados pelo dono — as
    # asserts viram "exatamente o que foi decidido", nunca menos nem mais.
    vocabulario = load_period_vocabulary()
    assert len(vocabulario) == 1, "one vocabulary instance was authored on 2026-09-02"
    ids = tuple(expression.id for expression in vocabulario[0].expressions)
    assert len(ids) == 11 and ids[0] == "today" and "last_week" in ids, ids

    classes = load_claim_classes()
    assert len(classes) == 1 and classes[0].is_complete(), "four classes worded (OD-104)"

    assert load_policies() == ()

    formulas = load_comparison_formulas()
    assert len(formulas) == 1, (
        "one formula instance was authored on 2026-08-26; a different count is a "
        "governed decision to be re-derived here rather than absorbed"
    )
    declared = tuple(formula.id for formula in formulas[0].formulas)
    assert declared == ("percentage_change",), declared


@pytest.mark.parametrize(
    ("resolver", "code"),
    [
        (resolve_period_vocabulary, VOCABULARY_CODE),
        (resolve_comparison_formulas, VOCABULARY_CODE),
        (resolve_claim_classes, VOCABULARY_CODE),
        (resolve_policy, POLICY_CODE),
    ],
)
def test_every_dependent_path_refuses_against_the_shipped_content(
    resolver: object, code: InterpretationReasonCode
) -> None:
    with pytest.raises(ContentUnresolvable) as caught:
        resolver(ON)  # type: ignore[operator]
    assert caught.value.code is code


def test_the_closed_formula_set_is_empty_so_every_comparison_refuses() -> None:
    """`FR-071`, `SC-040`. Absence of a formula is refusal, not permission.

    **This still passes after the 2026-08-26 authoring, and the reason is the DATE,
    not the emptiness — say so, or it reads as a lucky pass.** `ON` is 2026-08-13 and
    the authored instance is effective from 2026-08-26, so on `ON` there is still no
    instance in force and the refusal is the same refusal.

    That is worth keeping rather than moving the date: it asserts that authoring a
    formula does not retroactively make earlier comparisons resolvable, which is a
    property of the effectivity window and is now actually exercised instead of being
    vacuously true over an empty file.
    """
    with pytest.raises(ContentUnresolvable) as caught:
        resolve_comparison_formulas(ON)
    assert caught.value.code is InterpretationReasonCode.INTERPRETATION_VOCABULARY_UNRESOLVABLE


# --- the four conditions, for vocabulary --------------------------------------


def test_vocabulary_resolves_when_exactly_one_complete_instance_is_effective() -> None:
    resolved = resolve_period_vocabulary(ON, instances=(_vocabulary("v1"),))
    assert resolved.version == "v1"


def test_vocabulary_refuses_when_zero_are_effective() -> None:
    with pytest.raises(ContentUnresolvable, match="no approved") as caught:
        resolve_period_vocabulary(ON, instances=(_vocabulary("v1", to=date(2026, 2, 1)),))
    assert caught.value.code is VOCABULARY_CODE


def test_vocabulary_refuses_when_more_than_one_is_effective() -> None:
    """Picking one would be picking arbitrarily."""
    with pytest.raises(ContentUnresolvable, match="more than one") as caught:
        resolve_period_vocabulary(ON, instances=(_vocabulary("v1"), _vocabulary("v2")))
    assert caught.value.code is VOCABULARY_CODE


def test_vocabulary_refuses_when_the_effective_instance_declares_no_expression() -> None:
    """Incomplete is unresolvable, not partially usable."""
    empty = PeriodVocabulary(
        version="v1", effective_from=date(2026, 1, 1), approval=APPROVAL, expressions=()
    )
    with pytest.raises(ContentUnresolvable, match="incomplete") as caught:
        resolve_period_vocabulary(ON, instances=(empty,))
    assert caught.value.code is VOCABULARY_CODE


def test_the_formula_set_refuses_on_each_of_the_same_four_conditions() -> None:
    assert resolve_comparison_formulas(ON, instances=(_formulas("v1"),)).version == "v1"
    for instances in (
        (),
        (_formulas("v1"), _formulas("v2")),
        (_formulas("v1", entries=False),),
    ):
        with pytest.raises(ContentUnresolvable) as caught:
            resolve_comparison_formulas(ON, instances=instances)
        assert caught.value.code is VOCABULARY_CODE


# --- the four conditions, for policy ------------------------------------------


def test_policy_resolves_when_exactly_one_complete_instance_is_effective() -> None:
    assert resolve_policy(ON, policies=(_policy("p1"),)).version == "p1"


def test_policy_refuses_when_zero_are_effective() -> None:
    with pytest.raises(ContentUnresolvable, match="no approved") as caught:
        resolve_policy(ON, policies=(_policy("p1", to=date(2026, 2, 1)),))
    assert caught.value.code is POLICY_CODE


def test_policy_refuses_when_more_than_one_is_effective() -> None:
    with pytest.raises(ContentUnresolvable, match="more than one") as caught:
        resolve_policy(ON, policies=(_policy("p1"), _policy("p2")))
    assert caught.value.code is POLICY_CODE


@pytest.mark.parametrize(
    "field",
    [
        "ambiguity_threshold",
        "clarification_round_bound",
        "clarification_expiry_seconds",
        "question_length_bound",
        "redaction_rule",
        "cross_question_disclosure",
    ],
)
def test_a_policy_missing_any_of_the_six_is_not_constructible(field: str) -> None:
    """The single-failure-mode design, enforced at construction.

    There is no representable configuration in which the system runs with
    ambiguity controls but no untrusted-text screening, or the reverse.
    """
    fields = _policy("p1").model_dump()
    del fields[field]
    with pytest.raises(Exception, match=f"{field}|Field required"):
        InterpretationPolicy(**fields)


# --- no default, no carry-forward, no inference -------------------------------


def test_nothing_is_substituted_when_content_is_unresolvable() -> None:
    """Not a default, not an inferred value, not a previously seen one.

    Asserted as the absence of a return: the resolver raises, so there is no
    value for a caller to mistake for a governed one.
    """
    with pytest.raises(ContentUnresolvable):
        resolve_policy(ON, policies=())


def test_a_previously_resolved_instance_is_not_carried_forward() -> None:
    """Resolution is per-evaluation, with no memory between calls."""
    assert resolve_policy(ON, policies=(_policy("p1"),)).version == "p1"
    with pytest.raises(ContentUnresolvable):
        resolve_policy(ON, policies=())


def test_an_expired_instance_is_not_extended_to_cover_today() -> None:
    lapsed = _policy("p1", to=date(2026, 8, 12))
    assert resolve_policy(date(2026, 8, 12), policies=(lapsed,)).version == "p1"
    with pytest.raises(ContentUnresolvable, match="no approved"):
        resolve_policy(date(2026, 8, 13), policies=(lapsed,))


def test_a_governed_value_of_zero_would_be_present_rather_than_absent() -> None:
    """Absence means ``None`` or an empty collection — never a falsy value.

    Treating a governed zero as missing would substitute a refusal for an
    approved answer. Checked directly on the predicate, since no governed field
    currently permits zero.
    """
    from analytics_interaction.governance.resolve import is_absent

    assert not is_absent(0)
    assert not is_absent(False)
    assert is_absent(None)
    assert is_absent(())


# --- refusal wording discloses nothing ----------------------------------------


def test_the_refusal_names_no_threshold_bound_expiry_or_rule() -> None:
    """A principal refused by a policy must learn nothing about the policy."""
    with pytest.raises(ContentUnresolvable) as caught:
        resolve_policy(ON, policies=())
    violation = refusal_for(caught.value)
    assert violation.code is POLICY_CODE
    for leak in ("threshold", "bound", "expiry", "seconds", "500", "600"):
        assert leak not in violation.detail.lower()


def test_the_two_content_kinds_refuse_with_their_own_codes() -> None:
    """Merging them would let a vocabulary addition ship without privacy review."""
    with pytest.raises(ContentUnresolvable) as vocabulary:
        resolve_period_vocabulary(ON, instances=())
    with pytest.raises(ContentUnresolvable) as policy:
        resolve_policy(ON, policies=())
    assert vocabulary.value.code is not policy.value.code


# --- schema rules that keep a convention from being assumed -------------------


def test_a_week_relative_rule_without_a_week_start_is_not_constructible() -> None:
    """`PERIOD_CONVENTION_UNDECLARED` rather than resolving under an assumption.

    Whether "semana passada" starts Sunday or Monday changes every weekly number
    in the product, and nothing in this repository declares it.
    """
    with pytest.raises(Exception, match="week-relative"):
        PeriodExpression(
            id="last_week",
            surface_forms=("semana passada",),
            boundary_rule="previous_week",
            inclusivity="inclusive",
        )


def test_a_month_relative_rule_without_a_month_rule_is_not_constructible() -> None:
    with pytest.raises(Exception, match="month-relative"):
        PeriodExpression(
            id="last_month",
            surface_forms=("mês passado",),
            boundary_rule="previous_month",
            inclusivity="inclusive",
        )


def test_claim_class_wording_must_cover_every_contract_declared_class() -> None:
    """An answer carrying an unworded class would have a claim nobody could read."""
    from analytics_interaction.contracts.answer import ClaimClass
    from analytics_interaction.governance.schemas import ClaimClassContent

    partial = ClaimClassContent(
        version="c1",
        effective_from=date(2026, 1, 1),
        approval=APPROVAL,
        classes=(
            ClaimClassWording(
                claim_class=ClaimClass.FACTUAL_RESULT, label="Resultado", disclosure="Medido."
            ),
        ),
    )
    assert not partial.is_complete()
    with pytest.raises(ContentUnresolvable, match="does not cover every"):
        resolve_claim_classes(ON, instances=(partial,))

    full = ClaimClassContent(
        version="c1",
        effective_from=date(2026, 1, 1),
        approval=APPROVAL,
        classes=tuple(
            ClaimClassWording(claim_class=member, label=member.value, disclosure=member.value)
            for member in ClaimClass
        ),
    )
    assert resolve_claim_classes(ON, instances=(full,)).version == "c1"


def test_a_claim_class_may_not_be_worded_twice_in_one_instance() -> None:
    from analytics_interaction.contracts.answer import ClaimClass
    from analytics_interaction.governance.schemas import ClaimClassContent

    wording = ClaimClassWording(
        claim_class=ClaimClass.LIMITATION, label="Limitação", disclosure="Nota."
    )
    with pytest.raises(Exception, match="at most once"):
        ClaimClassContent(
            version="c1",
            effective_from=date(2026, 1, 1),
            approval=APPROVAL,
            classes=(wording, wording),
        )
