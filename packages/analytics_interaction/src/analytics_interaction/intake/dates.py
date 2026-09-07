"""Two dates, two purposes, no derivation — T055 (FR-096, FR-097; SC-056, SC-057).

| Field | Resolves | Never affects |
|---|---|---|
| ``reference_date`` | relative and named period expressions | version resolution |
| ``as_of`` | metric-definition version resolution | period resolution |

**Neither defaults from the other, in either direction** (`FR-097`). That is
enforced here by making the crossing *unexpressible* rather than forbidden: the
two accessors below each return one date and take no argument that could supply
the other. A function that wanted to fill an absent ``as_of`` from the reference
date would have to be written somewhere else, and `T055`'s tests plus the
static guard in `T056` would both notice.

**No clock, anywhere on this path** (`FR-099`). ``reference_date`` is supplied by
the caller and is required unconditionally. A conditional field would need the
text parsed to know whether it applies — putting a parse before a validation and
making the contract's validity depend on the text it carries (`R-9`) — and a
defaulted one would make every relative-period answer silently depend on when it
happened to run.

**An omitted ``as_of`` means current-definition resolution**, matching `002`
exactly. That is a resolution *policy*, not a value, so nothing is filled in:
``version_pin`` returns ``None`` and the downstream resolver reads that as
"current", which is what `002` already does.

This module performs **no date arithmetic**. Applying a `D-18` period rule
happens through `001`'s canonical-period machinery (`R-8`), so IANA resolution
and the pre-2019 daylight-saving transitions stay `001`'s.
"""

from __future__ import annotations

from datetime import date

from ..contracts._base import InteractionModel
from ..contracts.intake import QuestionIntake

__all__ = [
    "IntakeDates",
    "intake_dates",
    "period_anchor",
    "version_pin",
]


class IntakeDates(InteractionModel):
    """The two dates, carried together and kept apart.

    Together, because both are disclosed on every response and both enter the
    interpretation identity — the same sentence under a different reference date
    is a different interpretation rather than a collision (`FR-098`).

    Apart, because they answer different questions. The type exists so that
    "these two travel as a pair" is expressible without either becoming a
    fallback for the other.
    """

    reference_date: date
    as_of: date | None = None


def intake_dates(intake: QuestionIntake) -> IntakeDates:
    """Lift the two dates off a parsed intake, unchanged.

    A straight carry. No normalisation, no timezone shift, no coercion — the
    caller's dates are the dates the answer will disclose.
    """
    return IntakeDates(reference_date=intake.reference_date, as_of=intake.as_of)


def period_anchor(dates: IntakeDates) -> date:
    """What relative and named period expressions resolve against.

    Returns ``reference_date`` and only ever ``reference_date``. There is no
    branch, no fallback and no parameter that could introduce one: if the
    reference date were ever absent the contract would already have refused,
    because it is required.
    """
    return dates.reference_date


def version_pin(dates: IntakeDates) -> date | None:
    """What metric-definition version resolution is pinned to.

    Returns ``as_of``, and ``None`` when the caller omitted it. **The ``None`` is
    the answer**, not a gap to be filled: it means current-definition resolution,
    which is `002`'s own behaviour carried through. Substituting
    ``reference_date`` here would silently pin every question to the day it was
    asked about rather than to the definitions in force.
    """
    return dates.as_of
