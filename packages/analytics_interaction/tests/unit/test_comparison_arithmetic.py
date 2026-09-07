"""Exact arithmetic and the governed formula gate — T104, T106, T107.

The three implementation tasks of Phase 10 carry executable evidence lines, and
this is where they are executed:

* **T104** — values lifted to exact decimal; **no rounding applied by this
  feature**;
* **T106** — an unlisted formula refuses; **with `D-18` empty, every comparison
  refuses**; the zero-baseline rule is the governed one, never a local default;
* **T107** — differing declared units are a material mismatch, **never
  converted**.

Every governed formula exercised here is **fixture-only** and marked as such at
source. `D-18` ships empty and no formula, unit rule, rounding or zero-baseline
behaviour is proposed by this suite — the shipped-state test asserts the empty
set refuses, which is the only claim about production content anything here
makes.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from analytics_interaction.comparison.compute import (
    DIVIDING_OPERATIONS,
    OPERATIONS,
    derive_figure,
    to_exact,
)
from analytics_interaction.comparison.formula import (
    EXECUTABLE_ZERO_BASELINE_RULES,
    REFUSE_RULE,
    assert_baseline_is_usable,
    resolve_formula,
)
from analytics_interaction.comparison.units import assert_units_agree, declared_unit, result_unit
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code
from analytics_interaction.governance.resolve import ContentUnresolvable
from analytics_interaction.governance.schemas import ComparisonFormula

from ..conftest import ON
from ..fixtures.comparisons import (
    ABSOLUTE_DIFFERENCE,
    FIXTURE_MARKER,
    PERCENTAGE_CHANGE,
    RATIO,
    executed,
    formula_instances,
)

pytestmark = pytest.mark.unit

FIXTURE_SET = formula_instances(ABSOLUTE_DIFFERENCE, RATIO, PERCENTAGE_CHANGE)


# --- exact decimal ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("primary", "baseline", "expected"),
    [
        (Decimal("100"), Decimal("80"), Decimal("20")),
        (Decimal("0.3"), Decimal("0.1"), Decimal("0.2")),
        (100, 80, Decimal("20")),
        (Decimal("-5"), Decimal("5"), Decimal("-10")),
        (Decimal("1.005"), Decimal("1.000"), Decimal("0.005")),
    ],
)
def test_the_absolute_difference_is_exact(
    primary: Decimal | int, baseline: Decimal | int, expected: Decimal
) -> None:
    """`SC-040`. The second case is the one binary float gets wrong.

    ``0.3 - 0.1`` in float is ``0.19999999999999998``. In exact decimal it is
    ``0.2``, and it is ``0.2`` on every platform.
    """
    figure = derive_figure(
        formula_id="absolute_difference",
        unit=FIXTURE_MARKER,
        primary=primary,
        baseline=baseline,
        derived_from=("a", "b"),
        basis="teste",
    )
    assert figure.value == expected
    assert isinstance(figure.value, Decimal)


def test_the_exact_difference_is_not_the_float_one() -> None:
    """Stated as a contrast, so the property is visible rather than asserted."""
    figure = derive_figure(
        formula_id="absolute_difference",
        unit=FIXTURE_MARKER,
        primary=Decimal("0.3"),
        baseline=Decimal("0.1"),
        derived_from=("a", "b"),
        basis="teste",
    )
    assert str(figure.value) == "0.2"
    assert str(0.3 - 0.1) != "0.2"


@pytest.mark.parametrize(
    ("formula_id", "primary", "baseline", "expected"),
    [
        ("ratio", Decimal("150"), Decimal("100"), Decimal("1.5")),
        ("percentage_change", Decimal("150"), Decimal("100"), Decimal("50")),
        ("percentage_change", Decimal("50"), Decimal("100"), Decimal("-50")),
    ],
)
def test_every_registered_operation_computes_exactly(
    formula_id: str, primary: Decimal, baseline: Decimal, expected: Decimal
) -> None:
    """The three ids `contracts/governed-content.md` names, and only those."""
    figure = derive_figure(
        formula_id=formula_id,
        unit=FIXTURE_MARKER,
        primary=primary,
        baseline=baseline,
        derived_from=("a", "b"),
        basis="teste",
    )
    assert figure.value == expected


def test_the_operation_registry_is_the_closed_contract_set() -> None:
    assert set(OPERATIONS) == {"absolute_difference", "ratio", "percentage_change"}
    assert set(DIVIDING_OPERATIONS) == {"ratio", "percentage_change"}


def test_the_registry_cannot_be_extended_at_runtime() -> None:
    """A registrable formula set would be an ungoverned formula set."""
    with pytest.raises(TypeError):
        OPERATIONS["invented"] = lambda a, b: a  # type: ignore[index]


# --- no rounding, no conversion, no fallback ---------------------------------------


def test_no_result_is_quantised() -> None:
    """A repeating quotient keeps every digit the division produced.

    Rounding to two places here would decide how every ratio in the product
    reads, which is `D-18`'s decision and not this feature's.
    """
    figure = derive_figure(
        formula_id="ratio",
        unit=FIXTURE_MARKER,
        primary=Decimal("1"),
        baseline=Decimal("3"),
        derived_from=("a", "b"),
        basis="teste",
    )
    assert str(figure.value).startswith("0.3333333")
    assert len(str(figure.value)) > 5


def test_a_formula_declaring_a_quantisation_refuses() -> None:
    """This feature applies no governed rounding; it refuses to guess at one."""
    quantised = ComparisonFormula(
        id="absolute_difference",
        surface_forms=("x",),
        unit_rule=FIXTURE_MARKER,
        zero_baseline=REFUSE_RULE,
        quantisation="half_up_2",
    )
    with pytest.raises(ContractViolation) as refusal:
        resolve_formula("absolute_difference", on=ON, instances=formula_instances(quantised))
    assert refusal.value.code is Code.CALCULATION_NOT_SUPPORTED
    assert "quantisation" in refusal.value.detail


@pytest.mark.parametrize("value", [0.1, 1.0, float("nan"), float("inf")])
def test_a_float_operand_is_refused_never_converted(value: float) -> None:
    """``Decimal(0.1)`` is exact — and exactly the wrong number."""
    with pytest.raises(ContractViolation) as refusal:
        to_exact(value)
    assert refusal.value.code is Code.COMPARISON_SIDE_INVALID


@pytest.mark.parametrize("value", ["1.5", None, b"1", [1], True, False])
def test_only_the_two_governed_cell_types_lift(value: object) -> None:
    """``str`` lifts exactly and is still refused: it is not a cell value.

    ``bool`` is checked before ``int`` deliberately — it *is* an ``int`` in
    Python, and a comparison over True and False is not arithmetic anybody asked
    for.
    """
    with pytest.raises(ContractViolation):
        to_exact(value)


@pytest.mark.parametrize(
    ("value", "expected"), [(7, Decimal(7)), (Decimal("7.50"), Decimal("7.50"))]
)
def test_the_governed_cell_types_lift_unchanged(value: object, expected: Decimal) -> None:
    lifted = to_exact(value)
    assert lifted == expected
    assert str(lifted) == str(expected)


# --- the closed formula set --------------------------------------------------------


def test_an_unlisted_formula_refuses() -> None:
    """Never approximated by one that is listed (`FR-071`)."""
    with pytest.raises(ContractViolation) as refusal:
        resolve_formula("year_over_year", on=ON, instances=FIXTURE_SET)
    assert refusal.value.code is Code.CALCULATION_NOT_SUPPORTED


def test_the_refusal_discloses_no_governed_formula() -> None:
    """A caller who asked for something else learns nothing about the set."""
    with pytest.raises(ContractViolation) as refusal:
        resolve_formula("year_over_year", on=ON, instances=FIXTURE_SET)
    for governed in ("absolute_difference", "ratio", "percentage_change"):
        assert governed not in refusal.value.detail


def test_a_governed_formula_this_feature_cannot_compute_refuses() -> None:
    """Both gates are closed: `D-18` may declare more than the code implements."""
    exotic = ComparisonFormula(
        id="compound_annual_growth",
        surface_forms=("cagr",),
        unit_rule=FIXTURE_MARKER,
        zero_baseline=REFUSE_RULE,
    )
    with pytest.raises(ContractViolation) as refusal:
        resolve_formula("compound_annual_growth", on=ON, instances=formula_instances(exotic))
    assert refusal.value.code is Code.CALCULATION_NOT_SUPPORTED


def test_derive_figure_refuses_an_unregistered_id_even_if_a_caller_reaches_it() -> None:
    """Defence in depth: the gate is upstream, and the arithmetic checks anyway."""
    with pytest.raises(ContractViolation) as refusal:
        derive_figure(
            formula_id="invented",
            unit="x",
            primary=Decimal(1),
            baseline=Decimal(1),
            derived_from=("a", "b"),
            basis="teste",
        )
    assert refusal.value.code is Code.CALCULATION_NOT_SUPPORTED


# --- D-18's shipped state ----------------------------------------------------------


def test_the_shipped_formula_set_refuses_every_comparison() -> None:
    """**Zero effective instances.** The designed state, asserted directly."""
    with pytest.raises(ContentUnresolvable) as refusal:
        resolve_formula("absolute_difference", on=ON, instances=())
    assert refusal.value.code is Code.INTERPRETATION_VOCABULARY_UNRESOLVABLE


def test_the_real_governed_file_still_declares_no_formula() -> None:
    """Reads `interpretation_governance/` itself, not a fixture.

    If somebody authors a formula into the shipped file, this fails — which is
    the point. `D-18` is an open external record and content arriving without it
    being closed is the thing to catch.
    """
    with pytest.raises(ContentUnresolvable) as refusal:
        resolve_formula("absolute_difference", on=ON)
    assert refusal.value.code is Code.INTERPRETATION_VOCABULARY_UNRESOLVABLE


def test_an_effective_set_declaring_no_formula_refuses() -> None:
    """Empty is unresolvable, not unconstrained."""
    with pytest.raises(ContentUnresolvable):
        resolve_formula("absolute_difference", on=ON, instances=formula_instances())


def test_two_simultaneously_effective_sets_refuse() -> None:
    """Ambiguous governance is refused, never resolved by picking one."""
    both = (
        *formula_instances(ABSOLUTE_DIFFERENCE, version="a"),
        *formula_instances(RATIO, version="b"),
    )
    with pytest.raises(ContentUnresolvable):
        resolve_formula("absolute_difference", on=ON, instances=both)


def test_a_set_effective_only_later_refuses_today() -> None:
    """No carry-forward, no substitution from a future instance."""
    future = formula_instances(ABSOLUTE_DIFFERENCE, effective_from=date(2099, 1, 1))
    with pytest.raises(ContentUnresolvable):
        resolve_formula("absolute_difference", on=ON, instances=future)


def test_an_expired_set_refuses_rather_than_carrying_forward() -> None:
    expired = formula_instances(
        ABSOLUTE_DIFFERENCE, effective_from=date(2020, 1, 1), effective_to=date(2020, 12, 31)
    )
    with pytest.raises(ContentUnresolvable):
        resolve_formula("absolute_difference", on=ON, instances=expired)


# --- the governed zero baseline ----------------------------------------------------


def test_only_one_zero_baseline_rule_is_executable() -> None:
    """``DerivedFigure.value`` is a required ``Decimal``: a number, or nothing."""
    assert set(EXECUTABLE_ZERO_BASELINE_RULES) == {REFUSE_RULE}


def test_a_zero_baseline_follows_the_governed_rule() -> None:
    """The fixture declares ``refuse_comparison``, so the comparison refuses."""
    with pytest.raises(ContractViolation) as refusal:
        assert_baseline_is_usable(RATIO, Decimal(0))
    assert refusal.value.code is Code.CALCULATION_NOT_SUPPORTED
    assert "governed zero-baseline rule" in refusal.value.detail


def test_a_zero_baseline_under_a_non_dividing_formula_proceeds() -> None:
    """An absolute difference over a zero baseline is perfectly well-defined.

    Refusing it would be inventing a restriction the arithmetic does not have and
    the governed rule does not state.
    """
    assert_baseline_is_usable(ABSOLUTE_DIFFERENCE, Decimal(0))
    figure = derive_figure(
        formula_id="absolute_difference",
        unit=FIXTURE_MARKER,
        primary=Decimal("5"),
        baseline=Decimal(0),
        derived_from=("a", "b"),
        basis="teste",
    )
    assert figure.value == Decimal(5)


def test_a_zero_baseline_rule_this_feature_cannot_carry_out_refuses() -> None:
    """Distinguished in detail from applying the rule, because it means something else."""
    invented = ComparisonFormula(
        id="ratio",
        surface_forms=("x",),
        unit_rule=FIXTURE_MARKER,
        zero_baseline="treat_as_infinite",
    )
    with pytest.raises(ContractViolation) as refusal:
        resolve_formula("ratio", on=ON, instances=formula_instances(invented))
    assert refusal.value.code is Code.CALCULATION_NOT_SUPPORTED
    assert "not one this feature can carry out" in refusal.value.detail


def test_no_division_guard_exists_outside_the_governed_rule() -> None:
    """The arithmetic itself does not special-case zero.

    ``derive_figure`` divides. Reaching it with a zero baseline raises Python's
    own error rather than yielding a substituted value — proving there is no
    local fallback that a governed rule could be bypassed to reach.
    """
    from decimal import DivisionByZero

    with pytest.raises(DivisionByZero):
        derive_figure(
            formula_id="ratio",
            unit=FIXTURE_MARKER,
            primary=Decimal(1),
            baseline=Decimal(0),
            derived_from=("a", "b"),
            basis="teste",
        )


# --- units --------------------------------------------------------------------------


def test_compatible_units_agree_and_return_the_shared_unit() -> None:
    unit = assert_units_agree(executed(unit="count").result, executed(unit="count").result)
    assert unit == "count"


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("count", "minutes"),
        ("BRL", "USD"),
        ("count", "COUNT"),
        ("count", "count "),
        ("seconds", "minutes"),
    ],
)
def test_differing_units_refuse_and_are_never_converted(left: str, right: str) -> None:
    """Including case and whitespace: those are normalisations nobody governed."""
    with pytest.raises(ContractViolation) as refusal:
        assert_units_agree(executed(unit=left).result, executed(unit=right).result)
    assert refusal.value.code is Code.COMPARISON_SIDE_INVALID
    assert left not in refusal.value.detail
    assert right not in refusal.value.detail


def test_the_result_unit_comes_from_the_formula_not_from_an_operand() -> None:
    """A ratio's unit is neither operand's, which is why `D-18` declares it."""
    assert result_unit(RATIO) != declared_unit(executed(unit="count").result)
    assert result_unit(RATIO) == RATIO.unit_rule


def test_a_side_without_exactly_one_metric_column_refuses() -> None:
    """Zero means nothing to compare; two means picking one would be choosing."""
    with pytest.raises(ContractViolation):
        declared_unit(
            executed(dimension_columns=("country", "platform")).result.model_copy(
                update={"columns": ()}
            )
        )


def test_the_metric_column_is_read_past_dimension_columns() -> None:
    """A positional read would return a dimension's unit whenever one came first."""
    assert declared_unit(executed(unit="count", dimension_columns=("country",)).result) == "count"


# --- determinism ---------------------------------------------------------------------


def test_repeated_equivalent_inputs_serialise_byte_identically() -> None:
    """`SC-005`: identical output for identical input, including the last digit."""
    figures = [
        derive_figure(
            formula_id="percentage_change",
            unit=FIXTURE_MARKER,
            primary=Decimal("1"),
            baseline=Decimal("3"),
            derived_from=("a", "b"),
            basis="teste",
        )
        for _ in range(3)
    ]
    serialised = {figure.model_dump_json() for figure in figures}
    assert len(serialised) == 1


def test_the_figure_records_its_formula_unit_operands_and_basis() -> None:
    """`DerivedFigure` carries what makes the number auditable."""
    figure = derive_figure(
        formula_id="absolute_difference",
        unit=RATIO.unit_rule,
        primary=Decimal("10"),
        baseline=Decimal("4"),
        derived_from=("claim-a", "claim-b"),
        basis="janela governada",
    )
    assert figure.value == Decimal(6)
    assert figure.unit == RATIO.unit_rule
    assert figure.derived_from == ("claim-a", "claim-b")
    assert figure.basis == "janela governada"
