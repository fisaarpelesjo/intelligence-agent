"""The metric's declared direction — T007 (`FR-003`).

**Whether a movement is GOOD or BAD is a property of the metric, and this module
refuses to guess it.** A 12% fall in trials and a 12% rise in cancellations are the
same kind of bad; a 12% fall in cancellations is good. Nothing about the *number*
says which, and inferring it from the sign is the defect this file exists to make
impossible.

## The distinction that this module is entirely about

`003` already has a `Direction` — `INCREASE`, `DECREASE`, `NO_MOVEMENT` — and `005`
carries it on every candidate. **That is the direction of the MOVEMENT, derived
from the sign of a difference.** It is not the direction this module reads.

What this reads is the metric's **polarity**: whether lower is better. Those two
compose into "is this bad", and confusing them would let a rise be called bad
because it is a rise.

## The catalog now declares it, and this reader still cannot reach it

**That sentence used to read the other way, and the change is measured.** Until
2026-09-04 the property had no governed home: it lived in the warehouse column `004`
measured, and `006`'s own § 3 requires direction to be *declared by the source*, so
every metric came back ``PRIORITY_DIRECTION_NOT_DECLARED`` honestly.

`D-1303` gave it a home on 2026-09-04. `MetricVersion` carries `lower_is_better`, and
twenty of the catalog's metrics state it. **This module still answers absence for all
of them**, because the declaration sits on the VERSION and the reader below does a flat
lookup on whatever object it is handed — and `load_catalog` hands back the top-level
`Metric`, which does not carry it.

That gap is measured, not assumed: `test_the_catalog_does_declare_a_direction_and_this_
reader_cannot_reach_it` asserts both halves and goes red the day the reader descends.
**Closing it is not a one-line change**, which is why it is written down instead of done
here: reaching into ``.versions`` means deciding WHICH version answers, and that is an
as-of question with a governance answer, not a `getattr`.

## Why it refuses instead of falling back to the warehouse column

Reading `lower_is_better` straight from the view would be this feature acquiring a
governed fact through a side door: which metric the column belongs to, and whether that
mapping is approved, are exactly what the catalog is for. That argument is what `D-1303`
eventually agreed with — the fact moved INTO the catalog rather than this module reaching
out to the warehouse. `005` learned the same lesson from the other end: a figure measured
correctly against an ungoverned source is still ungoverned.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import Field

from ..contracts import (
    ComponentAbsence,
    PriorityModel,
    PriorityReasonCode,
)

__all__ = ["DeclaresDirection", "MetricDirection", "read_direction"]

#: The field names a governed declaration of polarity could plausibly carry, in the
#: order a reader should try them.
#:
#: **A tuple rather than one name, and that is not hedging.** It was written when the
#: field did not exist and its name was not decided. `D-1303` has since picked
#: `lower_is_better`, which was already first in this tuple; the other two stay because
#: removing them would narrow the lookup for no measured gain, and each is a word this
#: repository already uses for the idea -- the first is the warehouse column `004`
#: measured, and the other two are the words `006`'s own spec uses.
#:
#: **The set does NOT grow to make a metric resolve.** A catalog that declares
#: polarity under a fourth name is a governance decision, and adding it here is a
#: line in a review rather than a convenience.
DECLARATION_NAMES: tuple[str, ...] = ("lower_is_better", "direction", "polarity")


class DeclaresDirection(Protocol):
    """The shape this module reads. Deliberately narrow.

    A protocol rather than `001`'s `Metric`, for the reason `005`'s ports give: it
    states what is needed and nothing more, so the day the field arrives this module
    reads it without also acquiring the rest of the catalog's surface.
    """

    name: str


class MetricDirection(PriorityModel):
    """Whether lower is better for this metric, or why that is unknown.

    **Declared or absent, never partially either**, the shape `005`'s resolutions
    use: one that resolved carries the polarity and the field it was read from; one
    that did not carries an absence naming itself.
    """

    metric: str = Field(min_length=1)
    lower_is_better: bool | None = Field(
        default=None,
        description="From the catalog. Present exactly when the metric declares it.",
    )
    read_from: str | None = Field(
        default=None,
        description=(
            "The field the value came from, so an ordering can be traced back to a "
            "declaration rather than to this module."
        ),
    )
    absence: ComponentAbsence | None = Field(
        default=None, description="Present exactly when the metric declares no direction."
    )

    @property
    def is_declared(self) -> bool:
        """Whether a direction was found. Never *"whether it is safe to guess"*."""
        return self.lower_is_better is not None


def read_direction(metric: DeclaresDirection) -> MetricDirection:
    """Find the metric's declared polarity, or say it declares none.

    **Reads, and does not compute.** There is no branch here that looks at a figure,
    a difference or a sign — the whole point of `FR-003` is that no arithmetic can
    reach this answer, and the way that is kept is that no number is passed in.

    Returns an absence rather than raising, because a run reports per finding and an
    exception would end the run for every other metric alongside it — the same shape
    `005`'s `method_or_refusal` uses and for the same reason.
    """
    for field in DECLARATION_NAMES:
        value = getattr(metric, field, None)
        if isinstance(value, bool):
            return MetricDirection(metric=metric.name, lower_is_better=value, read_from=field)

    return MetricDirection(
        metric=metric.name,
        absence=ComponentAbsence(reason=PriorityReasonCode.PRIORITY_DIRECTION_NOT_DECLARED),
    )
