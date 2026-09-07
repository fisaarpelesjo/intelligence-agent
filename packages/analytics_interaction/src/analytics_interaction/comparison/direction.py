"""Whether a comparison went up, down or nowhere. The one piece the arithmetic did not have.

Authorized by the owner on 2026-08-20: a comparison must report "aumento", "queda" or
"estabilidade", and the model must **receive** that rather than decide it.

## Why this is a separate module and three lines of arithmetic

Measured before writing it: `compute.py` already owns the three operations — absolute
difference, ratio and percentage change — in a closed `MappingProxyType`, over `Decimal`, with
`float` refused rather than converted. `formula.py` already applies the governed zero-baseline
rule, and refuses only the operations that actually divide. None of that needed rewriting, and
rewriting it would have put a second definition of "percentage change" in the repository.

What none of them had is the **word**. A difference of `-3` is a fact; calling it a fall is a
reading of that fact, and the reading has to be deterministic for the same reason the arithmetic
does: a model asked to look at `-3` and say whether that is a decline will usually be right, and
"usually" is not a property an answer can carry.

## Stability is a judgement, so it is a parameter

Zero difference is stable and needs no threshold. Anything else does: a change of one install in ten
million is arithmetically an increase and editorially noise. `tolerance` is therefore explicit and
defaults to zero — the only value this feature can justify on its own. A deployment that wants "±2%
counts as stable" states it, and the answer discloses the tolerance that was applied, because a
threshold nobody sees is a threshold nobody agreed to.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

__all__ = ["Direction", "classify_direction"]


class Direction(StrEnum):
    """The three readings, and there is no fourth.

    A closed set rather than a signed number so an answer states a word a reader understands, and so
    "no movement" is a distinct outcome rather than the absence of one.
    """

    INCREASE = "increase"
    DECREASE = "decrease"
    STABLE = "stable"


def classify_direction(difference: Decimal, *, tolerance: Decimal = Decimal(0)) -> Direction:
    """Read a signed difference as a direction. Total, deterministic, no clock and no rounding.

    ``difference`` is primary minus baseline, which is what `compute.OPERATIONS`'
    ``absolute_difference`` produces — so the sign convention is inherited rather than restated, and
    a caller cannot get it backwards by passing the operands the other way round without also
    getting the number backwards.

    ``tolerance`` is compared against the **absolute** difference, so it is symmetric by
    construction: a band that called `+5` stable and `-5` a fall would be a band that flattered
    growth.

    A negative tolerance is refused rather than clamped. It would mean "nothing is ever stable",
    which is expressible with zero, so a negative value is a caller mistake and not a preference.
    """
    if tolerance < 0:
        raise ValueError(f"a stability tolerance cannot be negative; got {tolerance}")
    if abs(difference) <= tolerance:
        return Direction.STABLE
    return Direction.INCREASE if difference > 0 else Direction.DECREASE
