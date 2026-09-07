"""The exhaustive operator x dimension-type matrix — T032 (FR-005; SC-001).

All 15 pairings are asserted **individually**, not by iterating the table under
test. Iterating it would only prove the table is self-consistent; naming each
pairing proves the table says what the contract says, and a silent edit to any
single entry fails here.
"""

from __future__ import annotations

import pytest

from analytics_query.contracts.matrix import (
    OPERATOR_MATRIX,
    dimension_type_for,
    is_permitted,
    refusal_for,
)
from analytics_query.contracts.operators import (
    DIMENSION_TYPE_ASSIGNMENTS,
    DimensionType,
    GovernedOperator,
    load_dimension_types,
    load_operators,
)
from analytics_query.contracts.reason_codes import AnalyticsReasonCode

pytestmark = pytest.mark.contract

ENUM = DimensionType.ENUMERATED_TEXT
OPEN = DimensionType.OPEN_TEXT
DATE = DimensionType.TEMPORAL_DATE


# --- all 15 pairings, one assertion each -------------------------------------


@pytest.mark.parametrize(
    ("operator", "dimension_type", "expected"),
    [
        (GovernedOperator.EQ, ENUM, True),
        (GovernedOperator.NE, ENUM, True),
        (GovernedOperator.IN, ENUM, True),
        (GovernedOperator.NOT_IN, ENUM, True),
        (GovernedOperator.BETWEEN, ENUM, False),
        (GovernedOperator.EQ, OPEN, True),
        (GovernedOperator.NE, OPEN, True),
        (GovernedOperator.IN, OPEN, True),
        (GovernedOperator.NOT_IN, OPEN, True),
        (GovernedOperator.BETWEEN, OPEN, False),
        (GovernedOperator.EQ, DATE, False),
        (GovernedOperator.NE, DATE, False),
        (GovernedOperator.IN, DATE, False),
        (GovernedOperator.NOT_IN, DATE, False),
        (GovernedOperator.BETWEEN, DATE, False),
    ],
    ids=lambda value: value.value if hasattr(value, "value") else str(value),
)
def test_each_pairing_is_exactly_as_contracted(
    operator: GovernedOperator, dimension_type: DimensionType, expected: bool
) -> None:
    assert is_permitted(operator, dimension_type) is expected


def test_the_matrix_is_complete_and_has_no_extra_entries() -> None:
    """5 operators x 3 types = 15. Nothing implied by omission."""
    expected = {(op, dt) for op in GovernedOperator for dt in DimensionType}
    assert set(OPERATOR_MATRIX) == expected
    assert len(OPERATOR_MATRIX) == 15


def test_adding_a_type_without_a_matrix_entry_would_fail() -> None:
    """Deny-by-default: an unlisted pairing is never permission."""
    assert is_permitted(GovernedOperator.EQ, "not_a_type") is False  # pyright: ignore[reportArgumentType]


# --- refusal codes -----------------------------------------------------------


def test_an_unmapped_dimension_fails_closed() -> None:
    verdict = refusal_for(GovernedOperator.EQ, "no_such_dimension")
    assert verdict.permitted is False
    assert verdict.code is AnalyticsReasonCode.DIMENSION_TYPE_UNDECLARED


def test_a_temporal_dimension_refuses_with_its_own_code() -> None:
    """Specific beats generic: the caller learns the dimension is closed to filters."""
    for operator in GovernedOperator:
        verdict = refusal_for(operator, "date")
        assert verdict.permitted is False
        assert verdict.code is AnalyticsReasonCode.DATE_DIMENSION_NOT_FILTERABLE


def test_a_denied_pairing_on_a_filterable_type_names_the_operator() -> None:
    verdict = refusal_for(GovernedOperator.BETWEEN, "country")
    assert verdict.permitted is False
    assert verdict.code is AnalyticsReasonCode.OPERATOR_NOT_APPLICABLE


def test_a_permitted_pairing_carries_no_code() -> None:
    verdict = refusal_for(GovernedOperator.IN, "country")
    assert verdict.permitted is True
    assert verdict.code is None


# --- the enums agree with the governed content -------------------------------


def test_the_operator_enum_matches_the_governed_allowlist() -> None:
    authored = load_operators()
    assert set(authored) == {op.value for op in GovernedOperator}
    for forbidden in ("like", "regex", "is_null", "is_not_null", "gt", "lt"):
        assert forbidden not in authored


def test_the_type_vocabulary_and_assignments_match_the_governed_content() -> None:
    types, assignments = load_dimension_types()
    assert set(types) == {dt.value for dt in DimensionType}
    assert assignments == {k: v.value for k, v in DIMENSION_TYPE_ASSIGNMENTS.items()}


def test_every_catalog_dimension_has_a_declared_type() -> None:
    """All six `001` dimensions, mapped exactly as `BO-6` records."""
    assert DIMENSION_TYPE_ASSIGNMENTS == {
        "platform": ENUM,
        "product": ENUM,
        "store": ENUM,
        "country": OPEN,
        "app_version": OPEN,
        "date": DATE,
    }
    for dimension in ("platform", "product", "store", "country", "app_version", "date"):
        assert dimension_type_for(dimension) is not None


def test_app_version_is_unordered_by_deliberate_choice() -> None:
    """`001` declares no ordering, so this feature must not invent one (`BO-6`)."""
    types, _ = load_dimension_types()
    assert dimension_type_for("app_version") is OPEN
    assert types[OPEN.value] is False
