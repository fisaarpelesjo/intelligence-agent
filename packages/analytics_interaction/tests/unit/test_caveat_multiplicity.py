"""Caveat multiplicity — T126, T127 correction (FR-084, FR-085; SC-047, SC-048).

**Every occurrence survives. Nothing is deduplicated, ever.**

An earlier form of `answer/caveats.py` collapsed repeats within a single origin,
on the reasoning that `001` stating one limitation twice about one side is one
limitation. That reasoning was wrong.

A repeat may be two distinct upstream decisions, two evaluations, two pieces of
evidence, or two segments of one range that produced the same governed code.
Deciding they are "really" one is an **interpretation of governed output**, which
is exactly what this layer must not perform — and the collapse is invisible
downstream, because a reader sees one qualification and has no way to learn a
second was issued.

This file is the regression guard. Eight claims, and each fails differently:

1. two byte-identical caveats from one origin stay two;
2. identical caveats from different origins stay separate;
3. three occurrences make ``total == 3``;
4. ordering is deterministic **without** removing anything;
5. required multiplicity is enforced as a multiset;
6. carrying one of two required occurrences withholds the answer;
7. wording, code, origin and attribution survive byte-for-byte;
8. no set, dict or frozenset on the path silently drops an occurrence.

The last is the structural one. A container that cannot hold duplicates is how
deduplication returns without anybody deciding to add it, so the path is scanned
rather than only exercised.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from semantic_catalog.contracts.reason_codes import ReasonCode

from analytics_interaction.answer import caveats as caveats_module
from analytics_interaction.answer.caveats import PROVENANCE_ORDER, carry_caveats
from analytics_interaction.answer.withhold import assert_caveats_are_releasable
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.answer import AttributedCaveat, CaveatOrigin
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code

pytestmark = pytest.mark.unit

LAGGING = ReasonCode.SOURCE_LAGGING_WITHIN_TOLERANCE
PARTIAL = ReasonCode.EQUIVALENT_PARTIAL_COMPARISON
TEXT = "fonte atrasada dentro da tolerância governada"
OTHER = "cobertura parcial equivalente"


def _caveat(
    code: ReasonCode | AnalyticsReasonCode = LAGGING,
    *,
    origin: CaveatOrigin = CaveatOrigin.SIDE_A,
    message: str = TEXT,
) -> AttributedCaveat:
    return AttributedCaveat(code=code, message_pt_br=message, origin=origin)


# --- 1. two identical caveats from one origin stay two --------------------------


def test_two_byte_identical_caveats_from_one_origin_survive_as_two() -> None:
    """**The corrected behaviour.**

    Both occurrences are carried. Collapsing them would tell the reader side A
    was qualified once when it was qualified twice.
    """
    carried = carry_caveats((_caveat(), _caveat()))

    assert len(carried.caveats) == 2
    assert carried.total == 2
    assert carried.caveats[0] == carried.caveats[1]


def test_two_occurrences_differing_only_in_wording_both_survive() -> None:
    """Not a contradiction the contract defines, so not a reason to discard one.

    Refusing here would discard a valid repeated occurrence to enforce a rule
    nobody wrote.
    """
    carried = carry_caveats((_caveat(message=TEXT), _caveat(message=OTHER)))

    assert carried.total == 2
    assert [c.message_pt_br for c in carried.caveats] == [TEXT, OTHER]


def test_repeats_within_the_verdict_origin_also_survive() -> None:
    """The rule has no exception for any origin."""
    carried = carry_caveats((_caveat(origin=CaveatOrigin.VERDICT),) * 2)
    assert carried.total == 2


# --- 2. identical caveats from different origins stay separate ------------------


def test_identical_caveats_from_two_sides_stay_distinct() -> None:
    """Two sides carrying one caveat is information, not redundancy."""
    carried = carry_caveats(
        (_caveat(origin=CaveatOrigin.SIDE_A),), (_caveat(origin=CaveatOrigin.SIDE_B),)
    )

    assert carried.total == 2
    assert {c.origin for c in carried.caveats} == {CaveatOrigin.SIDE_A, CaveatOrigin.SIDE_B}


def test_every_origin_pair_stays_distinct() -> None:
    """All four origins, the same code, four occurrences."""
    groups = tuple((_caveat(origin=origin),) for origin in PROVENANCE_ORDER)
    carried = carry_caveats(*groups)

    assert carried.total == len(PROVENANCE_ORDER) == 4
    assert [c.origin for c in carried.caveats] == list(PROVENANCE_ORDER)


# --- 3. the count is occurrences, not unique pairs -------------------------------


def test_three_identical_occurrences_produce_a_total_of_three() -> None:
    """``total`` counts what is carried, never distinct ``(code, origin)`` pairs."""
    carried = carry_caveats((_caveat(), _caveat(), _caveat()))

    assert carried.total == 3
    assert len(carried.caveats) == 3
    assert len({(str(c.code), c.origin) for c in carried.caveats}) == 1


@pytest.mark.parametrize("occurrences", [1, 2, 3, 5, 8])
def test_the_total_equals_the_occurrence_count(occurrences: int) -> None:
    carried = carry_caveats(tuple(_caveat() for _ in range(occurrences)))
    assert carried.total == occurrences
    assert len(carried.caveats) == occurrences


def test_the_contract_refuses_a_total_that_disagrees_with_the_carriage() -> None:
    """A consumer rendering a subset stays detectable, whatever the multiplicity."""
    from analytics_interaction.contracts.answer import CaveatSet

    with pytest.raises(ValueError, match="disagrees"):
        CaveatSet(caveats=(_caveat(), _caveat()), total=1)


# --- 4. deterministic order, achieved without removing anything -------------------


def test_the_order_is_encounter_order() -> None:
    """Groups as passed, occurrences as produced. Nothing is sorted."""
    carried = carry_caveats(
        (_caveat(PARTIAL, origin=CaveatOrigin.VERDICT, message=OTHER),),
        (_caveat(origin=CaveatOrigin.SIDE_A), _caveat(origin=CaveatOrigin.SIDE_A)),
        (_caveat(origin=CaveatOrigin.SIDE_B),),
    )

    assert [c.origin for c in carried.caveats] == [
        CaveatOrigin.VERDICT,
        CaveatOrigin.SIDE_A,
        CaveatOrigin.SIDE_A,
        CaveatOrigin.SIDE_B,
    ]


def test_equal_inputs_produce_byte_identical_output() -> None:
    """`SC-028`. Determinism comes from stable order, not from collapsing."""

    def build() -> str:
        return carry_caveats(
            (_caveat(origin=CaveatOrigin.VERDICT),),
            (_caveat(), _caveat()),
        ).model_dump_json()

    assert build() == build()


def test_a_different_group_order_is_a_different_answer() -> None:
    """Encounter order is meaningful: it is provenance order.

    Reordering the groups reorders the caveats, which is correct — the caller
    passes them verdict-first, and a renderer showing side B's caveat above the
    verdict's would be misattributing prominence.
    """
    forward = carry_caveats((_caveat(origin=CaveatOrigin.VERDICT),), (_caveat(),))
    backward = carry_caveats((_caveat(),), (_caveat(origin=CaveatOrigin.VERDICT),))

    assert forward.total == backward.total == 2
    assert forward.model_dump_json() != backward.model_dump_json()


# --- 5 and 6. required multiplicity ------------------------------------------------


def test_carrying_both_required_occurrences_releases() -> None:
    carried = carry_caveats((_caveat(), _caveat()))
    required = ((str(LAGGING), CaveatOrigin.SIDE_A), (str(LAGGING), CaveatOrigin.SIDE_A))

    assert_caveats_are_releasable(carried, required=required)


def test_carrying_one_of_two_required_occurrences_withholds() -> None:
    """**The set-comparison bug, asserted.**

    A set would call this complete: the pair is present. The reader would see one
    qualification where upstream issued two.
    """
    carried = carry_caveats((_caveat(),))
    required = ((str(LAGGING), CaveatOrigin.SIDE_A), (str(LAGGING), CaveatOrigin.SIDE_A))

    with pytest.raises(ContractViolation) as refusal:
        assert_caveats_are_releasable(carried, required=required)
    assert refusal.value.code is Code.INTERPRETATION_VOCABULARY_UNRESOLVABLE
    assert "withheld in full" in refusal.value.detail


def test_carrying_three_where_two_are_required_releases() -> None:
    """The requirement is a floor, not an equality.

    Upstream stating two and the answer carrying three is a carriage question,
    not a completeness one — and refusing it would withhold an answer that
    disclosed more than was required.
    """
    carried = carry_caveats((_caveat(), _caveat(), _caveat()))
    required = ((str(LAGGING), CaveatOrigin.SIDE_A),) * 2

    assert_caveats_are_releasable(carried, required=required)


def test_multiplicity_is_tracked_per_origin() -> None:
    """Two on side A and one on side B is not three of anything."""
    carried = carry_caveats(
        (_caveat(origin=CaveatOrigin.SIDE_A), _caveat(origin=CaveatOrigin.SIDE_A)),
        (_caveat(origin=CaveatOrigin.SIDE_B),),
    )
    satisfied = (
        (str(LAGGING), CaveatOrigin.SIDE_A),
        (str(LAGGING), CaveatOrigin.SIDE_A),
        (str(LAGGING), CaveatOrigin.SIDE_B),
    )
    assert_caveats_are_releasable(carried, required=satisfied)

    unsatisfied = (*satisfied, (str(LAGGING), CaveatOrigin.SIDE_B))
    with pytest.raises(ContractViolation):
        assert_caveats_are_releasable(carried, required=unsatisfied)


def test_the_withholding_refusal_still_discloses_nothing() -> None:
    """Naming the missing code would disclose an upstream limitation."""
    carried = carry_caveats((_caveat(),))
    required = ((str(LAGGING), CaveatOrigin.SIDE_A),) * 2

    with pytest.raises(ContractViolation) as refusal:
        assert_caveats_are_releasable(carried, required=required)
    assert "SOURCE_LAGGING" not in str(refusal.value)
    assert "side_a" not in str(refusal.value)


# --- 7. wording and attribution survive byte-for-byte -------------------------------


def test_every_occurrence_keeps_its_exact_wording_code_and_origin() -> None:
    """Nothing is re-worded, re-coded, re-attributed or normalised."""
    first = _caveat(LAGGING, origin=CaveatOrigin.SIDE_A, message=TEXT)
    second = _caveat(PARTIAL, origin=CaveatOrigin.SIDE_B, message=OTHER)
    third = _caveat(LAGGING, origin=CaveatOrigin.SIDE_A, message=TEXT)

    carried = carry_caveats((first, second, third))

    assert carried.caveats[0].message_pt_br == TEXT
    assert carried.caveats[1].message_pt_br == OTHER
    assert carried.caveats[2].message_pt_br == TEXT
    assert len(carried.caveats[0].message_pt_br) == len(TEXT)
    assert [c.code for c in carried.caveats] == [LAGGING, PARTIAL, LAGGING]
    assert [c.origin for c in carried.caveats] == [
        CaveatOrigin.SIDE_A,
        CaveatOrigin.SIDE_B,
        CaveatOrigin.SIDE_A,
    ]


def test_an_upstream_002_code_is_carried_alongside_a_001_code() -> None:
    """Both namespaces travel; neither is translated into the other."""
    carried = carry_caveats(
        (
            _caveat(LAGGING, origin=CaveatOrigin.SINGLE),
            _caveat(AnalyticsReasonCode.RESULT_CELL_SUPPRESSED, origin=CaveatOrigin.SINGLE),
        )
    )
    assert carried.total == 2
    assert str(carried.caveats[0].code) != str(carried.caveats[1].code)


# --- 8. no container on the path can drop an occurrence -------------------------------


def test_the_carriage_path_uses_no_deduplicating_container() -> None:
    """**The structural guard.**

    A ``set``, ``frozenset`` or ``dict`` keyed on a caveat cannot hold duplicates,
    and that is how deduplication returns without anybody deciding to add it. The
    function that carries occurrences is scanned directly.
    """
    tree = ast.parse(inspect.getsource(carry_caveats))
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not called & {"set", "frozenset", "dict", "sorted", "unique"}

    comprehensions = [
        node for node in ast.walk(tree) if isinstance(node, ast.SetComp | ast.DictComp)
    ]
    assert not comprehensions, "a set or dict comprehension appears on the carriage path"


def test_the_module_declares_no_deduplication_helper() -> None:
    """Not merely uncalled — absent, so a later caller cannot reach one."""
    tree = ast.parse(Path(inspect.getfile(caveats_module)).read_text(encoding="utf-8"))
    defined = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert not defined & {"deduplicate", "dedupe", "unique", "collapse", "merge", "distinct"}


def test_the_completeness_check_counts_rather_than_sets() -> None:
    """A set here is exactly how a repeated required caveat passes validation."""
    from analytics_interaction.answer import withhold

    source = Path(inspect.getfile(withhold)).read_text(encoding="utf-8")
    assert "Counter(" in source

    tree = ast.parse(inspect.getsource(assert_caveats_are_releasable))
    comprehensions = [node for node in ast.walk(tree) if isinstance(node, ast.SetComp)]
    assert not comprehensions, "a set comprehension appears in the completeness check"


def test_a_hundred_occurrences_all_survive() -> None:
    """Scale, because a subtle collapse might only show above a threshold."""
    carried = carry_caveats(tuple(_caveat() for _ in range(100)))
    assert carried.total == 100
    assert len(carried.caveats) == 100


# --- and ALLOW_WITH_CAVEAT stays visibly distinct --------------------------------------


def test_a_caveated_answer_is_distinguishable_from_a_plain_one() -> None:
    """`SC-048`. An empty set and a populated one differ in the counted field.

    Not by prose, not by a flag somebody sets — by the count, which a renderer
    cannot show as zero without contradicting the payload it was given.
    """
    plain = carry_caveats()
    caveated = carry_caveats((_caveat(),))

    assert plain.total == 0
    assert caveated.total == 1
    assert plain.model_dump_json() != caveated.model_dump_json()


def test_an_empty_caveat_set_is_explicit_not_absent() -> None:
    """`FR-085`: required, always populated as a collection."""
    plain = carry_caveats()
    assert plain.caveats == ()
    assert "caveats" in plain.model_dump()
