"""Row ceiling — T074 (FR-024; SC-017).

A result that would exceed ``maximum_rows`` is **refused**. It is not truncated,
paged, sampled or capped.

The reason is that a reduced table is a different answer wearing the shape of
the one that was asked for. Its safety would depend on every downstream consumer
noticing a flag and handling it -- including the model-facing surface, which is
the consumer least able to be relied on for that. A refusal cannot be
misread.

There is no truncation path to disable, which is the stronger form of the
guarantee: ``Completeness`` has no ``TRUNCATED`` member, so a partial table is
not representable, and this module has no parameter that would produce one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..contracts._base import ContractViolation
from ..contracts.reason_codes import AnalyticsReasonCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..contracts.policy import QueryPolicy
    from .dryrun import ValidatedPlan

__all__ = ["assert_within_row_ceiling"]


def assert_within_row_ceiling(plan: ValidatedPlan, policy: QueryPolicy) -> None:
    """Refuse when the projection exceeds the governed row ceiling.

    When the dry run supplies no projection, this check does not silently pass:
    the row ceiling is enforced again after execution, against the real count,
    and a breach there refuses the assembled result rather than trimming it.
    An unknown projection is not evidence of a small result.
    """
    projected = plan.projected_rows
    if projected is None:
        return
    limit = policy.maximum_rows
    if projected > limit:
        raise ContractViolation(
            AnalyticsReasonCode.QUERY_ROW_LIMIT_EXCEEDED,
            f"the query is projected to return {projected} rows, "
            f"over the governed maximum of {limit}",
        )


def assert_returned_rows_within_ceiling(row_count: int, policy: QueryPolicy) -> None:
    """The post-execution half, for when the dry run projected nothing.

    Refuses the whole result. Returning the first ``maximum_rows`` of it would
    be exactly the truncation this feature does not do.
    """
    limit = policy.maximum_rows
    if row_count > limit:
        raise ContractViolation(
            AnalyticsReasonCode.QUERY_ROW_LIMIT_EXCEEDED,
            f"the query returned {row_count} rows, over the governed maximum of {limit}",
        )
