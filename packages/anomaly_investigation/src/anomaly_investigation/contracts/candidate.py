"""The candidate finding — T007.

One measured movement worth a person's attention. **Unconstructible without its
evidence** (`FR-005`): every field below is required, and there is no default that
would let a candidate exist with a hole where its proof should be.

**Exactly one field carries an assertion** — ``direction``. That is not an accident
of drafting: everything richer is the owner's item 7, and ``extra="forbid"`` on the
base is what keeps a ``severity`` from being added by a well-meaning caller.

The three upstream types are **carried whole and never re-declared**:
``DerivedFigure`` from `003`, ``ComparableWindow`` from `002`, ``FreshnessRecord``
from `001`. A second definition of any of them would drift.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from analytics_interaction.comparison.direction import Direction
from analytics_interaction.contracts import DerivedFigure
from analytics_query.contracts.comparable_window import ComparableWindow
from pydantic import Field, field_validator
from semantic_catalog.freshness.external import FreshnessRecord

from ._base import AnomalyModel, GovernedName

__all__ = ["REQUIRED_CAUSALITY_WARNING", "CandidateFinding", "ClaimType"]


#: The baseline's ``proactive_insights.causality.required_warning``, byte for byte.
#:
#: **Transported, never composed.** It is a literal here because this feature is
#: forbidden to write prose (`FR-013`), and a sentence assembled at runtime would
#: be prose however short. The contract test compares this constant against the
#: baseline file by **equality**, so a drift in either direction fails rather than
#: silently emitting a paraphrase.
REQUIRED_CAUSALITY_WARNING = (
    "Os dados podem indicar associação temporal, mas não comprovam causalidade."
)


class ClaimType(StrEnum):
    """The baseline's ``allowed_language`` — **closed at three**.

    ``automatic_claims_allowed`` is ``false``, so a fourth value cannot be
    introduced by this feature. Checked as an **enum domain** rather than as a
    string, so a typo cannot pass as a fourth kind.
    """

    CORRELATION = "correlation"
    TEMPORAL_ASSOCIATION = "temporal_association"
    HYPOTHESIS = "hypothesis"


class CandidateFinding(AnomalyModel):
    """A movement that crossed a rule's threshold, with the evidence that let it.

    **What is absent is the point.** There is no ``cause``, no ``because``, no
    ``driver``, no ``root_cause`` and no field whose name implies one. `FR-006` is
    enforced by the shape before any test runs.
    """

    rule_id: GovernedName = Field(description="Which rule fired.")
    figure: DerivedFigure = Field(
        description="Carried from `003`. Already names derived_from and basis."
    )
    baseline_value: Decimal = Field(description="The side compared against, as returned.")
    direction: Direction = Field(
        description="The one assertion a candidate carries, hence the claim_type below."
    )
    primary_window: ComparableWindow
    baseline_window: ComparableWindow
    freshness: FreshnessRecord = Field(
        description=(
            "The observation that let this fire — a whole record, not a flag. "
            "A boolean would collapse the distinction SC-002 asserts."
        )
    )
    claim_type: ClaimType
    causality_warning: str = Field(description="Byte-equal to the baseline's required_warning.")

    @field_validator("causality_warning")
    @classmethod
    def _warning_is_the_governed_sentence(cls, value: str) -> str:
        """Equality, not containment.

        The moment a check accepted a paraphrase — or a sentence that merely
        *contains* the warning — this feature would be composing the warning, and
        composing is what `FR-013` forbids. The strict check is what keeps the
        transport honest.
        """
        if value != REQUIRED_CAUSALITY_WARNING:
            raise ValueError("causality_warning must be byte-equal to the baseline's warning")
        return value

    @field_validator("baseline_value")
    @classmethod
    def _baseline_is_finite(cls, value: Decimal) -> Decimal:
        """A non-finite baseline is not a measurement, and a candidate is evidence."""
        if not value.is_finite():
            raise ValueError("baseline_value must be finite")
        return value
