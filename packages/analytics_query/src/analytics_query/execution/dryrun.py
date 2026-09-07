"""Dry-run validation — T072 (FR-021; SC-003).

Execution is unreachable without a successful dry run. Not "should be preceded
by" — unreachable, because the only way to obtain the token that
``execution/run.py`` requires is to complete one.

The dry run is what makes the byte and row ceilings enforceable *before*
anything is billed: it returns the estimate and the schema the request will
produce, so the ceilings are checked against a real projection rather than a
guess. Skipping it would leave both ceilings as post-hoc reports of money
already spent.

A failed dry run refuses with ``DRY_RUN_FAILED`` and never falls through to
execution. The warehouse refusing to plan a query is not a reason to run it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..contracts._base import ContractViolation
from ..contracts.reason_codes import AnalyticsReasonCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .adapter import DryRunResult, RenderedQuery, ResultSchema, WarehouseAdapter

__all__ = ["DryRunFailed", "ValidatedPlan", "perform_dry_run"]


class DryRunFailed(Exception):  # noqa: N818 - a governed refusal, not an error
    """The warehouse could not plan the query, so it will not run it."""

    def __init__(self, detail: str) -> None:
        self.code = AnalyticsReasonCode.DRY_RUN_FAILED
        self.detail = detail
        super().__init__(f"{self.code.value}: {detail}")


@dataclass(frozen=True, slots=True)
class ValidatedPlan:
    """Proof that a dry run succeeded, plus what it established.

    This type is the mechanism. ``execution/run.py`` takes a ``ValidatedPlan``
    rather than a ``RenderedQuery``, and the only constructor is
    ``perform_dry_run`` — so "no execution without a dry run" is enforced by
    what the execution function will accept, not by a check someone must
    remember to call first.
    """

    query: RenderedQuery
    estimated_bytes: int
    schema: ResultSchema
    projected_rows: int | None

    def refusal(self) -> ContractViolation:  # pragma: no cover - convenience
        """Never used on the success path; present so callers need no raw code."""
        return ContractViolation(AnalyticsReasonCode.DRY_RUN_FAILED, "the dry run did not succeed")


def perform_dry_run(adapter: WarehouseAdapter, query: RenderedQuery) -> ValidatedPlan:
    """Plan the query without reading, or refuse.

    Every adapter failure collapses to one outcome. Distinguishing "syntax
    error" from "table not found" would tell a caller about the shape of the
    warehouse, and neither changes what happens next.
    """
    try:
        result: DryRunResult = adapter.dry_run(query)
    except Exception as exc:
        raise DryRunFailed(f"the warehouse could not plan the query: {exc}") from exc

    if result.estimated_bytes < 0:
        raise DryRunFailed("the dry run reported a negative byte estimate")

    return ValidatedPlan(
        query=query,
        estimated_bytes=result.estimated_bytes,
        schema=result.schema,
        projected_rows=result.projected_rows,
    )
