"""Absent is not zero, measured against the READER — `T822`.

## Why this file exists instead of the fixture that was here before

`T822` was marked on a node that built `Reading(...)` by hand and asserted the report
carried the zero. **`Reading(...)` was constructed only in tests** — nothing in the
repository took a view row to a reading, so the seam where the zero rule has to live did
not exist as code, and the mark was green over a fixture.

**And the uncommitted script that composed the real message had exactly the defect.** It
answered ``None`` when a numerator was falsy, and ``0`` is falsy. Measured against the view
on 2026-08-27: `Chargeback (%)` had numerator 0 over denominator 278 — a real, measured
**zero chargebacks** — and the message rendered ``-``, which reads as *we do not know*.

Every node below drives :func:`aggregate`, which is the code the report now runs.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from daily_reporting.contracts import ReportReasonCode, ReportRefusal
from daily_reporting.view.reading import aggregate, aggregation_class_of

pytestmark = pytest.mark.unit


def _ratio(numerator: object, denominator: object) -> dict[str, object]:
    return {"aggregation_class": "RATIO", "numerator": numerator, "denominator": denominator}


def _counted(value: object) -> dict[str, object]:
    return {"aggregation_class": "COUNT", "value": value}


def test_a_measured_zero_ratio_is_zero_and_not_absent() -> None:
    """**The defect, in the shape it really had.** Numerator 0 over denominator 278."""
    got = aggregate([_ratio(0, 278)], "value")
    assert got is not None, (
        "a numerator of zero came back as ABSENT; zero chargebacks is good news, and "
        "reporting it as '-' tells the reader we do not know"
    )
    assert got == Decimal(0)


def test_a_measured_zero_count_is_zero_and_not_absent() -> None:
    got = aggregate([_counted(0), _counted(0)], "value")
    assert got is not None and got == Decimal(0)


def test_a_row_with_nothing_in_the_column_is_absent() -> None:
    """The other half: **absent really is absent**, and answering zero there would invent."""
    assert aggregate([_counted(None)], "value") is None


def test_no_rows_at_all_is_absent() -> None:
    assert aggregate([], "value") is None


def test_a_ratio_over_a_zero_denominator_is_absent_rather_than_zero() -> None:
    """A rate over nothing is undefined, which is not a rate of zero over something."""
    assert aggregate([_ratio(0, 0)], "value") is None


def test_a_ratio_with_no_denominator_column_is_absent() -> None:
    assert aggregate([_ratio(5, None)], "value") is None


def test_the_ratio_divides_the_sums_rather_than_averaging_the_rows() -> None:
    """Summing the parts and dividing once is not the same as averaging per-row ratios."""
    got = aggregate([_ratio(1, 10), _ratio(9, 90)], "value")
    assert got == Decimal(10) / Decimal(100)


def test_the_column_is_a_parameter_so_the_reader_infers_nothing() -> None:
    """`FR-806`. Handed a different column it reads a different number."""
    rows = [{"aggregation_class": "COUNT", "value": 1, "value_usd": 500}]
    assert aggregate(rows, "value") == Decimal(1)
    assert aggregate(rows, "value_usd") == Decimal(500)


def test_the_class_is_read_from_the_rows() -> None:
    assert aggregation_class_of([_counted(1)]) == "COUNT"
    assert aggregation_class_of([_ratio(1, 2)]) == "RATIO"


def test_two_classes_across_one_kpi_refuses() -> None:
    """A KPI with two classes has no class, and nothing is chosen for it."""
    with pytest.raises(ReportRefusal) as refused:
        aggregate([_counted(1), _ratio(1, 2)], "value")
    assert refused.value.code is ReportReasonCode.REPORT_KPI_NOT_DERIVABLE


def test_a_class_this_reader_does_not_know_refuses() -> None:
    """Guessing between a sum and a snapshot is guessing the number."""
    with pytest.raises(ReportRefusal):
        aggregate([{"aggregation_class": "AVERAGE", "value": 1}], "value")


def test_the_falsy_trap_would_be_caught_by_these_nodes() -> None:
    """**Proof they bite**, over the exact implementation the uncommitted script had."""

    def the_defect(rows: list[dict[str, object]]) -> Decimal | None:
        numerator = rows[0]["numerator"]
        denominator = rows[0]["denominator"]
        if not numerator or not denominator:  # `0` is falsy -- this is the bug
            return None
        return Decimal(str(numerator)) / Decimal(str(denominator))

    rows = [_ratio(0, 278)]
    assert the_defect(rows) is None, "the stand-in no longer reproduces the defect"
    assert aggregate(rows, "value") == Decimal(0), (
        "the reader agrees with the defect, so these nodes would pass over it"
    )
