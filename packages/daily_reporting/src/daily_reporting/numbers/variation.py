"""How much a KPI moved, and **in which unit** — `T814`, `T815`.

## The unit is not a style choice

> *"Chargeback rose 1,4 point, from 1,4 % to 2,8 %"* reads.
> *"It rose 76 %"* does not.

And percentage points are meaningless for a volume: **there is no percentage point of
748 trials.** So a **rate** moves in percentage points and a **volume or a sum of
money** moves in relative percent — `FR-810`, the owner's decision `OD-14-D`.

## The decision's only input is the format, which is what makes it derived

:func:`variation_unit_for` takes ``format_type`` and **nothing else**. It cannot see
the KPI's name, so it cannot special-case one; a node asserts that over the signature
rather than trusting this paragraph. A function that could see the name would be one
edit away from a table of twenty exceptions, which is `FR-810` lost quietly.

## And nothing is converted between currencies

`FR-807`. `semantic/metrics/new_trials.yaml` records why: the view keeps the two
currencies in separate columns and **holds no exchange rate**, so a converted figure
would depend on a rate the reader chooses — and a number that depends on a parameter is
not a number this catalog may declare. Each money KPI is reported in its own currency,
which its own name already carries.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Final

__all__ = [
    "RATE_FORMAT",
    "VALUE_UNIT_MARKS",
    "WHOLE_FORMATS",
    "VariationUnit",
    "as_percent",
    "value_unit_for",
    "variation_between",
    "variation_unit_for",
]

#: The format the owner's view uses for a rate. **One marker, not twenty names** — the
#: difference between reading the source's vocabulary and authoring a table.
RATE_FORMAT: Final = "pct"

#: The source's formats whose numbers count WHOLE THINGS — `OD-35`. His question was the
#: argument: *"e pq casas decimais, e nao e valor, mas sim, numeros absolutos?"*. There is no
#: half trial and no half subscriber.
#:
#: **It lives HERE and not in the rendering module, for the same reason `RATE_FORMAT` does**:
#: these are the SOURCE's words, and the node that counts authored strings watches the
#: modules a reader's eyes reach. Keeping source vocabulary out of those modules is what
#: lets that guard keep its teeth instead of being widened to admit it.
WHOLE_FORMATS: Final[frozenset[str]] = frozenset({"int", "k"})

#: What one of this KPI's numbers IS, by the source's own `format_type` — `OD-42`. A rate
#: carries the per-cent sign, money carries its currency, and a count carries nothing because
#: what it counts is the KPI's own label. **Derived, never chosen per line**, and it lives
#: here with the rest of the source's vocabulary rather than in a module a reader's eyes reach
#: -- the same door the number format went through when the authored-strings node bit.
_VALUE_UNITS: Final[dict[str, str]] = {
    "pct": "%",
    "brl": "R$",
    "usd_k": "US$",
    "usd_m": "US$",
    "usd_avg": "US$",
}


#: The same governed set under its public name — condition 4 of `ADR 0036` reads it as the
#: fourth vocabulary (2026-09-01), and a private name crossing modules is a lie about custody.
VALUE_UNIT_MARKS: Final[dict[str, str]] = _VALUE_UNITS


def value_unit_for(format_type: str) -> str:
    """The unit the VALUE carries, or empty when the number is a bare count."""
    return _VALUE_UNITS.get(format_type.strip().lower(), "")


def as_percent(value: Decimal, format_type: str) -> Decimal:
    """A rate read at the scale its own `%` sign claims — and **the scale is measured**.

    The view stores a rate as a FRACTION OF ONE: on 2026-08-30 the four `Plan share` rates
    summed to exactly `1.0` for the closed day, not to `100`, and `Trial conversion (%)` read
    `0.0140` where an independent measurement of the same day read `1,40`.

    So a value carrying a per-cent sign has to be read at that scale, or the report states
    something false: `Cancellations (%)` went out as `0,00 %` when the rate is `0,24 %`.
    **This is not a rescaling of the source's number — it is reading the source's own scale**,
    and the alternative was a `%` sign over a fraction, which is the label-and-number mismatch
    this feature has now paid for four times.
    """
    return value * Decimal(100) if format_type.strip().lower() == RATE_FORMAT else value


#: Where the conversion belongs, said once: **at the read**. Everything downstream -- the
#: value, the variation in points, the threshold over the series -- then works in one scale,
#: and no module has to know whether its input was converted already.


class VariationUnit(StrEnum):
    """The two units a movement may be expressed in, and they never mix.

    ## The values are HIS WORDS, and they used to be ours

    They were `percentage_points` and `relative_percent` — **internal names leaking into
    the text a person reads**. The `ADR 0036` wording condition caught them by refusing a
    correct report, because they belong to no vocabulary the reader was promised: not the
    source's labels, not the two words of `OD-15`.

    `OD-20-C` decided the words: a rate that moves from 3 % to 5 % prints **"+2 pontos
    percentuais"**, and a volume that moves from 100 to 120 prints **"+20 %"**. The
    point-versus-relative distinction was already his, from `OD-14-D`; what he chose now is
    **the word**.
    """

    #: For a rate. The arithmetic is a subtraction: 2,8 % less 1,4 % is 1,4 points.
    #: **`pp` since 2026-08-30, by `OD-39`**, looking at the twenty-line preview: *"0,00
    #: pontos percentuais / coloca como pp, melhor"*. Eighteen characters became two on
    #: almost every rate line, and the variation column came back next to the number it
    #: describes. `OD-20-C` stands in what it actually decided -- the DISTINCTION between a
    #: point of a rate and a relative movement; only the spelling moved.
    PERCENTAGE_POINTS = "pp"

    #: For a volume or a sum of money. The arithmetic is a ratio against the previous
    #: value, which is undefined when that value is zero — and `None` is what this
    #: module answers there, rather than a number nobody measured.
    RELATIVE_PERCENT = "%"


def variation_unit_for(format_type: str) -> VariationUnit:
    """The unit a KPI of this format moves in. **Its only input is the format.**"""
    return (
        VariationUnit.PERCENTAGE_POINTS
        if format_type.strip().lower() == RATE_FORMAT
        else VariationUnit.RELATIVE_PERCENT
    )


def variation_between(
    previous: Decimal,
    current: Decimal,
    unit: VariationUnit,
) -> Decimal | None:
    """How far ``current`` moved from ``previous``, in ``unit``.

    Answers ``None`` when the movement is **undefined** rather than zero: a volume that
    was zero last week has no relative change this week, and reporting `0` there would
    state that nothing happened when what happened cannot be expressed this way. The
    KPI still appears in the report — `FR-815` — with its value and no variation.
    """
    if unit is VariationUnit.PERCENTAGE_POINTS:
        #: The raw difference, **and the scaling is NOT done here**. A rate is stored as a
        #: fraction of one in this view -- measured on 2026-08-30, the four `Plan share` rates
        #: sum to exactly `1.0` -- so somebody has to read it at the scale its `%` claims.
        #: **That happens ONCE, where the source is read**, and doing it here as well would
        #: multiply by a hundred twice for a caller that had already converted.
        return current - previous
    if previous == 0:
        return None
    try:
        return (current - previous) / previous * Decimal(100)
    except (InvalidOperation, ZeroDivisionError):  # pragma: no cover - guarded above
        return None
