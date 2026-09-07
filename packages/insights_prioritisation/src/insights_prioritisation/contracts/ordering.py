"""One ordering, over one aggregation class — T005 (`FR-005`, `FR-010`, `SC-002`, `SC-004`).

**This module is where the second of `spec.md` § 2's risks becomes structure:
SNAPSHOT AND COUNT DO NOT SHARE A SCALE without a declared normalisation.**

`004` measured the three aggregation classes as not interchangeable. `005` measured
the consequence in the warehouse: `MAU`, `Paid subscribers`, `MRR` and `LTV` are
**snapshots**, and the pipeline's own documentation warns they inflate about
**thirty-fold** if summed across days. A prioritiser that puts a snapshot movement
and a count movement on one scale does not compare them — **it invents a common
unit**, and the finding that wins wins for that reason alone.

## And ties are a shape here, not a flag

`FR-010` says a tie must be reported and input order must not break it. A flat
sequence cannot express that: whatever order the tied findings sit in **is** an
order, and a reader cannot tell it from a decision.

So an ordering is a sequence of **rank groups**. A group with more than one member
*is* the tie, and there is nowhere to record an order within it. **The structure
makes silently breaking a tie unrepresentable rather than discouraged.**
"""

from __future__ import annotations

from typing import Self

from anomaly_investigation.contracts import AggregationClass
from pydantic import Field, model_validator

from ._base import GovernedName, PriorityContractViolation, PriorityModel
from .prioritised import NotPrioritisable, PrioritisedFinding

__all__ = ["Normalisation", "Ordering"]


class Normalisation(PriorityModel):
    """A declared way of comparing across aggregation classes.

    **This type exists so that crossing classes is possible but never silent.**
    `FR-005` permits either answer — one ordering per class, or one ordering under a
    declared normalisation — and forbids the third: a single scale nobody declared.

    ``basis`` is a governed name and not a formula, because choosing *how* to
    compare a snapshot with a count is a business decision (`D-B` in `spec.md`),
    and a formula here would be this feature taking it.
    """

    basis: GovernedName = Field(
        description="The declared basis of comparison. Named by governance, not chosen here."
    )
    covers: tuple[AggregationClass, ...] = Field(
        description="Which classes this normalisation claims to make comparable."
    )

    @model_validator(mode="after")
    def _a_normalisation_covers_more_than_one_class(self) -> Self:
        """A normalisation over one class normalises nothing.

        Without this, a caller could declare a normalisation covering only
        ``COUNT`` and use its presence to justify mixing in a ``SNAPSHOT`` that the
        declaration never mentioned — the vacuously-satisfied condition of `F115`.
        """
        if len(set(self.covers)) < 2:
            raise PriorityContractViolation(
                f"normalisation {self.basis!r} covers {[c.value for c in self.covers]}; "
                "a normalisation exists to relate at least two classes"
            )
        return self


class Ordering(PriorityModel):
    """The placed findings and the ones that could not be placed.

    ``positions`` is a tuple of **rank groups**, best first. ``(a,), (b, c), (d,)``
    reads as: ``a`` first, ``b`` and ``c`` **tied** second, ``d`` fourth.
    """

    aggregation_class: AggregationClass | None = Field(
        default=None,
        description=(
            "The single class every member shares. `None` only when a normalisation "
            "is declared, and then the normalisation names the classes instead."
        ),
    )
    normalisation: Normalisation | None = Field(
        default=None,
        description="Required to mix classes; absent means this ordering holds one class.",
    )
    positions: tuple[tuple[PrioritisedFinding, ...], ...] = Field(
        default=(),
        description="Rank groups, best first. A group of more than one IS a reported tie.",
    )
    not_prioritisable: tuple[NotPrioritisable, ...] = Field(
        default=(),
        description="Findings that could not be placed, each naming its missing component.",
    )

    @model_validator(mode="after")
    def _the_ordering_defends_itself(self) -> Self:
        """Four refusals here, and a fifth that lives elsewhere. Each closes a way of
        publishing an unjustified order.

        1. **An empty rank group.** A group with no members is a rank nothing
           occupies, and it would shift every rank below it by one for no reason.
        2. **A finding in two places.** `SC-002` literally: a candidate both ordered
           and not prioritisable, or ordered twice, means the reader cannot say what
           the feature concluded.
        3. **Class and normalisation both absent.** Then nothing states what these
           findings have in common, and `FR-005`'s *"absent that, one ordering per
           class"* has no way to be checked.
        4. **Both present.** A single declared class *and* a normalisation across
           classes contradict each other; keeping both would let a reader pick the
           one that suits them.
        5. **A member outside the declared class** — and this one is **NOT checkable
           here**, which the first version of this docstring did not say. The class is
           a property of the `005` rule that produced the candidate, and
           `PrioritisedFinding` does not carry it, so there is nothing in this model to
           compare against. Saying "five refusals" while implementing four is the shape
           this repository keeps closing: a promise the code does not keep.

           **The claim is made true by construction instead**, in
           `order/within_class.py`: `one_ordering_per_class` takes findings already
           grouped by class and never merges two groups, so every member of every
           ordering it builds is of the declared class — not because something checked
           afterwards, but because nothing else was ever expressible. An `Ordering`
           built by hand can still declare a class its members do not share, and this
           docstring now says so rather than implying a guard.
        """
        groups = self.positions

        if any(len(group) == 0 for group in groups):
            raise PriorityContractViolation(
                "an ordering contains an empty rank group; a rank nobody occupies "
                "shifts every rank below it for no reason"
            )

        ordered_ids = [f.finding_id for group in groups for f in group]
        unplaced_ids = [f.finding_id for f in self.not_prioritisable]
        repeated = {i for i in ordered_ids if ordered_ids.count(i) > 1}
        both = set(ordered_ids) & set(unplaced_ids)
        if repeated:
            raise PriorityContractViolation(
                f"these findings appear more than once in the ordering: {sorted(repeated)}"
            )
        if both:
            raise PriorityContractViolation(
                f"these findings are both ordered and not prioritisable: {sorted(both)}. "
                "A reader cannot tell what was concluded."
            )

        has_class = self.aggregation_class is not None
        has_norm = self.normalisation is not None
        if not has_class and not has_norm:
            raise PriorityContractViolation(
                "an ordering declares either the single aggregation class its members "
                "share, or a normalisation that relates several. Neither was declared, "
                "so nothing states what these findings have in common."
            )
        if has_class and has_norm:
            raise PriorityContractViolation(
                "an ordering declares a single class or a normalisation across classes, "
                "never both -- the two contradict each other and a reader would pick one"
            )
        return self

    @property
    def is_empty(self) -> bool:
        """Whether nothing was placed.

        **An empty ordering is a result and not an absence** (`FR-009`), and the
        run that holds it says which. This property exists so a caller can ask
        without inspecting a tuple's length and inventing a meaning for it.
        """
        return not self.positions

    @property
    def ties(self) -> tuple[tuple[str, ...], ...]:
        """The reported ties, as groups of finding ids.

        Derived from ``positions`` so it cannot disagree with the ordering itself.
        """
        return tuple(
            tuple(f.finding_id for f in group) for group in self.positions if len(group) > 1
        )
