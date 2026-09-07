"""Cost provenance — T077 (FR-031; SC-035).

Both figures are always reported: the dry-run estimate and the actual bytes
billed. `SC-035` is measured on this — 100% of returned results carry both.

**Variance between them never withholds a result.** A dry run is an estimate by
definition, so a query that scans more than projected is ordinary, not
suspicious. Withholding on variance would discard correct results; tolerating it
"within a margin" would need a tolerance number nobody has a basis to set. What
actually bounds the overrun is the ceiling enforced on the job, which cancels an
execution that exceeds it (`FR-023`) — so by the time a result exists, the
variance is already known to be within budget.

Reporting both is what makes the estimate auditable rather than decorative: a
persistent gap between projection and reality is visible to whoever reads the
provenance, without any single query being refused for it.
"""

from __future__ import annotations

from pydantic import Field, StrictInt, model_validator

from ._base import ContractViolation, QueryModel
from .reason_codes import AnalyticsReasonCode

__all__ = ["CostProvenance"]


class CostProvenance(QueryModel):
    """What a query was projected to cost, and what it did cost."""

    dry_run_bytes: StrictInt = Field(ge=0)
    actual_bytes: StrictInt = Field(ge=0)
    maximum_bytes_billed: StrictInt = Field(gt=0)

    @model_validator(mode="after")
    def _actual_is_within_the_enforced_ceiling(self) -> CostProvenance:
        """A completed execution cannot have exceeded its own ceiling.

        The warehouse cancels an over-limit query, so a result reporting more
        billed bytes than the ceiling allowed describes something that should not
        have been able to happen — the ceiling was not applied to the job. That
        is a defect in enforcement, and it must not pass as a reported figure.
        """
        if self.actual_bytes > self.maximum_bytes_billed:
            raise ContractViolation(
                AnalyticsReasonCode.QUERY_COST_LIMIT_EXCEEDED,
                "the execution reports more billed bytes than the enforced ceiling allowed",
            )
        return self

    @property
    def variance_bytes(self) -> int:
        """Actual minus estimate. Negative when the estimate was generous.

        Reported, never acted on: no threshold over this value withholds a
        result.
        """
        return self.actual_bytes - self.dry_run_bytes

    @property
    def underestimated(self) -> bool:
        """Whether the execution scanned more than projected.

        True is a normal, returnable state. It exists so a steward can see the
        pattern, not so the pipeline can branch on it.
        """
        return self.actual_bytes > self.dry_run_bytes
