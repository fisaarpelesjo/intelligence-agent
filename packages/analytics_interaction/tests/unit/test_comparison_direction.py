"""The direction reading, and the sign convention it inherits.

The owner requires a comparison to report increase, fall or stability, and requires the model to
receive that word rather than choose it. So the cases here are about **determinism** and about the
one judgement the function takes as a parameter.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from analytics_interaction.comparison.compute import OPERATIONS
from analytics_interaction.comparison.direction import Direction, classify_direction

pytestmark = pytest.mark.unit


class TestTheThreeReadings:
    """Sign in, word out. Nothing here rounds and nothing reads a clock."""

    @pytest.mark.parametrize(
        ("difference", "expected"),
        [
            (Decimal(1), Direction.INCREASE),
            (Decimal(18432), Direction.INCREASE),
            (Decimal("0.01"), Direction.INCREASE),
            (Decimal(-1), Direction.DECREASE),
            (Decimal(-18432), Direction.DECREASE),
            (Decimal("-0.01"), Direction.DECREASE),
            (Decimal(0), Direction.STABLE),
        ],
    )
    def test_a_difference_reads_as_one_direction(
        self, difference: Decimal, expected: Direction
    ) -> None:
        assert classify_direction(difference) is expected

    def test_there_are_exactly_three_directions(self) -> None:
        """A fourth would be a reading nobody defined, so the set is asserted closed."""
        assert [member.value for member in Direction] == ["increase", "decrease", "stable"]

    def test_the_default_tolerance_is_zero(self) -> None:
        """The only band this feature can justify on its own: exact equality is stability."""
        assert classify_direction(Decimal("0.000001")) is Direction.INCREASE


class TestTheSignConventionIsInherited:
    """The direction must agree with the arithmetic that produced the number."""

    def test_it_matches_the_governed_absolute_difference(self) -> None:
        """`primary - baseline`, taken from `compute.OPERATIONS` rather than restated here.

        This is the case that would catch a reversed convention: if either side flipped, growth
        would read as a fall and every comparison in the product would be backwards.
        """
        difference = OPERATIONS["absolute_difference"](Decimal(120), Decimal(100))
        assert classify_direction(difference) is Direction.INCREASE

    def test_a_fall_through_the_same_path(self) -> None:
        difference = OPERATIONS["absolute_difference"](Decimal(80), Decimal(100))
        assert classify_direction(difference) is Direction.DECREASE

    def test_equal_sides_are_stable(self) -> None:
        difference = OPERATIONS["absolute_difference"](Decimal(100), Decimal(100))
        assert classify_direction(difference) is Direction.STABLE

    def test_a_zero_baseline_still_yields_a_direction(self) -> None:
        """An absolute difference over a zero baseline is well defined, and `formula.py` agrees.

        The governed zero-baseline rule refuses the operations that **divide**; going from nothing
        to something is an increase, and refusing to say so would be inventing a restriction.
        """
        difference = OPERATIONS["absolute_difference"](Decimal(5), Decimal(0))
        assert classify_direction(difference) is Direction.INCREASE


class TestToleranceIsExplicitAndSymmetric:
    """The one judgement, taken as a parameter so an answer can disclose it."""

    def test_a_small_change_inside_the_band_is_stable(self) -> None:
        assert classify_direction(Decimal(2), tolerance=Decimal(5)) is Direction.STABLE

    def test_the_band_is_symmetric(self) -> None:
        """A band that flattered growth would be a band that lied about decline."""
        assert classify_direction(Decimal(-2), tolerance=Decimal(5)) is Direction.STABLE
        assert classify_direction(Decimal(2), tolerance=Decimal(5)) is Direction.STABLE

    def test_the_boundary_is_inclusive_on_both_sides(self) -> None:
        assert classify_direction(Decimal(5), tolerance=Decimal(5)) is Direction.STABLE
        assert classify_direction(Decimal(-5), tolerance=Decimal(5)) is Direction.STABLE

    def test_just_outside_the_band_reads_as_movement(self) -> None:
        assert classify_direction(Decimal(6), tolerance=Decimal(5)) is Direction.INCREASE
        assert classify_direction(Decimal(-6), tolerance=Decimal(5)) is Direction.DECREASE

    def test_a_negative_tolerance_refuses(self) -> None:
        """It would mean "never stable", which zero already expresses, so it is a mistake."""
        with pytest.raises(ValueError, match="cannot be negative"):
            classify_direction(Decimal(1), tolerance=Decimal(-1))


class TestNoFloatEntersTheReading:
    """The exactness the rest of the path preserves is not broken here."""

    def test_the_function_is_exact_over_decimals(self) -> None:
        """`0.1 + 0.2` is a float trap; the same value as `Decimal` is stable and reads as one."""
        difference = Decimal("0.1") + Decimal("0.2") - Decimal("0.3")
        assert difference == Decimal(0)
        assert classify_direction(difference) is Direction.STABLE
