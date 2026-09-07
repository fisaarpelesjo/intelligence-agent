"""Fake warehouse adapter — T044 (SC-003).

Enables every execution test without a credential, and — more importantly —
**counts calls**. The authorization-before-cost test asserts this counter is zero
for an unauthorized principal, which is how "no cost incurred" becomes an
observation rather than a claim (`FR-014`, `SC-009`).

Test package only. Nothing under `src/` may reference it, asserted by the
fixture-containment scan.
"""

from __future__ import annotations

from analytics_query.execution.adapter import (
    DryRunResult,
    ExecutionLimits,
    ExecutionOutcome,
    ExecutionResult,
    RenderedQuery,
    ResultSchema,
    ScalarValue,
)

__all__ = ["FakeWarehouseAdapter"]


class FakeWarehouseAdapter:
    """A programmable ``WarehouseAdapter`` that records what it was asked to do."""

    def __init__(
        self,
        *,
        estimated_bytes: int = 1_000,
        actual_bytes: int = 1_000,
        schema: ResultSchema | None = None,
        execution_schema: ResultSchema | None = None,
        rows: tuple[tuple[ScalarValue, ...], ...] = (),
        projected_rows: int | None = None,
        outcome: ExecutionOutcome = ExecutionOutcome.COMPLETED,
        dry_run_raises: Exception | None = None,
        execute_raises: Exception | None = None,
    ) -> None:
        self.dry_run_calls = 0
        self.execute_calls = 0
        self.last_limits: ExecutionLimits | None = None
        self.last_query: RenderedQuery | None = None

        self._estimated_bytes = estimated_bytes
        self._actual_bytes = actual_bytes
        self._schema = schema or ResultSchema()
        #: Defaults to the dry-run schema. Setting it separately is how a
        #: shape-drift test makes execution disagree with validation.
        self._execution_schema = execution_schema
        self._rows = rows
        self._projected_rows = projected_rows
        self._outcome = outcome
        self._dry_run_raises = dry_run_raises
        self._execute_raises = execute_raises

    @property
    def total_calls(self) -> int:
        """Every warehouse interaction. Zero is the assertion that matters."""
        return self.dry_run_calls + self.execute_calls

    def dry_run(self, query: RenderedQuery) -> DryRunResult:
        self.dry_run_calls += 1
        self.last_query = query
        if self._dry_run_raises is not None:
            raise self._dry_run_raises
        return DryRunResult(
            estimated_bytes=self._estimated_bytes,
            schema=self._schema,
            projected_rows=self._projected_rows,
        )

    def execute(self, query: RenderedQuery, limits: ExecutionLimits) -> ExecutionResult:
        self.execute_calls += 1
        self.last_query = query
        self.last_limits = limits
        if self._execute_raises is not None:
            raise self._execute_raises
        return ExecutionResult(
            schema=self._execution_schema or self._schema,
            rows=self._rows,
            actual_bytes=self._actual_bytes,
            job_ref="fake-job-1",
            outcome=self._outcome,
        )
