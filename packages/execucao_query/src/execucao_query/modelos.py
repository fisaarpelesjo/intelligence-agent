from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Protocol

from catalogo_semantico import AccessDecision


class Operator(StrEnum):
    EQ = "eq"
    NE = "ne"
    IN = "in"
    NOT_IN = "not_in"


class ExecutionReasonCode(StrEnum):
    NOT_AUTHORIZED = "not_authorized"
    OPERATOR_NOT_ALLOWED = "operator_not_allowed"
    DIMENSION_NOT_ALLOWED = "dimension_not_allowed"
    COST_CEILING_EXCEEDED = "cost_ceiling_exceeded"
    ROW_CEILING_EXCEEDED = "row_ceiling_exceeded"
    DATA_SOURCE_UNAVAILABLE = "data_source_unavailable"


@dataclass(frozen=True)
class QueryFilter:
    dimension_id: str
    operator: Operator
    values: tuple[str, ...]


@dataclass(frozen=True)
class QueryRequest:
    decision: AccessDecision
    period_start: date
    period_end: date
    filter: QueryFilter | None = None


@dataclass(frozen=True)
class CostEstimate:
    estimated_bytes: int
    estimated_rows: int


@dataclass(frozen=True)
class QueryResult:
    value: float
    unit: str
    source_view: str
    rows_returned: int


@dataclass(frozen=True)
class ExecutionOutcome:
    success: bool
    reason_code: ExecutionReasonCode | None = None
    result: QueryResult | None = None


class DataSource(Protocol):
    def dry_run(self, request: QueryRequest) -> CostEstimate: ...

    def execute(self, request: QueryRequest) -> QueryResult: ...
