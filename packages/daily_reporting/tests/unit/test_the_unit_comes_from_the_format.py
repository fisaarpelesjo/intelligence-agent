"""Points for a rate, relative percent for the rest — `T814`, `T815`.

> *"Chargeback rose 1,4 point, from 1,4 % to 2,8 %"* reads.
> *"It rose 76 %"* does not.

And there is **no percentage point of 748 trials**.

## The strongest thing this file asserts is what the decision CANNOT see

:func:`variation_unit_for` takes the format and nothing else, so it cannot special-case
a KPI by name — and a function that could is one edit away from a table of twenty
exceptions, which is `FR-810` lost quietly. That is checked over the signature, because
behaviour with the extra parameter unused looks exactly like behaviour without it.
"""

from __future__ import annotations

import ast
import inspect
from decimal import Decimal

import pytest

from daily_reporting.numbers import variation as variation_module
from daily_reporting.numbers.variation import (
    RATE_FORMAT,
    VariationUnit,
    variation_between,
    variation_unit_for,
)

pytestmark = pytest.mark.unit


def test_a_rate_moves_in_points() -> None:
    assert variation_unit_for(RATE_FORMAT) is VariationUnit.PERCENTAGE_POINTS
    assert variation_unit_for("  PCT  ") is VariationUnit.PERCENTAGE_POINTS


@pytest.mark.parametrize("format_type", ["usd_cents", "usd", "brl", "qty", "count", "months", ""])
def test_everything_else_moves_in_relative_percent(format_type: str) -> None:
    assert variation_unit_for(format_type) is VariationUnit.RELATIVE_PERCENT


def test_the_decisions_only_input_is_the_format() -> None:
    """It cannot see the KPI's name, so it cannot know which KPI it is deciding for."""
    parameters = list(inspect.signature(variation_unit_for).parameters)
    assert parameters == ["format_type"], (
        f"the unit decision can see {parameters}; anything beyond the format lets it "
        f"special-case a KPI by name"
    )


def test_the_points_arithmetic_is_a_subtraction() -> None:
    """2,8 % less 1,4 % is 1,4 points, and never 76 anything."""
    moved = variation_between(Decimal("1.4"), Decimal("2.8"), VariationUnit.PERCENTAGE_POINTS)
    assert moved == Decimal("1.4")


def test_the_relative_arithmetic_is_a_ratio() -> None:
    assert variation_between(
        Decimal("500"), Decimal("600"), VariationUnit.RELATIVE_PERCENT
    ) == Decimal("20")


def test_a_previous_zero_answers_undefined_rather_than_zero() -> None:
    """**`None`, not `0`.** Reporting zero there states that nothing happened."""
    assert variation_between(Decimal(0), Decimal("40"), VariationUnit.RELATIVE_PERCENT) is None


def test_a_previous_zero_in_points_is_still_a_number() -> None:
    """A rate that was 0,0 % and is now 1,4 % moved 1,4 points, which is defined."""
    assert variation_between(
        Decimal(0), Decimal("1.4"), VariationUnit.PERCENTAGE_POINTS
    ) == Decimal("1.4")


def test_nothing_in_this_module_converts_between_currencies() -> None:
    """`FR-807`. The view holds no exchange rate, so a converted figure is a choice."""
    source = ast.parse(inspect.getsource(variation_module))
    docstrings = {
        ast.get_docstring(node, clean=False)
        for node in ast.walk(source)
        if isinstance(node, ast.Module | ast.FunctionDef | ast.ClassDef)
    }
    reached = {
        node.value
        for node in ast.walk(source)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value not in docstrings
    }
    offending = sorted(text for text in reached if "value_usd" in text or "value_brl" in text)
    assert not offending, f"the unit module reaches for a currency column: {offending}"
