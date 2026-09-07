"""Unsupported calculations refuse — T081 (FR-013, FR-014; SC-021).

Five kinds refuse directly. **The decomposition case is asserted explicitly, not
inferred from the direct one** — and that separation is the point of this file.

Refusing "faturamento dividido por instalações" is easy. Refusing the same
request asked in pieces — "me dê faturamento", "agora me dê instalações", "vou
dividir" — is the requirement, because answering each governed step *is*
answering the ungoverned whole. `FR-013` says the combination is never produced,
so the refusal is of the **plan**, not of the phrasing.

A suite that tested only the direct form would pass against an implementation
that refused the sentence and happily served the pieces. So the decomposition
case gets its own tests, its own count of governed steps, and an assertion that
the code is the **same** — a distinct code would tell a caller that decomposition
was detected, and therefore that the boundary is worth probing.

Additivity refusals are checked from the other side: they belong to `001`, and
this feature must pass the upstream code through rather than restating it in this
layer's vocabulary (`FR-021`).
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from semantic_catalog.contracts.reason_codes import ReasonCode

from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code
from analytics_interaction.interpretation import calculations as calculations_module
from analytics_interaction.interpretation.calculations import (
    UnsupportedCalculation,
    refuse_decomposition,
    refuse_unsupported,
)
from analytics_interaction.interpretation.operators import require_governed_operator

pytestmark = pytest.mark.unit


# --- the five kinds refuse directly --------------------------------------------


def test_the_kind_set_is_the_five_the_contract_enumerates() -> None:
    assert {kind.value for kind in UnsupportedCalculation} == {
        "custom_formula",
        "forecast",
        "causal_attribution",
        "ratio_of_unrelated_metrics",
        "arbitrary_reaggregation",
    }


@pytest.mark.parametrize("kind", list(UnsupportedCalculation))
def test_each_unsupported_kind_refuses(kind: UnsupportedCalculation) -> None:
    refusal = refuse_unsupported(kind)
    assert refusal.code is Code.CALCULATION_NOT_SUPPORTED
    assert kind.value in refusal.detail


def test_a_custom_formula_refuses() -> None:
    """Only `D-18`'s closed formula set is governed, and it is empty today."""
    assert refuse_unsupported(UnsupportedCalculation.CUSTOM_FORMULA).code is (
        Code.CALCULATION_NOT_SUPPORTED
    )


def test_a_forecast_refuses() -> None:
    """The catalog governs the past. A forecast needs a model of the future."""
    assert refuse_unsupported(UnsupportedCalculation.FORECAST).code is (
        Code.CALCULATION_NOT_SUPPORTED
    )


def test_a_causal_attribution_refuses() -> None:
    """Constitution II forbids causal claims outright."""
    assert refuse_unsupported(UnsupportedCalculation.CAUSAL_ATTRIBUTION).code is (
        Code.CALCULATION_NOT_SUPPORTED
    )


def test_a_ratio_of_unrelated_metrics_refuses() -> None:
    """Two metrics with no declared relationship produce a number with no meaning."""
    assert refuse_unsupported(UnsupportedCalculation.RATIO_OF_UNRELATED_METRICS).code is (
        Code.CALCULATION_NOT_SUPPORTED
    )


def test_an_arbitrary_reaggregation_refuses() -> None:
    """The metric's declared additivity decides which aggregations are valid."""
    assert refuse_unsupported(UnsupportedCalculation.ARBITRARY_REAGGREGATION).code is (
        Code.CALCULATION_NOT_SUPPORTED
    )


# --- the decomposition case, asserted explicitly -------------------------------


@pytest.mark.parametrize("kind", list(UnsupportedCalculation))
@pytest.mark.parametrize("steps", [2, 3, 5])
def test_a_decomposition_into_governed_steps_still_refuses(
    kind: UnsupportedCalculation, steps: int
) -> None:
    """Governed steps are never combined into the unsupported figure.

    Every kind, at several step counts — because "it refuses when asked
    directly" and "it refuses when assembled" are different claims about
    different code paths.
    """
    refusal = refuse_decomposition(kind, governed_steps=steps)
    assert refusal.code is Code.CALCULATION_NOT_SUPPORTED
    assert str(steps) in refusal.detail
    assert kind.value in refusal.detail


def test_the_decomposition_refusal_carries_the_same_code_as_the_direct_one() -> None:
    """A distinct code would tell a caller that decomposition was detected.

    That is information they cannot act on and an attacker can: it says the
    boundary noticed, and therefore that it is worth probing.
    """
    kind = UnsupportedCalculation.RATIO_OF_UNRELATED_METRICS
    assert refuse_unsupported(kind).code is refuse_decomposition(kind, governed_steps=2).code


def test_the_decomposition_refusal_records_how_many_governed_steps_were_involved() -> None:
    """Two governed steps assembled is a different fact from one bad request.

    A reviewer reading the audit trail should be able to tell them apart, even
    though the caller cannot.
    """
    refusal = refuse_decomposition(
        UnsupportedCalculation.RATIO_OF_UNRELATED_METRICS, governed_steps=2
    )
    assert "2 governed steps" in refusal.detail


def test_neither_refusal_quotes_the_question() -> None:
    """`FR-045`: the phrasing is never reproduced."""
    for refusal in (
        refuse_unsupported(UnsupportedCalculation.FORECAST),
        refuse_decomposition(UnsupportedCalculation.FORECAST, governed_steps=3),
    ):
        rendered = f"{refusal!s} {refusal.detail}".lower()
        for phrasing in ("faturamento", "dividido", "próximo mês", "prever"):
            assert phrasing not in rendered


# --- no path assembles the unsupported figure ----------------------------------


def test_the_module_performs_no_arithmetic() -> None:
    """The refusals are refusals. Nothing here computes a combination.

    A module that could divide two governed figures would be one assignment away
    from producing the ungoverned one.
    """
    source = Path(inspect.getfile(calculations_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    operations = [
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Add | ast.Sub | ast.Mult | ast.Div | ast.Mod | ast.Pow)
    ]
    assert not operations, f"the module computes: {operations}"


def test_the_module_returns_refusals_rather_than_values() -> None:
    """Every public function's return type is a governed refusal."""
    for function in (refuse_unsupported, refuse_decomposition):
        annotation = inspect.signature(function).return_annotation
        assert annotation in (ContractViolation, "ContractViolation")


def test_no_governed_operator_expresses_an_unsupported_calculation() -> None:
    """The operator matrix cannot be used to sneak one through.

    "greater than" is the natural way to ask for a threshold comparison the
    matrix does not have, and it abstains rather than being approximated with
    ``between`` and an invented ceiling.
    """
    for ungoverned in ("gt", "gte", "lt", "lte", "divide", "ratio", "regex"):
        with pytest.raises(ContractViolation) as caught:
            require_governed_operator(ungoverned)
        assert caught.value.code is Code.CALCULATION_NOT_SUPPORTED


# --- additivity stays upstream --------------------------------------------------


def test_the_additivity_code_belongs_to_001_and_is_not_restated_here() -> None:
    """`FR-021`: an upstream refusal is passed through, never paraphrased.

    `001` has a code for an aggregation a metric's declared additivity forbids.
    This feature declares none of its own — asserted by the three namespaces
    being disjoint, and by no interpretation code naming additivity.
    """
    upstream = {code.value for code in ReasonCode}
    assert any("ADDITIV" in code for code in upstream), "001 owns an additivity code"

    interpretation = {code.value for code in Code}
    assert not any("ADDITIV" in code for code in interpretation)
    assert not interpretation & upstream


def test_no_interpretation_code_restates_an_aggregation_concern() -> None:
    """Grain, additivity and aggregation are `001`'s vocabulary."""
    for concern in ("GRAIN", "AGGREGAT", "ADDITIV"):
        assert not [code.value for code in Code if concern in code.value]
