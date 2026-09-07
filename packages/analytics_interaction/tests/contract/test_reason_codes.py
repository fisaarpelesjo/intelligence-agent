"""Reason-code contract — T022 (FR-020; SC-015).

Four invariants, each of which fails in a different, real way.

**Three-way disjointness.** A consumer switches on a single ``code`` field. If a
string appeared in two namespaces, that switch would be ambiguous about which
layer produced the refusal — and the whole reason `003` declared its own
namespace instead of editing `001`'s closed enum was to keep the three
distinguishable.

**One outcome per code.** A code with no outcome is a state nothing may emit or
audit; a code with two would let a denial read as an allow depending on which
lookup ran.

**Every outcome class inhabited.** `001`'s rule, inherited: a declared outcome no
code can express is dead vocabulary that will eventually be given a meaning
nobody chose.

**The counts the contract states.** 32 / 30 / 1 / 1 is not decoration —
`contracts/reason-codes.md` §3 says the enumerated tables are authoritative, so
the numbers are a checkable claim about them.
"""

from __future__ import annotations

import pytest
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode

from analytics_interaction.contracts.reason_codes import (
    REASON_CODE_OUTCOME,
    InterpretationReasonCode,
    codes_with_outcome,
    outcome_for,
)

pytestmark = pytest.mark.contract

CATALOG = frozenset(code.value for code in ReasonCode)
ANALYTICS = frozenset(code.value for code in AnalyticsReasonCode)
INTERPRETATION = frozenset(code.value for code in InterpretationReasonCode)


# --- the namespace ------------------------------------------------------------


def test_the_namespace_declares_the_thirty_two_codes_the_contract_enumerates() -> None:
    assert len(InterpretationReasonCode) == 32


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [(Outcome.DENY, 30), (Outcome.ALLOW_WITH_CAVEAT, 1), (Outcome.ALLOW, 1)],
)
def test_each_outcome_class_holds_the_declared_number_of_codes(
    outcome: Outcome, expected: int
) -> None:
    assert len(codes_with_outcome(outcome)) == expected


def test_the_single_allow_and_single_caveat_codes_are_the_named_ones() -> None:
    """Which code is permissive matters as much as how many are.

    A count alone would pass if the ``ALLOW`` were, say,
    ``INSTRUCTION_INJECTION_REFUSED``.
    """
    assert codes_with_outcome(Outcome.ALLOW) == (InterpretationReasonCode.QUESTION_ANSWERED,)
    assert codes_with_outcome(Outcome.ALLOW_WITH_CAVEAT) == (
        InterpretationReasonCode.QUESTION_ANSWERED_WITH_CAVEAT,
    )


def test_clarification_required_is_classified_deny_despite_not_being_a_failure() -> None:
    """No answer was produced and no request was constructed.

    Classifying it permissively would let a caller read "clarification" as
    "partial success" — and a partial success is exactly the thing a governed
    refusal must never be mistaken for.
    """
    assert outcome_for(InterpretationReasonCode.CLARIFICATION_REQUIRED) is Outcome.DENY


# --- three-way disjointness ---------------------------------------------------


@pytest.mark.parametrize(
    ("left", "right", "pair"),
    [
        (INTERPRETATION, CATALOG, "003 / 001"),
        (INTERPRETATION, ANALYTICS, "003 / 002"),
        (CATALOG, ANALYTICS, "001 / 002"),
    ],
)
def test_the_three_namespaces_share_no_member(
    left: frozenset[str], right: frozenset[str], pair: str
) -> None:
    assert not left & right, f"{pair} share codes: {sorted(left & right)}"


def test_the_upstream_namespaces_are_the_sizes_this_contract_assumes() -> None:
    """The disjointness claim is only meaningful against the real upstream sets.

    If `001` or `002` grew a code, the intersection tests above would still pass
    while the contract's stated arithmetic silently went stale.
    """
    assert len(CATALOG) == 41
    assert len(ANALYTICS) == 25


def test_the_guard_would_catch_a_collision() -> None:
    """A disjointness test that has never been shown to fail proves nothing."""
    planted = INTERPRETATION | {next(iter(CATALOG))}
    assert planted & CATALOG


# --- the outcome map ----------------------------------------------------------


def test_every_code_has_exactly_one_outcome() -> None:
    assert set(REASON_CODE_OUTCOME) == set(InterpretationReasonCode)
    assert len(REASON_CODE_OUTCOME) == len(InterpretationReasonCode)


def test_every_outcome_class_is_inhabited() -> None:
    for outcome in Outcome:
        assert codes_with_outcome(outcome), f"no code expresses {outcome.value}"


def test_the_outcome_map_is_read_only() -> None:
    """A mutable map is a map something can edit between two lookups."""
    with pytest.raises(TypeError):
        REASON_CODE_OUTCOME[InterpretationReasonCode.QUESTION_ANSWERED] = Outcome.DENY  # type: ignore[index]


def test_an_unmapped_code_raises_rather_than_defaulting() -> None:
    """Guessing an outcome would let a denial read as an allow."""
    with pytest.raises(ValueError, match="no declared outcome class"):
        outcome_for("NOT_A_CODE")  # type: ignore[arg-type]


# --- ownership ----------------------------------------------------------------


def test_no_code_restates_an_upstream_concern() -> None:
    """The ownership rule, checked by concept rather than by string.

    An interpretation code may only describe a condition neither upstream layer
    can observe. These stems name conditions `001` and `002` already own —
    freshness, suppression, cost, shape — and a `003` code carrying one would be
    this layer paraphrasing a refusal it did not originate (`FR-021`).
    """
    upstream_concerns = (
        "FRESHNESS",
        "SUPPRESS",
        "COST",
        "SHAPE",
        "TIMEOUT",
        "WAREHOUSE",
        "DRY_RUN",
        "ROW_LIMIT",
        "COVERAGE",
        "RETENTION",
        "DEPRECAT",
        "GRAIN",
        "ADDITIV",
    )
    offenders = [
        code.value
        for code in InterpretationReasonCode
        if any(concern in code.value for concern in upstream_concerns)
    ]
    assert not offenders, f"these restate an upstream concern: {offenders}"


def test_the_two_structural_and_governed_limit_codes_are_distinct() -> None:
    """Step 1 may not disclose a governed limit; step 4 may.

    One code for both would force a single wording, and that wording would
    either name a governed number before the principal is proven entitled to
    hear it, or withhold it after they are.
    """
    assert (
        InterpretationReasonCode.QUESTION_EXCEEDS_STRUCTURAL_LIMIT
        is not InterpretationReasonCode.QUESTION_EXCEEDS_GOVERNED_LIMIT
    )


def test_the_authorization_context_has_exactly_one_code() -> None:
    """Not four. Distinguishing which part failed describes the identity system."""
    authorization = [c for c in InterpretationReasonCode if c.value.startswith("AUTHORIZATION_")]
    assert authorization == [InterpretationReasonCode.AUTHORIZATION_CONTEXT_UNRESOLVABLE]


def test_vocabulary_and_policy_have_separate_codes() -> None:
    """Separately owned and separately approved (`DEP-3`, `DEP-4`).

    Merging them would let a vocabulary addition ship without privacy review.
    """
    assert (
        InterpretationReasonCode.INTERPRETATION_VOCABULARY_UNRESOLVABLE
        is not InterpretationReasonCode.INTERPRETATION_POLICY_UNRESOLVABLE
    )
