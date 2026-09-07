"""The column is declared, never defaulted — `T811`, `T812`, `T813`.

**This node exists because of a published error.** MRR and Revenue were reported as
having no value, from reading only the `value` column; their numbers live in
`value_usd`. The default is what made the mistake silent, so there is no default.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from daily_reporting.contracts import ReportReasonCode, ReportRefusal
from daily_reporting.numbers.column import (
    SCHEMA_VERSION_DECLARING_THE_COLUMN,
    value_column_for,
)

pytestmark = pytest.mark.unit


def _contract(schema: object, name: str = "a_metric") -> Mapping[str, object]:
    return {"name": name, "catalog_schema_version": schema}


def test_the_column_is_read_from_the_contract_it_is_handed() -> None:
    """Handed two contracts, it answers two columns. That is the derivation."""
    at_version = SCHEMA_VERSION_DECLARING_THE_COLUMN
    assert value_column_for(_contract(at_version), version={"value_column": "value_usd"}) == (
        "value_usd"
    )
    assert value_column_for(_contract(at_version), version={"value_column": "value_brl"}) == (
        "value_brl"
    )


def test_a_metric_that_declares_nothing_is_refused_and_named() -> None:
    """**Not defaulted to `value`.** The refusal names the metric."""
    with pytest.raises(ReportRefusal) as refused:
        value_column_for(_contract(SCHEMA_VERSION_DECLARING_THE_COLUMN, "mrr"), version={})
    assert refused.value.code is ReportReasonCode.REPORT_VALUE_COLUMN_NOT_DECLARED
    assert "mrr" in refused.value.detail


def test_the_old_schema_cannot_carry_the_new_field() -> None:
    """`FR-808`. A declaration no validator knows about is a declaration nobody checked."""
    old = SCHEMA_VERSION_DECLARING_THE_COLUMN - 1
    with pytest.raises(ReportRefusal) as refused:
        value_column_for(_contract(old), version={"value_column": "value_usd"})
    assert refused.value.code is ReportReasonCode.REPORT_VALUE_COLUMN_NOT_DECLARED
    assert str(old) in refused.value.detail


def test_the_old_schema_without_the_field_refuses_too_and_says_why() -> None:
    """Two different sentences for two different problems, both refusing."""
    with pytest.raises(ReportRefusal) as refused:
        value_column_for(_contract(SCHEMA_VERSION_DECLARING_THE_COLUMN - 1), version={})
    assert refused.value.code is ReportReasonCode.REPORT_VALUE_COLUMN_NOT_DECLARED


@pytest.mark.parametrize("schema", [None, "2", 2.0])
def test_a_contract_with_no_integer_schema_version_refuses(schema: object) -> None:
    """Failing closed on a malformed document, rather than reading it optimistically."""
    with pytest.raises(ReportRefusal) as refused:
        value_column_for(_contract(schema), version={"value_column": "value"})
    assert refused.value.code is ReportReasonCode.REPORT_VALUE_COLUMN_NOT_DECLARED


@pytest.mark.parametrize("declared", ["", "   ", 7, None])
def test_an_unusable_declaration_is_not_a_declaration(declared: object) -> None:
    """Blank is not a column name, and a number is not one either."""
    with pytest.raises(ReportRefusal):
        value_column_for(
            _contract(SCHEMA_VERSION_DECLARING_THE_COLUMN),
            version={"value_column": declared},
        )
