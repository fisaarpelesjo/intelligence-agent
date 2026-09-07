"""Byte ceiling — T073 (FR-022; SC-004).

Two enforcement points, deliberately, and they protect different failures.

**Here, before execution**: the dry-run estimate is compared against
``maximum_bytes_billed`` and an over-estimate refuses. Zero execution, zero
actual bytes, and the caller is told the estimate and the limit so they can
narrow the request themselves.

**On the job** (`adapters/bigquery/client.py`): the same limit is set on the
warehouse job, so an execution whose real scan exceeds it is cancelled by the
warehouse rather than discovered afterwards. An estimate is an estimate; the
job-level ceiling is what makes `SC-004` true rather than probable.

Neither is redundant. The first gives a legible refusal, the second is the one
that holds when the estimate was wrong.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..contracts._base import ContractViolation
from ..contracts.reason_codes import AnalyticsReasonCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..contracts.policy import QueryPolicy
    from .dryrun import ValidatedPlan

__all__ = ["assert_within_byte_ceiling"]


def assert_within_byte_ceiling(plan: ValidatedPlan, policy: QueryPolicy) -> None:
    """Refuse when the estimate exceeds the governed ceiling.

    Takes a ``ValidatedPlan`` rather than a raw estimate: there is no way to
    check this ceiling without having run the dry run that produced the figure.

    The refusal names both numbers. That is a disclosure, and it is permitted
    only because the pipeline reaches this point after authorisation -- the
    caller is entitled to know the budget they exceeded.
    """
    estimated = plan.estimated_bytes
    limit = policy.maximum_bytes_billed
    if estimated > limit:
        raise ContractViolation(
            AnalyticsReasonCode.QUERY_COST_LIMIT_EXCEEDED,
            f"the query is estimated to scan {estimated} bytes, "
            f"over the governed maximum of {limit}",
        )
