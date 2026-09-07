"""Execution timeout — T075 (FR-025; SC-020).

A query that exceeds ``execution_timeout_seconds`` is cancelled and reported as
a **timeout**. Never as an empty result, never as zero.

That distinction carries the whole requirement. "0 installs" and "we do not
know how many installs" are different claims, and only one of them is safe to
act on. A timeout rendered as an empty table would be indistinguishable from a
genuine absence of data, and the caller would have no way to tell that the
number they are reading was never computed.

Partial output from a cancelled execution is discarded, not returned as far as
it got.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..contracts._base import ContractViolation
from ..contracts.reason_codes import AnalyticsReasonCode
from .adapter import ExecutionOutcome

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..contracts.policy import QueryPolicy
    from .adapter import ExecutionLimits, ExecutionResult

__all__ = ["OUTCOME_REASONS", "assert_completed", "limits_from_policy"]

#: Every non-completed outcome and the governed code it reports. Each is its own
#: condition, and none of them is an empty result.
OUTCOME_REASONS: dict[ExecutionOutcome, AnalyticsReasonCode] = {
    ExecutionOutcome.TIMED_OUT: AnalyticsReasonCode.QUERY_TIMEOUT,
    ExecutionOutcome.CANCELLED_OVER_LIMIT: AnalyticsReasonCode.QUERY_COST_LIMIT_EXCEEDED,
    ExecutionOutcome.FAILED: AnalyticsReasonCode.WAREHOUSE_UNAVAILABLE,
}


def limits_from_policy(policy: QueryPolicy) -> ExecutionLimits:
    """Build the job-level bounds from the governed policy.

    Both bounds come from the policy and neither has a default here. An
    execution whose limits were assembled from anything else would be bounded by
    numbers nobody approved.
    """
    from .adapter import ExecutionLimits

    return ExecutionLimits(
        maximum_bytes_billed=policy.maximum_bytes_billed,
        timeout_seconds=policy.execution_timeout_seconds,
    )


def assert_completed(result: ExecutionResult) -> None:
    """Refuse anything that is not a completed execution.

    Deny by default: an outcome absent from the mapping still refuses, with
    ``WAREHOUSE_UNAVAILABLE``, rather than being treated as success because it
    was unrecognised.
    """
    if result.outcome is ExecutionOutcome.COMPLETED:
        return
    code = OUTCOME_REASONS.get(result.outcome, AnalyticsReasonCode.WAREHOUSE_UNAVAILABLE)
    raise ContractViolation(
        code,
        f"the execution ended as {result.outcome.value} and its partial output is discarded",
    )
