"""Dimensional breakdown — T105 (FR-005, FR-006; SC-005).

One row per dimension-value combination, with the dimensional coverage stated in
provenance.

Coverage is the part that is easy to skip and expensive to omit. A breakdown
that returns three countries when the metric covers five looks complete — there
is no gap on the screen. Stating which dimension values the result actually
covers is what lets a reader notice the other two are missing.

Runs through the real gates: `001` decides whether the requested dimensions are
allowed for this metric-source pair, and this feature only reports what came
back.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from semantic_catalog.contracts.audit_event import PrincipalType
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode
from semantic_catalog.validation.pipeline import evaluate

from analytics_query.contracts._base import ContractViolation, build
from analytics_query.contracts.operators import GovernedOperator
from analytics_query.contracts.request import AnalyticsQuery, DateRange, GovernedFilter
from analytics_query.contracts.result import ResultColumn
from analytics_query.decision.bridge import evaluate_fully, is_permissive
from analytics_query.execution.adapter import (
    ExecutionOutcome,
    ExecutionResult,
    ResultColumnSchema,
    ResultSchema,
)
from analytics_query.results.assemble import assemble_result

from ..fixtures.catalog.bundle import (
    ALLOWED_METRIC,
    ALLOWED_SOURCE,
    ON,
    SCOPE,
    STANDARD_ACCESS,
    bundle,
    snapshot,
)

pytestmark = pytest.mark.integration

JULY = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))

#: `country` is declared in the fixture metric's allowed dimensions.
BREAKDOWN = "country"

SCHEMA = ResultSchema(
    columns=(
        ResultColumnSchema(BREAKDOWN, "STRING", None),
        ResultColumnSchema(ALLOWED_METRIC, "INT64", "sessions"),
    )
)
COLUMNS = (
    ResultColumn(identifier=BREAKDOWN, unit="label", is_metric=False),
    ResultColumn(identifier=ALLOWED_METRIC, unit="sessions", is_metric=True),
)


def _request(**overrides: object) -> AnalyticsQuery:
    payload: dict[str, object] = {
        "metrics": (ALLOWED_METRIC,),
        "sources": (ALLOWED_SOURCE,),
        "dimensions": (BREAKDOWN,),
        "date_range": JULY,
    }
    payload.update(overrides)
    return build(AnalyticsQuery, **payload)


def _decide(request: AnalyticsQuery):
    return evaluate_fully(
        request,
        evaluate=evaluate,
        bundle=bundle(),
        snapshot=snapshot(),
        principal_type=PrincipalType.USER,
        authorization_scope=SCOPE,
        requester_access=STANDARD_ACCESS,
        on=ON,
    )


# --- the governed breakdown --------------------------------------------------


def test_a_declared_dimension_is_allowed_by_the_real_gates() -> None:
    decision = _decide(_request())
    assert decision.outcome is Outcome.ALLOW
    assert is_permissive(decision)


def test_an_undeclared_dimension_is_refused_upstream() -> None:
    """`001` owns the combination gate; this feature only reports the verdict."""
    decision = _decide(_request(dimensions=("store",)))
    assert decision.outcome is Outcome.DENY
    assert decision.reason_code in {
        ReasonCode.DIMENSION_NOT_ALLOWED_FOR_METRIC,
        ReasonCode.DIMENSION_NOT_GOVERNED,
        ReasonCode.DIMENSION_NOT_APPLICABLE_TO_SOURCE,
    }
    assert not is_permissive(decision)


# --- one row per combination -------------------------------------------------


def test_one_row_per_dimension_value() -> None:
    execution = ExecutionResult(
        schema=SCHEMA,
        rows=(("BR", Decimal("300")), ("AR", Decimal("120")), ("CL", Decimal("55"))),
        actual_bytes=900,
        job_ref="j-1",
        outcome=ExecutionOutcome.COMPLETED,
    )
    result = assemble_result(execution, columns=COLUMNS)
    assert len(result.rows) == 3
    # One label (the country) and one figure per row.
    assert [row.labels for row in result.rows] == [("BR",), ("AR",), ("CL",)]
    assert [row.cells[0].value for row in result.rows] == [
        Decimal("300"),
        Decimal("120"),
        Decimal("55"),
    ]


def test_dimensional_coverage_is_stated_rather_than_implied() -> None:
    """A breakdown missing two countries has no gap on the screen."""
    from datetime import UTC, datetime

    from analytics_query.contracts.provenance import CostProvenance
    from analytics_query.contracts.result_provenance import ResultProvenance, SourceUpdate

    provenance = build(
        ResultProvenance,
        contributing_sources=(ALLOWED_SOURCE,),
        resolved_metric_versions=(f"{ALLOWED_METRIC}@1",),
        data_revisions=(),
        data_as_of=datetime(2026, 8, 11, tzinfo=UTC),
        source_updates=(
            SourceUpdate(
                source_id=ALLOWED_SOURCE, last_updated_at=datetime(2026, 8, 11, tzinfo=UTC)
            ),
        ),
        dimensional_coverage=(BREAKDOWN,),
        limitations=(),
        cost=CostProvenance(dry_run_bytes=1000, actual_bytes=900, maximum_bytes_billed=1_000_000),
        execution_identifiers=("j-1",),
        policy_version="p-fixture",
        catalog_release_id=bundle().release_id,
    )
    assert provenance.dimensional_coverage == (BREAKDOWN,)


# --- filters on the breakdown dimension (FR-005, FR-006) --------------------


def test_a_governed_filter_on_the_breakdown_dimension_is_accepted() -> None:
    request = _request(
        filters=(
            build(
                GovernedFilter,
                dimension=BREAKDOWN,
                operator=GovernedOperator.IN,
                values=("BR", "AR"),
            ),
        )
    )
    assert request.filters[0].values == ("BR", "AR")


def test_an_ungoverned_operator_never_reaches_the_request() -> None:
    with pytest.raises(ContractViolation):
        build(
            GovernedFilter,
            dimension=BREAKDOWN,
            operator="like",  # type: ignore[arg-type]
            values=("BR%",),
        )


def test_an_empty_filter_value_set_is_refused() -> None:
    """Never read as "no filter" or as "match nothing"."""
    with pytest.raises(ContractViolation):
        build(GovernedFilter, dimension=BREAKDOWN, operator=GovernedOperator.IN, values=())


def test_a_filter_on_the_date_dimension_is_refused() -> None:
    """`date_range` is the sole temporal bound."""
    from analytics_query.contracts.date_filter import reject_date_filters

    refusal = reject_date_filters(
        (
            build(
                GovernedFilter,
                dimension="date",
                operator=GovernedOperator.EQ,
                values=("2026-07-01",),
            ),
        )
    )
    assert refusal.refused
    assert refusal.code is not None
    assert refusal.code.value == "DATE_DIMENSION_NOT_FILTERABLE"
