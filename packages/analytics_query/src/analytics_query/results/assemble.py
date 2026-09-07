"""Result assembly — T091 (FR-037, FR-038; SC-006).

Values are **copied**. No rounding, scaling, interpolation, extrapolation,
imputation or recomputation happens anywhere in this module, and the returned
figures are byte-identical to what the adapter handed back.

That is a stronger constraint than it sounds, because every one of those
transformations has a plausible motive. Rounding makes a table read better.
Scaling puts two metrics on one axis. Imputation fills a gap the reader would
otherwise ask about. Each produces a number the warehouse never computed, and
the caller cannot tell which figures were touched.

So the only arithmetic in this file is none. `Decimal` values pass through
unchanged, and the one conversion — an `int` staying an `int` — is not a
conversion at all.

Columns carry their **governed identifier and declared unit** from the catalog,
never a label derived here. A unit invented at assembly time would describe the
figure wrongly while looking authoritative.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from ..contracts._base import ContractViolation
from ..contracts.reason_codes import AnalyticsReasonCode
from ..contracts.result import (
    AnalyticsResult,
    Completeness,
    ResultCell,
    ResultColumn,
    ResultRow,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..execution.adapter import ExecutionResult, ScalarValue

__all__ = ["assemble_result", "to_cell"]


def to_cell(value: ScalarValue) -> ResultCell:
    """Wrap one warehouse value without touching it.

    ``float`` is refused rather than converted. A float that reached here has
    already lost precision, and turning it into a ``Decimal`` would preserve the
    error while making it look exact — which is worse than refusing, because it
    is undetectable downstream (`SC-006`).
    """
    if value is None:
        return ResultCell(value=None)
    if isinstance(value, bool):
        raise ContractViolation(
            AnalyticsReasonCode.RESULT_SHAPE_MISMATCH,
            "a boolean is not a governed metric value",
        )
    if isinstance(value, Decimal | int):
        return ResultCell(value=value)
    if isinstance(value, float):
        raise ContractViolation(
            AnalyticsReasonCode.RESULT_SHAPE_MISMATCH,
            "the warehouse returned an inexact numeric type for a governed metric value",
        )
    raise ContractViolation(
        AnalyticsReasonCode.RESULT_SHAPE_MISMATCH,
        "the warehouse returned a non-numeric value in a metric column",
    )


def assemble_result(
    execution: ExecutionResult,
    *,
    columns: tuple[ResultColumn, ...],
) -> AnalyticsResult:
    """Build the governed result from the adapter response.

    ``columns`` come from the catalog — their identifiers and units are governed
    content, and this function only checks that the execution produced as many
    columns as were declared. It does not name them itself.

    A zero-row execution assembles as ``Completeness.EMPTY``. That is a genuine
    absence of data, and it is deliberately a *different* state from a
    governance-withheld result (`FR-040`, handled in ``completeness.py``).
    """
    if len(execution.schema.columns) != len(columns):
        raise ContractViolation(
            AnalyticsReasonCode.RESULT_SHAPE_MISMATCH,
            "the executed column count differs from the governed columns",
        )

    # A dimension column carries a label; a metric column carries a figure. They
    # are split here rather than coerced into one type, because `ResultCell` is
    # numeric so an exact warehouse value survives transport (`SC-006`).
    is_metric = tuple(column.is_metric for column in columns)

    rows: list[ResultRow] = []
    for row in execution.rows:
        if len(row) != len(columns):
            raise ContractViolation(
                AnalyticsReasonCode.RESULT_SHAPE_MISMATCH,
                "a returned row is not as wide as the governed columns",
            )
        labels = tuple(
            _to_label(value) for value, metric in zip(row, is_metric, strict=True) if not metric
        )
        cells = tuple(
            to_cell(value) for value, metric in zip(row, is_metric, strict=True) if metric
        )
        rows.append(ResultRow(labels=labels, cells=cells))

    return AnalyticsResult(
        columns=columns,
        rows=tuple(rows),
        completeness=Completeness.COMPLETE if rows else Completeness.EMPTY,
    )


def _to_label(value: ScalarValue) -> str:
    """A dimension value, as the warehouse supplied it.

    Rendered as text without reformatting: a label that arrived as ``01`` must
    not become ``1``, because the two are different dimension values.
    """
    if value is None:
        raise ContractViolation(
            AnalyticsReasonCode.RESULT_SHAPE_MISMATCH,
            "a dimension column returned no value; a breakdown row must name its cohort",
        )
    return value if isinstance(value, str) else str(value)
