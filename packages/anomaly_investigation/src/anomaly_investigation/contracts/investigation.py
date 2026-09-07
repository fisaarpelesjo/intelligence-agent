"""One candidate's dimension breakdown — T009.

**An entity, not just the set of its segments**, and `FR-011` is what forces that:
an investigation that finds no declared dimension has **zero** segment
contributions and **still has to report that absence** — and a set with no members
reports nothing.

So it carries what no member can: the reconciliation verdict, the declaration that
no dimension was declared, and the causality warning every output carries.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from ._base import AnomalyModel, GovernedName
from .candidate import REQUIRED_CAUSALITY_WARNING, ClaimType
from .segment import SegmentContribution

__all__ = ["Investigation", "ReconciliationVerdict"]


class ReconciliationVerdict(StrEnum):
    """Whether the segments account for the total.

    ``NOT_ATTEMPTED`` is the value that makes the empty case honest. With zero
    declared dimensions there is nothing to reconcile, and ``RECONCILED`` would be
    **vacuously true** — the exact defect the spec's convention names, where a
    criterion that can never fail reads as a criterion that passed. *Nothing was
    attempted* can never be mistaken for *everything agreed*.
    """

    RECONCILED = "reconciled"
    DID_NOT_RECONCILE = "did_not_reconcile"
    NOT_ATTEMPTED = "not_attempted"


class Investigation(AnomalyModel):
    """The dimension breakdown of one candidate, association only."""

    rule_id: GovernedName = Field(description="The candidate investigated.")
    dimensions_declared: tuple[GovernedName, ...] = Field(
        default=(),
        description="May be EMPTY, and empty is a reported fact rather than an absence.",
    )
    contributions: tuple[SegmentContribution, ...] = Field(default=())
    reconciliation: ReconciliationVerdict
    residual: Decimal | None = Field(
        default=None,
        description="The unexplained remainder. None when reconciliation was not attempted.",
    )
    claim_type: ClaimType = Field(
        description="The reconciliation verdict is an assertion, so it declares its class."
    )
    causality_warning: str = Field(description="Byte-equal, on every emitted output.")

    @field_validator("causality_warning")
    @classmethod
    def _warning_is_the_governed_sentence(cls, value: str) -> str:
        if value != REQUIRED_CAUSALITY_WARNING:
            raise ValueError("causality_warning must be byte-equal to the baseline's warning")
        return value

    @field_validator("residual")
    @classmethod
    def _residual_is_finite(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("residual must be finite")
        return value

    @model_validator(mode="after")
    def _absence_and_verdict_agree(self) -> Investigation:
        """Three couplings, and each one closes a way of reading a hole as a result.

        **No declared dimension means nothing was attempted.** Any other verdict
        over an empty set is an agreement with nobody.

        **Contributions without declared dimensions are impossible**, because a
        segment belongs to a dimension the catalog declared.

        **A verdict that was not attempted carries no residual.** A residual is
        the remainder of a subtraction that did not happen.
        """
        if not self.dimensions_declared:
            if self.contributions:
                raise ValueError("contributions exist but no dimension was declared")
            if self.reconciliation is not ReconciliationVerdict.NOT_ATTEMPTED:
                raise ValueError("with no declared dimension the verdict is NOT_ATTEMPTED")
        if self.reconciliation is ReconciliationVerdict.NOT_ATTEMPTED and self.residual is not None:
            raise ValueError("a reconciliation that was not attempted has no residual")
        return self
