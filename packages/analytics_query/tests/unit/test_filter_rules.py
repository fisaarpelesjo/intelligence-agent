"""Filter rules — T033 (FR-006; SC-001).

Null, arity, type, empty-list, duplicate, range-order and the date-dimension
refusal. Each rule refuses with **its own code**, because a caller who gets a
generic error cannot tell which of seven rules they broke.

The null rule is the one worth stating plainly: a filter value may never be null,
in a scalar, in any list element, or in either `between` bound — and no
``is_null`` operator exists. Nullity is therefore not expressible as a filter at
all, which keeps SQL three-valued logic out of the governed surface entirely, so
``ne`` and ``not_in`` can never encounter a null operand and two implementations
cannot diverge on one.
"""

from __future__ import annotations

import pytest

from analytics_query.contracts._base import ContractViolation, build
from analytics_query.contracts.date_filter import (
    is_date_dimension,
    reject_date_filters,
)
from analytics_query.contracts.filters import validate_filter, validate_filters
from analytics_query.contracts.operators import GovernedOperator
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.contracts.request import GovernedFilter

pytestmark = pytest.mark.unit

PERMITTED = {"platform": ["android", "ios", "web"], "store": ["google_play"]}


def _filter(operator: str, values: tuple[str, ...], dimension: str = "country") -> GovernedFilter:
    return build(
        GovernedFilter,
        dimension=dimension,
        operator=GovernedOperator(operator),
        values=values,
    )


# --- nulls: forbidden everywhere ---------------------------------------------


def test_a_null_scalar_value_is_refused() -> None:
    with pytest.raises(ContractViolation) as caught:
        build(GovernedFilter, dimension="country", operator=GovernedOperator.EQ, values=None)
    assert caught.value.code is AnalyticsReasonCode.FILTER_VALUE_NULL


@pytest.mark.parametrize(
    "values",
    [
        (None,),
        ("BR", None),
        (None, "BR"),
        ("BR", None, "AR"),
    ],
)
def test_a_null_in_any_list_element_is_refused(values: tuple[object, ...]) -> None:
    with pytest.raises(ContractViolation) as caught:
        build(GovernedFilter, dimension="country", operator=GovernedOperator.IN, values=values)
    assert caught.value.code is AnalyticsReasonCode.FILTER_VALUE_NULL


def test_a_null_in_either_between_bound_is_refused() -> None:
    for values in ((None, "2026-07-31"), ("2026-07-01", None)):
        with pytest.raises(ContractViolation) as caught:
            build(
                GovernedFilter, dimension="date", operator=GovernedOperator.BETWEEN, values=values
            )
        assert caught.value.code is AnalyticsReasonCode.FILTER_VALUE_NULL


def test_no_nullity_operator_exists() -> None:
    """Nullity is not expressible as a filter in this feature at all."""
    declared = {op.value for op in GovernedOperator}
    assert "is_null" not in declared
    assert "is_not_null" not in declared


# --- arity -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("operator", "values"),
    [
        ("eq", ()),
        ("eq", ("a", "b")),
        ("ne", ("a", "b")),
        ("between", ("a",)),
        ("between", ("a", "b", "c")),
    ],
)
def test_arity_violations_are_refused(operator: str, values: tuple[str, ...]) -> None:
    with pytest.raises(ContractViolation) as caught:
        _filter(operator, values)
    assert caught.value.code in {
        AnalyticsReasonCode.REQUEST_MALFORMED,
        AnalyticsReasonCode.FILTER_VALUE_SET_EMPTY,
    }


def test_in_and_not_in_accept_one_or_more() -> None:
    assert len(_filter("in", ("BR",)).values) == 1
    assert len(_filter("not_in", ("BR", "AR")).values) == 2


# --- empty, duplicate, range order -------------------------------------------


@pytest.mark.parametrize("operator", ["eq", "ne", "in", "not_in", "between"])
def test_an_empty_value_set_is_refused(operator: str) -> None:
    """Never read as 'no filter' and never as 'match nothing'."""
    with pytest.raises(ContractViolation) as caught:
        _filter(operator, ())
    assert caught.value.code is AnalyticsReasonCode.FILTER_VALUE_SET_EMPTY


def test_duplicate_values_are_refused_not_de_duplicated() -> None:
    with pytest.raises(ContractViolation) as caught:
        _filter("in", ("BR", "BR"))
    assert caught.value.code is AnalyticsReasonCode.REQUEST_MALFORMED


def test_a_reversed_between_range_is_refused_and_never_swapped() -> None:
    with pytest.raises(ContractViolation) as caught:
        _filter("between", ("2026-07-31", "2026-07-01"))
    assert caught.value.code is AnalyticsReasonCode.FILTER_RANGE_INVALID


def test_equal_between_bounds_are_structurally_valid() -> None:
    """A single-point range is a legitimate ask, not a malformed one.

    It still has no permitted pairing (§4.3), but that refusal comes from the
    matrix, not from the range-order rule — the two must not be conflated.
    """
    built = _filter("between", ("2026-07-01", "2026-07-01"), dimension="country")
    assert built.values == ("2026-07-01", "2026-07-01")
    # Structurally accepted, then refused by the matrix — a different rule.
    verdict = validate_filter(built)
    assert verdict.permitted is False
    assert verdict.code is AnalyticsReasonCode.OPERATOR_NOT_APPLICABLE


# --- the date dimension ------------------------------------------------------


def test_every_filter_on_the_date_dimension_is_refused() -> None:
    """`date_range` is the sole temporal bound; a filter never sets a second one."""
    assert is_date_dimension("date")
    for operator in ("eq", "ne", "in", "not_in"):
        refusal = reject_date_filters([_filter(operator, ("2026-07-01",), dimension="date")])
        assert refusal.refused is True
        assert refusal.code is AnalyticsReasonCode.DATE_DIMENSION_NOT_FILTERABLE
        assert refusal.dimension == "date"


def test_a_non_temporal_dimension_is_not_refused_by_the_date_rule() -> None:
    assert reject_date_filters([_filter("eq", ("BR",))]).refused is False


def test_the_date_dimension_remains_valid_as_a_breakdown() -> None:
    """Only filtering is closed. `date` is still observable in a result."""
    assert is_date_dimension("date")
    assert reject_date_filters([]).refused is False


def test_validate_filter_refuses_a_date_filter_with_the_specific_code() -> None:
    verdict = validate_filter(_filter("eq", ("2026-07-01",), dimension="date"))
    assert verdict.permitted is False
    assert verdict.code is AnalyticsReasonCode.DATE_DIMENSION_NOT_FILTERABLE


# --- type-dependent validation ----------------------------------------------


def test_an_enumerated_dimension_validates_membership() -> None:
    ok = validate_filter(_filter("eq", ("android",), dimension="platform"), PERMITTED)
    assert ok.permitted is True

    bad = validate_filter(_filter("eq", ("symbian",), dimension="platform"), PERMITTED)
    assert bad.permitted is False
    assert bad.code is AnalyticsReasonCode.FILTER_VALUE_NOT_GOVERNED


def test_an_enumerated_dimension_without_a_supplied_list_fails_closed() -> None:
    """A membership check with nothing to check against always passes — so refuse."""
    verdict = validate_filter(_filter("eq", ("android",), dimension="platform"))
    assert verdict.permitted is False
    assert verdict.code is AnalyticsReasonCode.DIMENSION_TYPE_UNDECLARED


def test_an_open_dimension_validates_type_and_shape() -> None:
    """A refinement of `FR-006`, not a narrowing: there is no value set to test."""
    assert validate_filter(_filter("eq", ("BR",))).permitted is True
    assert validate_filter(_filter("in", ("BR", "AR"))).permitted is True


def test_an_unknown_dimension_fails_closed() -> None:
    verdict = validate_filter(_filter("eq", ("x",), dimension="not_governed"))
    assert verdict.permitted is False
    assert verdict.code is AnalyticsReasonCode.DIMENSION_TYPE_UNDECLARED


def test_validate_filters_returns_the_first_refusal() -> None:
    """One code to act on, and evaluation stops before a later rule discloses more."""
    verdict = validate_filters(
        [
            _filter("eq", ("2026-07-01",), dimension="date"),
            _filter("eq", ("x",), dimension="not_governed"),
        ]
    )
    assert verdict.permitted is False
    assert verdict.code is AnalyticsReasonCode.DATE_DIMENSION_NOT_FILTERABLE


def test_all_permitted_filters_pass() -> None:
    assert validate_filters([_filter("eq", ("BR",)), _filter("in", ("AR", "CL"))]).permitted is True
