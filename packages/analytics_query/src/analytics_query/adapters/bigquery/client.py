"""BigQuery adapter — T046 (FR-023, FR-026, FR-027; SC-002, SC-004).

**The only module in this package permitted to import `google.cloud.bigquery`.**
A contract test asserts it, so the dependency's blast radius is this file rather
than the package (ADR 0007).

**No credential is read, stored, logged or embedded here.** The client is
injected by the deployment, which obtains it through Application Default
Credentials. There is no project id, key path or service-account literal in this
module, so there is nothing to leak — and `semantic_catalog` gains no dependency
and keeps no credential, which is why `001`'s test asserting its CLI acquires no
warehouse access keeps passing.

``maximum_bytes_billed`` is set **on the job**. The warehouse cancels an
over-limit query itself; this adapter never discovers the overrun afterwards and
never reports a bill it failed to prevent (`FR-023`, `SC-004`).
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from google.cloud import bigquery

from ...execution.adapter import (
    DryRunResult,
    ExecutionOutcome,
    ExecutionResult,
    RenderedQuery,
    ResultColumnSchema,
    ResultSchema,
    ScalarValue,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterable

    from ...execution.adapter import ExecutionLimits

__all__ = ["BigQueryAdapter"]

_SCALAR_TYPES: dict[type, str] = {
    str: "STRING",
    int: "INT64",
    float: "FLOAT64",
    bool: "BOOL",
    Decimal: "NUMERIC",
}


class BigQueryAdapter:
    """Read-only, bounded access to the ``semantic`` dataset."""

    __slots__ = ("_client",)

    def __init__(self, client: bigquery.Client) -> None:
        """Take an already-constructed client.

        Constructing one here would mean naming a project and resolving
        credentials inside the package. Injection keeps both outside it.
        """
        self._client = client

    def dry_run(self, query: RenderedQuery) -> DryRunResult:
        """Validate and estimate. ``dry_run=True`` means the warehouse reads nothing."""
        config = bigquery.QueryJobConfig(
            dry_run=True,
            use_query_cache=False,
            query_parameters=_parameters(query.parameters),
        )
        job = self._client.query(query.text, job_config=config)
        return DryRunResult(
            estimated_bytes=int(job.total_bytes_processed or 0),
            schema=_schema(getattr(job, "schema", None)),
            projected_rows=None,
        )

    def execute(self, query: RenderedQuery, limits: ExecutionLimits) -> ExecutionResult:
        """Run under bounds the warehouse itself enforces."""
        config = bigquery.QueryJobConfig(
            dry_run=False,
            # Enforced by BigQuery: a query projected to exceed this is cancelled
            # rather than run and billed.
            maximum_bytes_billed=limits.maximum_bytes_billed,
            use_query_cache=False,
            query_parameters=_parameters(query.parameters),
        )
        job = self._client.query(query.text, job_config=config)
        try:
            iterator = job.result(timeout=limits.timeout_seconds)
        except Exception as exc:
            return ExecutionResult(
                schema=ResultSchema(),
                rows=(),
                actual_bytes=int(getattr(job, "total_bytes_billed", 0) or 0),
                job_ref=_job_ref(job),
                outcome=_failure_outcome(exc),
            )

        schema = _schema(getattr(iterator, "schema", None))
        rows = tuple(
            tuple(cast("ScalarValue", value) for value in row.values())
            for row in cast("Iterable[Any]", iterator)
        )
        return ExecutionResult(
            schema=schema,
            rows=rows,
            actual_bytes=int(getattr(job, "total_bytes_billed", 0) or 0),
            job_ref=_job_ref(job),
            outcome=ExecutionOutcome.COMPLETED,
        )


def _job_ref(job: object) -> str:
    """An opaque handle. Never the query text."""
    return str(getattr(job, "job_id", "") or "")


def _failure_outcome(exc: Exception) -> ExecutionOutcome:
    """Map a client failure onto a governed outcome.

    A timeout and an over-limit cancellation are different conditions and are
    reported as such — never as an empty or zero result (`FR-025`, `SC-020`).
    """
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "timeout" in name or "timeout" in text:
        return ExecutionOutcome.TIMED_OUT
    if "bytes billed" in text or "maximum_bytes_billed" in text:
        return ExecutionOutcome.CANCELLED_OVER_LIMIT
    return ExecutionOutcome.FAILED


def _parameters(parameters: dict[str, ScalarValue]) -> list[bigquery.ScalarQueryParameter]:
    """Bind every caller value as a parameter.

    This is the point at which "values are never syntax" becomes literal: the
    value travels in the job's parameter list, not in the statement.
    """
    bound: list[bigquery.ScalarQueryParameter] = []
    for name, value in sorted(parameters.items()):
        if value is None:
            raise ValueError(f"parameter {name!r} is null; a governed filter value is never null")
        type_name = _SCALAR_TYPES.get(type(value))
        if type_name is None:
            raise TypeError(f"parameter {name!r} has ungoverned type {type(value).__name__}")
        bound.append(bigquery.ScalarQueryParameter(name, type_name, value))
    return bound


def _schema(fields: object) -> ResultSchema:
    """Read the ordered column tuple the warehouse reports."""
    if not fields:
        return ResultSchema()
    columns: list[ResultColumnSchema] = []
    for field in cast("list[Any]", fields):
        columns.append(
            ResultColumnSchema(
                identifier=str(getattr(field, "name", "")),
                type_name=str(getattr(field, "field_type", "")),
                unit=None,
            )
        )
    return ResultSchema(columns=tuple(columns))
