"""The warehouse port — T037 (FR-021, FR-026; SC-003).

Two methods, and deliberately no third. The port accepts a ``RenderedQuery``
that a compiler produced; it exposes nothing that takes text, so no caller can
reach the warehouse with a string of their own. There is no ``query()``,
``run_sql()``, ``execute_many()`` or ``raw`` variant, and adding one would be
visible in this file rather than buried in an implementation.

``execute`` takes ``ExecutionLimits`` as a required argument rather than an
optional one. An unbounded execution is not expressible: to call the port at all
you must state a byte ceiling and a timeout, and the ceiling is applied **on the
job** so the warehouse cancels an overrun itself (`FR-023`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable

__all__ = [
    "DryRunResult",
    "ExecutionLimits",
    "ExecutionOutcome",
    "ExecutionResult",
    "RenderedQuery",
    "ResultColumnSchema",
    "ResultSchema",
    "ScalarValue",
    "WarehouseAdapter",
]

#: What a value crossing this boundary may be. Deliberately narrow: no
#: callables, no nested structures, nothing that could carry syntax.
#:
#: ``Decimal`` is included because it is the only exact type here. A warehouse
#: NUMERIC arriving as ``float`` would already have lost precision, and
#: `FR-038` requires values returned exactly as the warehouse supplied them —
#: so the exact type has to survive the boundary rather than be reconstructed
#: after it.
type ScalarValue = str | int | float | bool | Decimal | None


@dataclass(frozen=True, slots=True)
class RenderedQuery:
    """Compiled query text plus its bound parameters.

    ``text`` holds a fixed skeleton and governed identifiers only. **Every**
    caller-supplied value lives in ``parameters`` — the emitted-text guard
    asserts that no parameter value appears in ``text`` (`FR-002`).
    """

    text: str
    parameters: dict[str, ScalarValue] = field(default_factory=lambda: dict[str, ScalarValue]())


@dataclass(frozen=True, slots=True)
class ResultColumnSchema:
    """One column as the warehouse describes it."""

    identifier: str
    type_name: str
    unit: str | None = None


@dataclass(frozen=True, slots=True)
class ResultSchema:
    """Ordered column tuple. Compared for exact equality by shape verification."""

    columns: tuple[ResultColumnSchema, ...] = ()


@dataclass(frozen=True, slots=True)
class DryRunResult:
    """What a dry run reports. No rows — a dry run reads nothing."""

    estimated_bytes: int
    schema: ResultSchema
    projected_rows: int | None = None


@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    """Bounds applied to the job itself, not checked afterwards.

    Required, not optional. An execution with no ceiling is not expressible
    through this port.
    """

    maximum_bytes_billed: int
    timeout_seconds: int


class ExecutionOutcome(StrEnum):
    """How an execution ended, as the warehouse reports it."""

    COMPLETED = "completed"
    TIMED_OUT = "timed_out"
    CANCELLED_OVER_LIMIT = "cancelled_over_limit"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Rows as returned. Values are copied onward with no arithmetic (`FR-038`)."""

    schema: ResultSchema
    rows: tuple[tuple[ScalarValue, ...], ...]
    actual_bytes: int
    job_ref: str
    outcome: ExecutionOutcome


@runtime_checkable
class WarehouseAdapter(Protocol):
    """Read-only, bounded access to the ``semantic`` dataset.

    Implementations: ``adapters/bigquery/client.py`` (the only module permitted
    to import the BigQuery client) and a programmable fake under ``tests/``.
    """

    def dry_run(self, query: RenderedQuery) -> DryRunResult:
        """Validate and estimate without reading. Raises on an invalid query."""
        ...

    def execute(self, query: RenderedQuery, limits: ExecutionLimits) -> ExecutionResult:
        """Run under the given bounds. The warehouse enforces them."""
        ...
