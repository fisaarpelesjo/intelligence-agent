"""A finding together with the grounds that placed it — T004 (`FR-002`, `FR-011`, `FR-012`).

**This module is where the third of `spec.md` § 2's risks becomes structure: an
inherited approximation TRAVELS.**

The caveat this exists for is real and it is not ours. The only warehouse table with
data attributes revenue and subscriptions to a game by the user's *most played*
game, and the builder's own comment says so: *"APROXIMACAO: a assinatura inteira vai
pro top_game do usuario"*. A ranking that puts a game first while dropping that
sentence presents an **approximate attribution as a precise priority**.

So caveats are a field of the placed finding rather than of the run. A caveat on the
run would say *"something here is approximate"*; a caveat on the position says
**which** one is.

**And the reading instant travels for the same reason.** The source table is
`CREATE OR REPLACE` daily: two correct readings of the same quantity gave 7.019 and
6.942 on consecutive days. A figure without its instant is a number whose meaning
expired quietly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import Field, field_validator, model_validator

from ._base import GovernedName, PriorityContractViolation, PriorityModel
from .component import PriorityComponent

__all__ = ["NotPrioritisable", "PrioritisedFinding"]


class PrioritisedFinding(PriorityModel):
    """One candidate placed in an ordering, with everything that placed it.

    **Every component here carries a value.** A finding with an absent component is
    not a finding placed lower — it is a :class:`NotPrioritisable`, and the two are
    different types precisely so that no arithmetic can slide one into the other.
    """

    finding_id: GovernedName = Field(
        description="The candidate this position belongs to. Identity comes from `005`."
    )
    components: tuple[PriorityComponent, ...] = Field(
        description="The grounds of the position. Reconstructible by a reader (FR-002)."
    )
    reading_instant: datetime = Field(
        description=(
            "When the figures behind this finding were read. Travels because the "
            "source is rebuilt daily and a number without its instant expires quietly."
        )
    )
    caveats: tuple[str, ...] = Field(
        default=(),
        description=(
            "Carried verbatim from the input finding. Not composed here -- this "
            "field holds transported text, which is why it may be free string."
        ),
    )

    @field_validator("reading_instant")
    @classmethod
    def _instant_is_aware(cls, value: datetime) -> datetime:
        """A naive datetime is refused.

        Two instants without zones cannot be compared, and `FR-012` requires that
        a difference in instants be **visible**. An offset-naive value hides it.
        """
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise PriorityContractViolation(
                "reading_instant must carry a timezone; a naive instant cannot be compared"
            )
        return value

    @model_validator(mode="after")
    def _a_position_states_its_grounds(self) -> Self:
        """**The structural form of `FR-002` and of `SC-001`.**

        Two refusals, and the second is the one with teeth:

        1. **No components at all** — the position exists with no grounds, which is
           the ordering that *looks* measured and is not.
        2. **A component with an absence** — this type is for findings that were
           placed, and a placed finding cannot rest on an ingredient nobody
           obtained. Allowing it is how a missing component ends up contributing
           zero: the value is absent, the arithmetic needs a number, and the
           default appears one layer down where no contract is watching.
        """
        if not self.components:
            raise PriorityContractViolation(
                f"{self.finding_id!r} was placed with no components; an ordering "
                "whose grounds are not in the output must not be produced"
            )
        absent = [c.name for c in self.components if not c.is_available]
        if absent:
            raise PriorityContractViolation(
                f"{self.finding_id!r} was placed while these components are absent: "
                f"{absent}. A finding with an absent component is NotPrioritisable, "
                "never a finding ranked lower."
            )
        names = [c.name for c in self.components]
        if len(names) != len(set(names)):
            raise PriorityContractViolation(
                f"{self.finding_id!r} repeats a component name: {names}. A component "
                "counted twice weights itself twice without saying so."
            )
        return self


class NotPrioritisable(PriorityModel):
    """One candidate that could **not** be placed, and which component was missing.

    **A separate type, and that is the whole design.** A single type with an
    optional rank would let a caller sort by "rank, missing last" and reproduce the
    defect this feature exists to prevent. Two types make the silent path
    unreachable: there is nowhere to put a not-prioritisable finding *within* the
    order.
    """

    finding_id: GovernedName = Field(description="The candidate that could not be placed.")
    components: tuple[PriorityComponent, ...] = Field(
        description="What was obtained and what was not. Both, so a reader sees the gap."
    )
    reading_instant: datetime = Field(
        description="As on a placed finding, and for the same reason."
    )
    caveats: tuple[str, ...] = Field(default=(), description="Carried verbatim, as above.")

    @field_validator("reading_instant")
    @classmethod
    def _instant_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise PriorityContractViolation(
                "reading_instant must carry a timezone; a naive instant cannot be compared"
            )
        return value

    @model_validator(mode="after")
    def _at_least_one_component_is_absent_and_names_itself(self) -> Self:
        """**The mirror refusal, and it is what keeps the two types honest.**

        If a finding with every component available could be filed here, the
        distinction between *placed* and *not placeable* would be a caller's
        opinion rather than a property of the data. So: at least one component must
        be absent, and every absence must name its reason — which
        :class:`ComponentAbsence` already forces, so this only has to require that
        one exists.
        """
        if not self.components:
            raise PriorityContractViolation(
                f"{self.finding_id!r} is not prioritisable but names no component at all; "
                "the missing component must be named (FR-004)"
            )
        absent = [c for c in self.components if not c.is_available]
        if not absent:
            raise PriorityContractViolation(
                f"{self.finding_id!r} has every component available and therefore "
                "belongs in the ordering, not among the not-prioritisable"
            )
        return self

    @property
    def missing(self) -> tuple[str, ...]:
        """The names of the components that were not obtained.

        Derived rather than stored so it cannot drift from ``components``.
        """
        return tuple(c.name for c in self.components if not c.is_available)
