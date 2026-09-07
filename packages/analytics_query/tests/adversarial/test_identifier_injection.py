"""Identifier-shape adversarial tests — T057 (FR-001, FR-003; SC-001).

An identifier is the one part of a request that legitimately reaches the emitted
text, so a predicate-shaped identifier is the obvious attack. It is rejected at
**parse**, before any catalog lookup — which matters twice over: the compiler
never sees it, and a probe learns nothing about what the catalog contains,
because rejection happens before anything is looked up (`FR-011`, `SC-009`).
"""

from __future__ import annotations

from datetime import date

import pytest

from analytics_query.contracts._base import ContractViolation, build
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.contracts.request import AnalyticsQuery, DateRange

pytestmark = pytest.mark.adversarial

JULY = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))

HOSTILE = [
    "installs; DROP TABLE x",
    "installs OR 1=1",
    "installs--",
    "installs/*c*/",
    "installs)",
    "(installs",
    "installs'",
    'installs"',
    "installs`",
    "semantic.installs",
    "raw.events",
    "installs UNION SELECT 1",
    "installs\nsessions",
    "installs sessions",
    "*",
    "1=1",
    "",
    "INSTALLS",
]


@pytest.mark.parametrize("identifier", HOSTILE)
@pytest.mark.parametrize("field", ["metrics", "dimensions", "sources"])
def test_a_predicate_shaped_identifier_is_refused(identifier: str, field: str) -> None:
    payload: dict[str, object] = {"metrics": ("installs",), "date_range": JULY}
    payload[field] = (identifier,)
    with pytest.raises(ContractViolation) as caught:
        build(AnalyticsQuery, **payload)
    assert caught.value.code is AnalyticsReasonCode.REQUEST_MALFORMED


def test_a_hostile_filter_dimension_is_refused() -> None:
    from analytics_query.contracts.operators import GovernedOperator
    from analytics_query.contracts.request import GovernedFilter

    with pytest.raises(ContractViolation):
        build(
            GovernedFilter,
            dimension="country; DROP TABLE x",
            operator=GovernedOperator.EQ,
            values=("BR",),
        )


def test_rejection_precedes_any_catalog_lookup() -> None:
    """No catalog is supplied, and refusal happens anyway.

    Constructing the request performs the check, so there is no code path in
    which a hostile identifier is carried as far as a lookup.
    """
    with pytest.raises(ContractViolation):
        build(AnalyticsQuery, metrics=("installs; --",), date_range=JULY)
