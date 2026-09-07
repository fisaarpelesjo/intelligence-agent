"""One invocation over a set of rules — T010.

**A run with zero candidates is a successful run** (`FR-009`). The distinction that
makes that safe is `SC-002`'s: *"nothing moved"* and *"we could not tell"* must stay
readable apart, so this contract keeps three lists where one would be tempting.

``instant`` is a **parameter**. Nothing here reads a clock, and nothing here starts
itself (`FR-007`, `FR-012`) — whatever calls a run supplies the moment it ran.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator
from semantic_catalog.freshness.external import FreshnessRecord

from ._base import AnomalyModel, GovernedName
from .candidate import CandidateFinding
from .reason_codes import AnomalyReasonCode

__all__ = ["Run", "RunOutcome", "Withholding"]


class RunOutcome(StrEnum):
    """Whether the run itself completed.

    ``COMPLETED`` with zero candidates is the ordinary quiet day. ``FAILED`` means
    the run could not be carried out — and conflating the two is what turns a
    healthy silence into an alarm, or an outage into a healthy silence.
    """

    COMPLETED = "completed"
    FAILED = "failed"


class Withholding(AnomalyModel):
    """One rule that could not be evaluated, and why.

    **The code is ours; the evidence is the source's.** They meet here without
    mixing: ``reason_code`` is a governed word from this feature's namespace, and
    ``freshness`` is the record that produced it. `FR-014` is easiest to violate
    at a refusal path, where writing a helpful sentence feels harmless.

    ``upstream_code`` exists because `FR-001` says an unbound metric refuses
    **upstream**: when that happens the original code travels here verbatim rather
    than being re-classified into this vocabulary, which is how the original
    reason stays readable.
    """

    rule_id: GovernedName
    reason_code: AnomalyReasonCode
    freshness: FreshnessRecord | None = Field(
        default=None,
        description="The observation that produced the withholding, when one exists.",
    )
    upstream_code: str | None = Field(
        default=None,
        max_length=200,
        description="An upstream refusal carried verbatim, never restated (FR-001).",
    )


class Run(AnomalyModel):
    """What one invocation did, rule by rule."""

    run_id: GovernedName
    instant: datetime = Field(
        description="Supplied by the caller. This feature reads no clock (FR-007)."
    )
    rules_considered: tuple[GovernedName, ...] = Field(default=())
    candidates: tuple[CandidateFinding, ...] = Field(default=())
    withholdings: tuple[Withholding, ...] = Field(
        default=(), description='"We could not tell" — one per rule that could not be evaluated.'
    )
    quiet: tuple[GovernedName, ...] = Field(
        default=(), description='"Nothing moved" — rules that ran and did not cross.'
    )
    never_firable: tuple[GovernedName, ...] = Field(
        default=(),
        description=(
            "Rules whose threshold cannot be crossed. A configuration defect, reported "
            "rather than hidden — a detector that hides one makes the KPI look quiet."
        ),
    )
    outcome: RunOutcome

    @model_validator(mode="after")
    def _every_rule_is_accounted_for(self) -> Run:
        """A completed run says what happened to **each** rule it considered.

        This is `SC-002` made structural. Without it, a rule could vanish from a
        run's report — neither fired, nor quiet, nor withheld — and its silence
        would be indistinguishable from *"nothing moved"*, which is the one
        inference this feature must never let a reader make by accident.

        A ``FAILED`` run is exempt: it stopped, so the fact that it cannot account
        for every rule is the honest reading of what happened.
        """
        if self.outcome is not RunOutcome.COMPLETED:
            return self

        considered = set(self.rules_considered)
        reported = (
            {candidate.rule_id for candidate in self.candidates}
            | {withholding.rule_id for withholding in self.withholdings}
            | set(self.quiet)
            | set(self.never_firable)
        )
        missing = considered - reported
        if missing:
            raise ValueError(f"completed run does not account for: {sorted(missing)}")
        unexpected = reported - considered
        if unexpected:
            raise ValueError(f"run reports rules it did not consider: {sorted(unexpected)}")
        return self
