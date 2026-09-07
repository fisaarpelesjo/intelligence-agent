"""One declared ingredient of an ordering — T003 (`FR-002`, `FR-004`).

**This module is where the first of `spec.md` § 2's three risks becomes structure
rather than a comment: a missing component is NAMED and NEVER ZEROED.**

The defect it forecloses is not hypothetical. `005` measured its exact shape in the
warehouse: `Not renewed (qty)` runs 95 to 137 per day for 396 days, then **disappears**
on the newest day — and a rule that treated the absence as a value read **minus 100 per cent**,
a fall, instead of *incomplete day*. **Substituting zero for an absence does not
express ignorance; it expresses a judgement**, and here that judgement is *"this
finding is the least important"*.

So the type below cannot hold an absence disguised as a number. Not by convention —
**by construction**: a component carries a value **or** a named absence, exactly one
of the two, and a construction with both or with neither is refused.

**Zero is still a legal value**, and that is deliberate. A component measured at
zero is a measurement. The defect was never the number; it was the substitution.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Self

from pydantic import Field, field_validator, model_validator

from ._base import GovernedName, PriorityContractViolation, PriorityModel
from .reason_codes import PriorityReasonCode

__all__ = ["ComponentAbsence", "PriorityComponent"]


class ComponentAbsence(PriorityModel):
    """Why a component could not be obtained.

    **The reason is a governed code and not free text**, so an absence can be
    counted, compared and refused. A sentence here would be prose this feature
    composed about its own failure, which `FR-006` forbids on emitted fields.
    """

    reason: PriorityReasonCode = Field(
        description="Why the value is absent. Never a sentence -- a governed code."
    )

    @field_validator("reason")
    @classmethod
    def _reason_is_one_this_module_owns(cls, value: PriorityReasonCode) -> PriorityReasonCode:
        """Only the two codes that describe an absence may appear here.

        The other two in the namespace describe a *run* or an *ordering* failing,
        and letting them stand in for a missing component is the `005` defect of
        **a code used for something that was never its job**.
        """
        permitted = {
            PriorityReasonCode.PRIORITY_COMPONENT_UNAVAILABLE,
            PriorityReasonCode.PRIORITY_DIRECTION_NOT_DECLARED,
            PriorityReasonCode.PRIORITY_CONFIDENCE_NOT_MEASURED,
        }
        if value not in permitted:
            raise PriorityContractViolation(
                f"{value.value!r} does not describe a missing component; "
                f"permitted here: {sorted(c.value for c in permitted)}"
            )
        return value


class PriorityComponent(PriorityModel):
    """One named ingredient of an ordering, with where it was read from.

    ``read_from`` is required and has no default. A component whose source entity
    is unnamed is **unconstructible**, which is what makes `FR-002` checkable: an
    ordering can be reconstructed from its output only if every ingredient says
    where it came from.
    """

    name: GovernedName = Field(description="Which component this is. Declared, not inferred.")
    read_from: GovernedName = Field(
        description=(
            "The entity this value was read from. Required and never defaulted: a "
            "component with no source cannot be checked by a reader."
        )
    )

    #: Exactly one of the two below is set. The validator enforces it.
    value: Decimal | None = Field(
        default=None,
        description="The measured value. Exact, never float. Zero is a value, not an absence.",
    )
    absence: ComponentAbsence | None = Field(
        default=None, description="Set instead of `value` when the component could not be obtained."
    )
    weighted_by: GovernedName | None = Field(
        default=None,
        description=(
            "What multiplied this value, named. Set when a confidence factor was "
            "applied; `None` means the value is as it was read."
        ),
    )

    @field_validator("value")
    @classmethod
    def _value_is_finite(cls, value: Decimal | None) -> Decimal | None:
        """``NaN`` and infinity are refused where they arrive.

        A non-finite component would make every comparison against it false, so a
        finding carrying one would sort in a position nobody can explain — and it
        would look like a measurement while behaving like an absence. `005` closed
        the same hole twice, on a rule threshold and on an observed figure.
        """
        if value is not None and not value.is_finite():
            raise PriorityContractViolation("a component value must be finite")
        return value

    @model_validator(mode="after")
    def _a_value_or_a_named_absence_never_both_and_never_neither(self) -> Self:
        """**The structural form of `FR-004`.**

        Four states are conceivable and only two are legal:

        =================  =============  ==========================================
        ``value``          ``absence``    outcome
        =================  =============  ==========================================
        set                unset          the component was obtained
        unset              set            the component was **not** obtained, named
        set                set            refused -- which is it?
        unset              unset          refused -- **this is the zero-default hole**
        =================  =============  ==========================================

        The fourth row is the one that matters. Without this refusal a caller could
        build a component with neither, and every downstream arithmetic would treat
        the missing value as whatever its own default was — most often zero. **The
        contract makes the silent path unreachable rather than discouraged.**
        """
        has_value = self.value is not None
        has_absence = self.absence is not None
        if has_value and has_absence:
            raise PriorityContractViolation(
                f"component {self.name!r} carries both a value and an absence; exactly one is legal"
            )
        if not has_value and not has_absence:
            raise PriorityContractViolation(
                f"component {self.name!r} carries neither a value nor a named absence. "
                "An absence must be named -- it is never a default and never zero."
            )
        if self.weighted_by is not None and not has_value:
            raise PriorityContractViolation(
                f"component {self.name!r} names {self.weighted_by!r} as its weight and carries "
                "no value; a factor applied to nothing is a claim about a number nobody has"
            )
        return self

    @property
    def is_available(self) -> bool:
        """Whether this component contributed a value.

        A property rather than a stored field so it cannot disagree with the two
        fields it summarises.
        """
        return self.value is not None
