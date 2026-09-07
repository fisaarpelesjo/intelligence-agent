"""One prioritisation run — T006 (`FR-009`, `SC-007`).

**The distinction this module exists for: "nothing deserved attention" and "the
prioritiser broke" must never look the same.**

`005` closed the same hole and it is worth restating because the shape recurs: a run
that produced nothing and a run that failed both hand back an empty collection, and
if the outcome is read from the collection's length the two become one. An operator
who cannot tell them apart learns nothing from either.

So the outcome is a **field**, and an empty ordering on a completed run is a
**result** — the answer *"nothing crossed a threshold today"*, which is actionable.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator, model_validator

from ._base import PriorityContractViolation, PriorityModel
from .ordering import Ordering
from .reason_codes import PriorityReasonCode

__all__ = ["PrioritisationRun", "RunOutcome"]


class RunOutcome(StrEnum):
    """Two outcomes, and they are not two shapes of the same thing."""

    #: The run finished. It may hold an empty ordering, and that is an answer.
    COMPLETED = "completed"

    #: The run did not finish. It carries a code saying so, and its orderings — if
    #: any — are not to be read as conclusions.
    DID_NOT_COMPLETE = "did_not_complete"


class PrioritisationRun(PriorityModel):
    """The whole result of one prioritisation.

    ``orderings`` holds one per aggregation class, or one under a declared
    normalisation. Several are the ordinary case rather than the exception —
    `FR-005` makes *one ordering per class* the default when nothing declares how
    to relate them.
    """

    outcome: RunOutcome = Field(
        description="Completed or not. A FIELD, never inferred from an empty ordering."
    )
    orderings: tuple[Ordering, ...] = Field(
        default=(), description="One per aggregation class, or one under a declared normalisation."
    )
    reason_code: PriorityReasonCode | None = Field(
        default=None, description="Set only when the run did not complete."
    )
    read_at: datetime = Field(
        description=(
            "The instant this run's inputs were read. Carried so a run's conclusions "
            "can be dated -- the source is rebuilt daily."
        )
    )

    @field_validator("read_at")
    @classmethod
    def _instant_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise PriorityContractViolation(
                "read_at must carry a timezone; a naive instant cannot be compared"
            )
        return value

    @model_validator(mode="after")
    def _the_run_defends_itself(self) -> Self:
        """Four refusals, and the pairing is what makes the outcome readable.

        1. **Completed with a reason code.** The code would describe a failure that
           did not happen, and a reader would trust the code over the outcome.
        2. **Did not complete with no code.** Then the failure has no name, and
           *"something went wrong"* is the whole report.
        3. **The wrong code.** Only ``PRIORITY_RUN_DID_NOT_COMPLETE`` belongs on a
           run: the other three describe a component or an ordering, and using one
           here is the `005` defect of a code used for something that was never its
           job.
        4. **Two orderings claiming the same class.** Then the same findings could
           be ordered twice, differently, and both would be published.
        """
        if self.outcome is RunOutcome.COMPLETED and self.reason_code is not None:
            raise PriorityContractViolation(
                f"a completed run carries no reason code, and this one carries "
                f"{self.reason_code.value!r}"
            )
        if self.outcome is RunOutcome.DID_NOT_COMPLETE and self.reason_code is None:
            raise PriorityContractViolation(
                "a run that did not complete must name why; an unnamed failure "
                "reports only that something went wrong"
            )
        if (
            self.reason_code is not None
            and self.reason_code is not PriorityReasonCode.PRIORITY_RUN_DID_NOT_COMPLETE
        ):
            raise PriorityContractViolation(
                f"{self.reason_code.value!r} describes a component or an ordering, "
                "not a run. Only PRIORITY_RUN_DID_NOT_COMPLETE belongs here."
            )

        declared = [o.aggregation_class for o in self.orderings if o.aggregation_class is not None]
        if len(declared) != len(set(declared)):
            raise PriorityContractViolation(
                f"two orderings claim the same aggregation class: "
                f"{sorted(c.value for c in declared)}. The same findings could be "
                "ordered twice and both published."
            )
        return self

    @property
    def produced_nothing(self) -> bool:
        """A completed run whose every ordering is empty.

        **This is a result and the property says so by requiring COMPLETED.** A run
        that did not complete is never "produced nothing"; it is "did not finish",
        and conflating the two is the whole point of this module.
        """
        return self.outcome is RunOutcome.COMPLETED and all(o.is_empty for o in self.orderings)
