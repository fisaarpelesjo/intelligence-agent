"""Request contract — T031 (FR-001, FR-007, FR-009; SC-001).

The properties that make the request surface governed rather than merely
documented: unknown fields are refused (which is how `BD-1` holds), the date
range is mandatory and never reordered, and no field exists through which query
text, an observation, a data revision or a fixture selector could arrive.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from analytics_query.contracts._base import ContractViolation, build
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.contracts.request import AnalyticsQuery, DateRange, GovernedFilter

pytestmark = pytest.mark.contract

JULY = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))


def _query(**overrides: object) -> AnalyticsQuery:
    payload: dict[str, object] = {"metrics": ("installs",), "date_range": JULY}
    payload.update(overrides)
    return build(AnalyticsQuery, **payload)


# --- BD-1: the three fields are rejected, not ignored ------------------------


@pytest.mark.parametrize("field", ["comparison", "order_by", "limit"])
def test_the_bd1_fields_are_rejected_as_unknown(field: str) -> None:
    """Never silently ignored — a caller must not believe a comparison ran."""
    with pytest.raises(ContractViolation) as caught:
        build(AnalyticsQuery, metrics=("installs",), date_range=JULY, **{field: "anything"})
    assert caught.value.code is AnalyticsReasonCode.REQUEST_MALFORMED
    assert "extra_forbidden" in caught.value.detail or "not permitted" in caught.value.detail


@pytest.mark.parametrize(
    "field",
    ["sql", "query_text", "freshness", "observations", "data_revision", "use_fixtures"],
)
def test_no_field_admits_text_observations_or_a_fixture_selector(field: str) -> None:
    """These absences are structural, not a validation rule someone maintains."""
    with pytest.raises(ContractViolation):
        build(AnalyticsQuery, metrics=("installs",), date_range=JULY, **{field: "anything"})


def test_the_declared_field_set_is_exactly_the_governed_one() -> None:
    assert set(AnalyticsQuery.model_fields) == {
        "metrics",
        "dimensions",
        "sources",
        "filters",
        "date_range",
        "as_of",
    }


# --- the date range ----------------------------------------------------------


def test_the_date_range_is_mandatory() -> None:
    with pytest.raises(ContractViolation):
        build(AnalyticsQuery, metrics=("installs",))


def test_a_reversed_range_is_refused_and_never_swapped() -> None:
    with pytest.raises(ContractViolation) as caught:
        build(DateRange, start=date(2026, 7, 31), end=date(2026, 7, 1))
    assert caught.value.code is AnalyticsReasonCode.DATE_RANGE_INVALID


def test_a_single_day_range_is_valid() -> None:
    same = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 1))
    assert same.days == 1


def test_range_length_is_inclusive() -> None:
    assert JULY.days == 31


# --- identifiers -------------------------------------------------------------


@pytest.mark.parametrize(
    "identifier",
    ["Installs", "installs; DROP TABLE x", "installs--", "in stalls", "", "installs'"],
)
def test_predicate_shaped_identifiers_die_at_parse(identifier: str) -> None:
    """Rejected before any catalog lookup, so the compiler's inputs stay boring."""
    with pytest.raises(ContractViolation):
        _query(metrics=(identifier,))


def test_duplicate_identifiers_are_refused() -> None:
    with pytest.raises(ContractViolation) as caught:
        _query(metrics=("installs", "installs"))
    assert caught.value.code is AnalyticsReasonCode.REQUEST_MALFORMED


# --- immutability and determinism -------------------------------------------


def test_the_request_is_frozen() -> None:
    query = _query()
    with pytest.raises(ValidationError):
        query.metrics = ("sessions",)  # pyright: ignore[reportAttributeAccessIssue]


def test_serialisation_is_deterministic() -> None:
    """The same request serialises to the same bytes, every time."""
    query = _query(dimensions=("country",))
    assert query.model_dump_json() == query.model_dump_json()


def test_a_well_formed_request_is_accepted() -> None:
    query = _query(
        dimensions=("country", "platform"),
        sources=("google_play",),
        filters=(build(GovernedFilter, dimension="country", operator="eq", values=("BR",)),),
    )
    assert query.metrics == ("installs",)
    assert query.date_range.days == 31
