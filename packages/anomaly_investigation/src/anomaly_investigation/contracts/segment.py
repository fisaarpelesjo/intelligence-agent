"""One dimension value's figure and its share — T008.

**Association only.** A segment contribution says *this segment moved by this much
and accounts for this share of the total movement*. It never says the segment
**caused** anything.

``value`` is a measurement and ``contribution`` is an assertion, and the two live
apart on purpose: a segment's figure is what the warehouse returned; *"this segment
accounts for this share"* is a statement about the movement.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field, field_validator, model_validator

from ._base import AnomalyModel, GovernedName
from .candidate import ClaimType

__all__ = ["SegmentContribution", "SourceValue"]


class SourceValue(AnomalyModel):
    """Text that came from a source, carried as the **value of a named field**.

    A dimension label arrives from a warehouse row and may read *"queda causada
    por mudança de preço"*. **It is still delivered** — withholding source data
    would be a different feature and a worse one. What `FR-014` forbids is the one
    thing that would make it ours:

    .. code-block:: text

        "O segmento " + label + " puxou a queda"   <- FORBIDDEN, and T029 refuses it
        SourceValue(text=label, origin="platform") <- this is the contract

    **This is a type rather than a convention**, and that is what makes the
    structural check possible: a convention can only be reviewed, a type can be
    checked. It states the limit `SC-003a` states — a closed vocabulary governs
    what this feature *writes*, never what a warehouse row *carries*.
    """

    text: str = Field(
        max_length=1000,
        description="Exactly what the source returned. Never edited, never trimmed, never ours.",
    )
    origin: GovernedName = Field(
        description="Which dimension this value came from, so a reader knows whose text it is."
    )


class SegmentContribution(AnomalyModel):
    """One segment's figure and its share of the movement."""

    dimension: GovernedName = Field(
        description="One of the baseline's declared dimensions, resolved through the catalog."
    )
    segment_label: SourceValue = Field(description="Source text, never concatenated (FR-014).")
    value: Decimal | None = Field(
        default=None,
        description="None when the cell was suppressed. **A suppressed cell is not a zero.**",
    )
    suppressed: bool = Field(
        default=False, description="Carried from `002`'s ResultCell.suppressed."
    )
    contribution: Decimal = Field(
        description="The baseline's contribution_to_change, obtained through `003`. An assertion."
    )
    claim_type: ClaimType

    @field_validator("value", "contribution")
    @classmethod
    def _is_finite(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("a segment figure must be finite")
        return value

    @model_validator(mode="after")
    def _suppressed_carries_no_value(self) -> SegmentContribution:
        """A suppressed cell may not also carry a figure.

        If both were allowed, a caller could read the number and ignore the flag —
        which is the *"treat a suppressed cell as data"* failure arriving through
        the contract instead of through arithmetic. Refusing the combination makes
        the flag impossible to bypass by not looking at it.
        """
        if self.suppressed and self.value is not None:
            raise ValueError("a suppressed segment carries no value")
        return self
