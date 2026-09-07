"""Suppression properties — T082 (FR-041; SC-028, SC-029).

Four properties, and the third is the one that is easy to get wrong.

1. **Threshold behaviour** — strictly below the governed floor is withheld; a
   group exactly at the floor is releasable.
2. **Explicit reasons** — never an absent row, an empty result or a zero.
3. **Arithmetic resistance** — a single suppressed cell beside a visible total
   is one equation in one variable, so suppression extends until it is not.
4. **Values are never altered** — no rounding, no noise, no banding. A
   perturbed figure is still a returned figure, and the caller cannot tell how
   far from the truth it is.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from analytics_query.contracts._base import build
from analytics_query.contracts.policy import PolicyApproval, QueryPolicy
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.contracts.result import ResultCell
from analytics_query.results.anti_reconstruction import (
    FullySuppressed,
    extend_suppression,
    is_reconstructible,
)
from analytics_query.results.suppression import suppress_cell, suppress_row, would_suppress

pytestmark = pytest.mark.unit

POLICY = build(
    QueryPolicy,
    version="p-1",
    effective_from=date(2026, 8, 1),
    approval=PolicyApproval(
        approver_role="data_platform", evidence_ref="a-1", approved_on=date(2026, 8, 1)
    ),
    maximum_bytes_billed=1,
    maximum_rows=1,
    execution_timeout_seconds=1,
    maximum_range_days=1,
    minimum_aggregation_threshold=5,
)


def _cell(value: str) -> ResultCell:
    return ResultCell(value=Decimal(value))


# --- 1. threshold behaviour --------------------------------------------------


@pytest.mark.parametrize("size", [0, 1, 2, 3, 4])
def test_a_group_below_the_threshold_is_withheld(size: int) -> None:
    assert would_suppress(size, POLICY)
    assert suppress_cell(_cell("42"), size, POLICY).suppressed


@pytest.mark.parametrize("size", [5, 6, 100])
def test_a_group_at_or_above_the_threshold_is_released(size: int) -> None:
    """The floor is the smallest publishable size, not the smallest suppressed one."""
    assert not would_suppress(size, POLICY)
    assert suppress_cell(_cell("42"), size, POLICY).value == Decimal("42")


def test_the_threshold_comes_from_the_policy_not_a_default() -> None:
    """No literal floor anywhere in the executable code."""
    import ast
    import inspect

    from analytics_query.results import suppression

    tree = ast.parse(inspect.getsource(suppression))
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            node.value = ast.Constant("")
    code = ast.unparse(tree)
    for marker in ("= 5", "DEFAULT_THRESHOLD", "or 5", "MINIMUM ="):
        assert marker not in code


# --- 2. explicit reasons -----------------------------------------------------


def test_a_suppressed_cell_carries_its_reason_and_no_value() -> None:
    cell = suppress_cell(_cell("42"), 2, POLICY)
    assert cell.value is None
    assert cell.suppression_reason is AnalyticsReasonCode.RESULT_CELL_SUPPRESSED


def test_suppression_is_never_a_zero() -> None:
    """A zero is a claim about the data; a suppression is a claim about access."""
    assert suppress_cell(_cell("42"), 2, POLICY).value != Decimal("0")
    assert suppress_cell(_cell("42"), 2, POLICY).value is not None or True
    assert suppress_cell(_cell("42"), 2, POLICY).value is None


def test_suppression_is_never_an_absent_cell() -> None:
    """The row keeps its width; the cell keeps its position."""
    row = (_cell("1"), _cell("2"), _cell("3"))
    suppressed = suppress_row(row, (2, 10, 10), POLICY)
    assert len(suppressed) == 3
    assert suppressed[0].suppressed
    assert not suppressed[1].suppressed


def test_misaligned_group_sizes_raise_rather_than_guess() -> None:
    """Not knowing which figure a count describes means not knowing what is safe."""
    with pytest.raises(ValueError, match="do not align"):
        suppress_row((_cell("1"), _cell("2")), (10,), POLICY)


# --- 3. arithmetic-reconstruction resistance --------------------------------


def test_one_suppressed_cell_beside_a_visible_total_is_reconstructible() -> None:
    row = (suppress_cell(_cell("1"), 2, POLICY), _cell("2"), _cell("3"))
    assert is_reconstructible(row, total_visible=True)


def test_two_suppressed_cells_are_not_reconstructible() -> None:
    """Two unknowns leave the system underdetermined."""
    row = (
        suppress_cell(_cell("1"), 2, POLICY),
        suppress_cell(_cell("2"), 2, POLICY),
        _cell("3"),
    )
    assert not is_reconstructible(row, total_visible=True)


def test_no_visible_total_leaves_nothing_to_subtract_from() -> None:
    row = (suppress_cell(_cell("1"), 2, POLICY), _cell("2"))
    assert not is_reconstructible(row, total_visible=False)


def test_suppression_extends_until_the_arithmetic_fails() -> None:
    row = suppress_row((_cell("1"), _cell("20"), _cell("30")), (2, 10, 50), POLICY)
    assert sum(c.suppressed for c in row) == 1

    extended = extend_suppression(row, (2, 10, 50), POLICY, total_visible=True)
    assert sum(c.suppressed for c in extended) == 2
    assert not is_reconstructible(extended, total_visible=True)


def test_the_extension_takes_the_smallest_visible_group() -> None:
    """The cell whose exposure would identify the fewest people."""
    row = suppress_row((_cell("1"), _cell("20"), _cell("30")), (2, 10, 50), POLICY)
    extended = extend_suppression(row, (2, 10, 50), POLICY, total_visible=True)
    assert extended[1].suppressed  # group size 10, the smaller of the two visible
    assert not extended[2].suppressed


def test_no_extension_happens_when_nothing_is_reconstructible() -> None:
    row = suppress_row((_cell("1"), _cell("2")), (10, 10), POLICY)
    assert extend_suppression(row, (10, 10), POLICY, total_visible=True) == row


def test_a_fully_suppressed_row_refuses_rather_than_returning_blanks() -> None:
    """A table of empty cells still shows the cohort's shape."""
    row = suppress_row((_cell("1"), _cell("2")), (2, 2), POLICY)
    with pytest.raises(FullySuppressed) as caught:
        extend_suppression(row, (2, 2), POLICY, total_visible=True)
    assert caught.value.code is AnalyticsReasonCode.RESULT_FULLY_SUPPRESSED


# --- 4. values are never altered --------------------------------------------


@pytest.mark.parametrize("raw", ["42", "42.5", "0.001", "1000000", "3.14159265358979"])
def test_a_released_value_is_returned_exactly(raw: str) -> None:
    released = suppress_cell(_cell(raw), 100, POLICY)
    assert released.value == Decimal(raw)
    assert str(released.value) == raw


def test_no_rounding_noise_or_banding_appears_in_either_module() -> None:
    """Scans executable code, not prose.

    Both modules *discuss* rounding and noise at length — explaining why there
    is none is the point. What must not exist is the arithmetic.
    """
    import ast
    import inspect

    from analytics_query.results import anti_reconstruction, suppression

    for module in (suppression, anti_reconstruction):
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                node.value = ast.Constant("")  # blank every docstring
        code = ast.unparse(tree)
        for marker in ("round(", "random", "gauss", "laplace", "jitter", "//"):
            assert marker not in code, f"{module.__name__} perturbs values: {marker!r}"


def test_a_released_cell_is_the_same_object() -> None:
    """Nothing is rebuilt, so nothing can be altered in the rebuilding."""
    cell = _cell("42")
    assert suppress_cell(cell, 100, POLICY) is cell
