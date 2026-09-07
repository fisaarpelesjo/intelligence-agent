"""The analytics result — T025 (FR-024, FR-038, FR-039; SC-017).

``Completeness`` has **no** ``TRUNCATED`` member, and that absence is the
mechanism rather than a rule to remember. A row-limit breach refuses (`FR-024`);
a partial table is therefore not merely forbidden but **not constructible**, so
no code path can produce one and no reviewer has to check that none does.

Values are ``Decimal``. A warehouse figure routed through ``float`` acquires
binary-floating-point drift, and `SC-006` requires returned values to be
byte-identical to what the warehouse supplied — which ``float`` cannot promise.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import Field, model_validator

from ._base import ContractViolation, QueryModel
from .reason_codes import AnalyticsReasonCode

__all__ = ["AnalyticsResult", "Completeness", "ResultCell", "ResultColumn"]


class Completeness(StrEnum):
    """A returned result is complete for the request as asked, or genuinely empty.

    There is deliberately no ``TRUNCATED``. Truncation is not a representable
    state in this feature.
    """

    COMPLETE = "complete"
    EMPTY = "empty"


class ResultColumn(QueryModel):
    """A governed output column: its identifier, declared unit and value kind."""

    identifier: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    is_metric: bool


class ResultCell(QueryModel):
    """One value, or one explicit withholding.

    A suppressed cell is never an absent row and never a zero: both would read as
    data. It carries the reason it was withheld, so the omission is visible.
    """

    value: Decimal | int | None = None
    suppressed: bool = False
    suppression_reason: AnalyticsReasonCode | None = None

    @model_validator(mode="after")
    def _suppression_is_explicit(self) -> ResultCell:
        if self.suppressed:
            if self.value is not None:
                raise ContractViolation(
                    AnalyticsReasonCode.REQUEST_MALFORMED,
                    "a suppressed cell must carry no value",
                )
            if self.suppression_reason is None:
                raise ContractViolation(
                    AnalyticsReasonCode.REQUEST_MALFORMED,
                    "a suppressed cell must state why it was withheld",
                )
        elif self.suppression_reason is not None:
            raise ContractViolation(
                AnalyticsReasonCode.REQUEST_MALFORMED,
                "only a suppressed cell may carry a suppression reason",
            )
        return self


class ResultRow(QueryModel):
    """One row: its dimension labels, and its metric cells.

    The two are separate because they are different kinds of thing.
    ``ResultCell.value`` is ``Decimal | int | None`` so an exact warehouse figure
    survives transport (`SC-006`) — a dimension label is a string and does not
    belong in that type. Keeping labels out of the numeric cell is what lets the
    cell stay exact and lets suppression apply only where it means something: a
    country name is not a figure that can be withheld for cohort size.

    ``labels`` align positionally with the ``is_metric=False`` columns, in
    declaration order; ``cells`` align with the ``is_metric=True`` columns.
    """

    labels: tuple[str, ...] = ()
    cells: tuple[ResultCell, ...] = ()


class AnalyticsResult(QueryModel):
    """Structured tabular output with governed columns and exact values."""

    columns: tuple[ResultColumn, ...] = Field(min_length=1)
    rows: tuple[ResultRow, ...] = ()
    completeness: Completeness

    @property
    def dimension_columns(self) -> tuple[ResultColumn, ...]:
        return tuple(column for column in self.columns if not column.is_metric)

    @property
    def metric_columns(self) -> tuple[ResultColumn, ...]:
        return tuple(column for column in self.columns if column.is_metric)

    @model_validator(mode="after")
    def _rows_match_the_declared_columns(self) -> AnalyticsResult:
        labels, cells = len(self.dimension_columns), len(self.metric_columns)
        for row in self.rows:
            if len(row.labels) != labels or len(row.cells) != cells:
                raise ContractViolation(
                    AnalyticsReasonCode.RESULT_SHAPE_MISMATCH,
                    f"a row carries {len(row.labels)} labels and {len(row.cells)} cells "
                    f"against {labels} dimension and {cells} metric columns",
                )
        if self.completeness is Completeness.EMPTY and self.rows:
            raise ContractViolation(
                AnalyticsReasonCode.REQUEST_MALFORMED,
                "an empty result may not carry rows",
            )
        return self

    def all_cells(self) -> tuple[ResultCell, ...]:
        """Every metric cell, flattened. Labels are deliberately excluded.

        Suppression and completeness reason about figures, not about which
        cohort a row names.
        """
        return tuple(cell for row in self.rows for cell in row.cells)
