"""Shape drift — T081 (FR-030; SC-034).

Five drift classes, five distinct failing shapes, and every one withholds.

The comparison is an ordered tuple of (identifier, type, unit) with exact
equality, so the reordering case matters as much as the others: two schemas with
the same columns in a different order produce rows whose positions mean
something else, and a positional read of those rows is silently wrong rather
than loudly broken.
"""

from __future__ import annotations

import pytest

from analytics_query.contracts._base import ContractViolation
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.execution.adapter import ResultColumnSchema, ResultSchema
from analytics_query.execution.shape import ShapeDrift, assert_shapes_agree, describe_drift

pytestmark = pytest.mark.unit

VALIDATED = ResultSchema(
    columns=(
        ResultColumnSchema("country", "STRING", None),
        ResultColumnSchema("installs", "INT64", "users"),
    )
)


def _schema(*columns: ResultColumnSchema) -> ResultSchema:
    return ResultSchema(columns=columns)


DRIFTS = [
    (
        ShapeDrift.COLUMN_ADDED,
        _schema(
            ResultColumnSchema("country", "STRING", None),
            ResultColumnSchema("installs", "INT64", "users"),
            ResultColumnSchema("sessions", "INT64", "sessions"),
        ),
    ),
    (
        ShapeDrift.COLUMN_REMOVED,
        _schema(ResultColumnSchema("country", "STRING", None)),
    ),
    (
        ShapeDrift.COLUMN_RENAMED,
        _schema(
            ResultColumnSchema("country", "STRING", None),
            ResultColumnSchema("installs_total", "INT64", "users"),
        ),
    ),
    (
        ShapeDrift.COLUMN_RETYPED,
        _schema(
            ResultColumnSchema("country", "STRING", None),
            ResultColumnSchema("installs", "FLOAT64", "users"),
        ),
    ),
    (
        ShapeDrift.COLUMN_REUNITED,
        _schema(
            ResultColumnSchema("country", "STRING", None),
            ResultColumnSchema("installs", "INT64", "sessions"),
        ),
    ),
]


def test_identical_schemas_agree() -> None:
    """Otherwise every assertion below would pass vacuously."""
    assert_shapes_agree(VALIDATED, VALIDATED)
    assert describe_drift(VALIDATED, VALIDATED) is None


@pytest.mark.parametrize(("drift", "executed"), DRIFTS, ids=[d.value for d, _ in DRIFTS])
def test_each_drift_class_withholds(drift: ShapeDrift, executed: ResultSchema) -> None:
    with pytest.raises(ContractViolation) as caught:
        assert_shapes_agree(VALIDATED, executed)
    assert caught.value.code is AnalyticsReasonCode.RESULT_SHAPE_MISMATCH


@pytest.mark.parametrize(("drift", "executed"), DRIFTS, ids=[d.value for d, _ in DRIFTS])
def test_each_drift_class_is_classified(drift: ShapeDrift, executed: ResultSchema) -> None:
    assert describe_drift(VALIDATED, executed) is drift


def test_all_five_classes_are_covered() -> None:
    assert {d for d, _ in DRIFTS} == set(ShapeDrift)


def test_reordering_columns_is_drift() -> None:
    """Same columns, different positions: a positional read is silently wrong."""
    reordered = _schema(
        ResultColumnSchema("installs", "INT64", "users"),
        ResultColumnSchema("country", "STRING", None),
    )
    with pytest.raises(ContractViolation):
        assert_shapes_agree(VALIDATED, reordered)


def test_there_is_no_tolerance_parameter() -> None:
    """No margin to widen, and none to get wrong."""
    import inspect

    assert list(inspect.signature(assert_shapes_agree).parameters) == ["validated", "executed"]


def test_the_mismatch_message_names_no_column() -> None:
    """A shape mismatch must not become the disclosure a refusal avoided."""
    with pytest.raises(ContractViolation) as caught:
        assert_shapes_agree(VALIDATED, DRIFTS[0][1])
    detail = caught.value.detail.lower()
    for identifier in ("country", "installs", "sessions"):
        assert identifier not in detail


def test_an_empty_schema_differs_from_a_populated_one() -> None:
    with pytest.raises(ContractViolation):
        assert_shapes_agree(VALIDATED, ResultSchema())
