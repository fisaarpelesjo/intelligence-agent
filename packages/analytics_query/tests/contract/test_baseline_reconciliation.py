"""Baseline deviation check — T120 (`BD-1`).

`docs/intelligence-agent.yaml` claimed a request surface wider than the one
`FR-001` approves: `comparison`, `order_by` and `limit` were listed as optional
fields of `AnalyticsQuery`. ADR 0008 records why they stay out; **this check
asserts the baseline no longer says otherwise.**

The ADR alone is not enough, and that is the precedent `001`'s `T111` set: an
ADR records *why* a divergence exists, and the edit stops it resurfacing in
every future feature that reads the baseline as fact. A reader who finds
`comparison` listed here will build against it.

It asserts the **corrected state**, not the correction event, so it keeps
working as a regression guard: if somebody re-adds `limit` to `optional_fields`,
this fails rather than the conflict quietly returning.

Two things it deliberately does not do. It does not check the rest of the
baseline — unrelated architecture is out of scope. And it never treats the
baseline as authoritative: where the two disagree, the spec and the implemented
contract govern, and the YAML is what gets fixed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml

import analytics_query
from analytics_query.contracts.request import AnalyticsQuery

pytestmark = pytest.mark.contract

REPO = Path(analytics_query.__file__).resolve().parents[4]
BASELINE = REPO / "docs" / "intelligence-agent.yaml"
ADR_0008 = REPO / "docs" / "adr" / "0008-bd1-request-surface-deviation.md"

#: `BD-1`: named in the baseline, absent from the contract by decision.
DELIBERATELY_ABSENT = ("comparison", "order_by", "limit")


def _analytics_query_section() -> dict[str, Any]:
    document = cast("dict[str, Any]", yaml.safe_load(BASELINE.read_text(encoding="utf-8")))
    section = document.get("analytics_query")
    assert isinstance(section, dict), "the baseline must declare an analytics_query section"
    return cast("dict[str, Any]", section)


SECTION = _analytics_query_section()


def test_the_check_reads_a_real_baseline() -> None:
    """A check over a missing file would report zero conflicts."""
    assert BASELINE.is_file()
    assert SECTION.get("input_contract") == "AnalyticsQuery"


# --- BD-1: the corrected state ----------------------------------------------


@pytest.mark.parametrize("field", DELIBERATELY_ABSENT)
def test_a_deliberately_absent_field_is_not_listed_as_optional(field: str) -> None:
    assert field not in SECTION.get("optional_fields", []), (
        f"the baseline still offers {field!r} as an optional request field"
    )


@pytest.mark.parametrize("field", DELIBERATELY_ABSENT)
def test_a_deliberately_absent_field_is_named_as_absent(field: str) -> None:
    """Recorded, not merely deleted — silence would read as an oversight."""
    assert field in SECTION.get("absent_fields", []), f"{field!r} is dropped without being recorded"


@pytest.mark.parametrize("field", DELIBERATELY_ABSENT)
def test_a_deliberately_absent_field_is_not_in_the_contract(field: str) -> None:
    """The other half of the reconciliation: the code agrees with the baseline."""
    assert field not in AnalyticsQuery.model_fields


def test_the_baseline_field_lists_match_the_implemented_contract() -> None:
    """Required plus optional is exactly the request surface."""
    declared = set(SECTION.get("required_fields", [])) | set(SECTION.get("optional_fields", []))
    assert declared == set(AnalyticsQuery.model_fields), (
        f"baseline declares {sorted(declared)}; contract has {sorted(AnalyticsQuery.model_fields)}"
    )


def test_the_required_fields_are_the_ones_the_contract_requires() -> None:
    required = {name for name, field in AnalyticsQuery.model_fields.items() if field.is_required()}
    assert set(SECTION.get("required_fields", [])) == required


def test_the_comparison_allowlist_is_gone_with_the_field() -> None:
    """An allowlist for a field that cannot be supplied describes nothing.

    Worse, a reader would take its presence as evidence the field exists.
    """
    assert "allowed_comparisons" not in SECTION


# --- the temporal statement -------------------------------------------------


def test_the_baseline_no_longer_claims_date_filters_are_required() -> None:
    """The old key asserted the opposite of the implemented behaviour.

    A filter targeting the date dimension is refused; the period is set solely
    by the required `date_range`.
    """
    validation = cast("dict[str, Any]", SECTION.get("validation", {}))
    assert "temporal_filter_required" not in validation
    assert validation.get("temporal_bound_required") is True


# --- the reconciliation is attributable -------------------------------------


def test_the_reconciliation_references_its_adr() -> None:
    """A future reader must be able to find why, not just what."""
    text = BASELINE.read_text(encoding="utf-8")
    assert "ADR 0008" in text
    assert "T120" in text


def test_the_adr_recorded_the_deferral_this_task_discharges() -> None:
    adr = ADR_0008.read_text(encoding="utf-8")
    assert "T120" in adr
    assert "does not edit" in adr, "ADR 0008 must still disclaim editing the baseline itself"


# --- the SQL prohibitions are untouched by this reconciliation --------------


@pytest.mark.parametrize(
    "flag",
    [
        "multiple_statements_allowed",
        "ddl_allowed",
        "dml_allowed",
        "raw_dataset_allowed",
        "core_dataset_allowed",
    ],
)
def test_the_structural_prohibitions_remain_false(flag: str) -> None:
    """Reconciling one statement must not loosen a neighbouring one."""
    validation = cast("dict[str, Any]", SECTION.get("validation", {}))
    assert validation.get(flag) is False


def test_model_generated_sql_remains_forbidden() -> None:
    assert SECTION.get("model_generated_sql") is False
