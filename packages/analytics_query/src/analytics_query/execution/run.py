"""Bounded read-only execution — T088 (FR-023, FR-026, FR-032; SC-002, SC-004).

The one place a warehouse read actually happens. Three properties hold here, and
each is enforced by construction rather than by sequence:

**Bounded.** ``execute`` takes ``ExecutionLimits`` as a required argument and
the limits are built from the governed policy, so an unbounded execution is not
expressible. The byte ceiling is applied *on the job*: the warehouse cancels an
overrun itself rather than this code discovering it afterwards.

**Preceded by a dry run.** This function takes a ``ValidatedPlan``, whose only
constructor is ``perform_dry_run``. There is no argument shape through which a
raw query reaches the adapter.

**Nothing partial escapes.** A cancelled, timed-out or failed execution returns
no rows at all — there is no field in which partial output could survive. Its
real cost is still recorded, because the money was spent whether or not an
answer came back, and a ledger that recorded only successes would under-report
spend exactly when something is going wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .adapter import ExecutionOutcome
from .timeout import assert_completed, limits_from_policy

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..contracts.policy import QueryPolicy
    from .adapter import ExecutionResult, WarehouseAdapter
    from .dryrun import ValidatedPlan

__all__ = ["ExecutionRecord", "assert_execution_completed", "execute_bounded"]


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    """What an execution attempt produced, successful or not.

    ``result`` is present only on completion; on any other outcome it is
    ``None``. "Output discarded on failure" is therefore a property of the type
    rather than a step someone has to remember to perform.
    """

    outcome: ExecutionOutcome
    actual_bytes: int
    job_ref: str
    result: ExecutionResult | None = None

    @property
    def completed(self) -> bool:
        return self.outcome is ExecutionOutcome.COMPLETED


def execute_bounded(
    adapter: WarehouseAdapter,
    plan: ValidatedPlan,
    policy: QueryPolicy,
) -> ExecutionRecord:
    """Run the validated plan under governed bounds.

    Returns a record for every outcome rather than raising on failure. The
    caller must write the cost to the ledger before deciding what to report, and
    an exception here would lose the one number that has to be written down.
    Refusal is the caller's next step, through ``assert_execution_completed``.
    """
    limits = limits_from_policy(policy)
    result = adapter.execute(plan.query, limits)

    if result.outcome is not ExecutionOutcome.COMPLETED:
        # Cost is kept; rows are not. Even a cancelled execution was billed for
        # whatever it scanned before the warehouse stopped it.
        return ExecutionRecord(
            outcome=result.outcome,
            actual_bytes=result.actual_bytes,
            job_ref=result.job_ref,
            result=None,
        )

    return ExecutionRecord(
        outcome=result.outcome,
        actual_bytes=result.actual_bytes,
        job_ref=result.job_ref,
        result=result,
    )


def assert_execution_completed(record: ExecutionRecord) -> ExecutionResult:
    """Unwrap a completed execution, or refuse with its governed code.

    The only way to obtain the rows. A caller cannot read ``record.result``
    without having handled the failure cases first, because on those it is
    ``None``.
    """
    if record.result is None:
        assert_completed(_synthetic(record))
        raise AssertionError(  # pragma: no cover - a non-completed record always refuses
            "unreachable: assert_completed must refuse every non-completed outcome"
        )
    return record.result


def _synthetic(record: ExecutionRecord) -> ExecutionResult:
    """The minimal shape ``assert_completed`` inspects, for a failed record."""
    from .adapter import ExecutionResult, ResultSchema

    return ExecutionResult(
        schema=ResultSchema(),
        rows=(),
        actual_bytes=record.actual_bytes,
        job_ref=record.job_ref,
        outcome=record.outcome,
    )
