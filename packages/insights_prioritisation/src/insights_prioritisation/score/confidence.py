"""The confidence factor, and what it actually measures — `D-C` and `D-C1`.

**The owner decided twice, and the second decision is the one that made the first
implementable.** `D-C`: confidence is a MULTIPLIER — a big doubtful finding goes DOWN
and stays VISIBLE, it is not a veto. `D-C1`: the number is
``FreshnessRecord.completeness_ratio``, which travels on every candidate, and ``None``
**refuses** rather than standing in as 1.0.

## Why `None` refuses, in one sentence

Assuming 1.0 is the zero-substitution defect running the other way. Zero-for-absent
ranks a finding last in silence; one-for-unmeasured promotes it to full confidence in
silence, and the output looks exactly like one where completeness was measured and
found perfect. Both are a judgement wearing the clothes of a measurement.

## The declaration this module is obliged to make, and why it is not decoration

**`completeness_ratio` measures COMPLETENESS OF THE DATA. It does not measure
statistical certainty about the anomaly.** They are not the same quantity, and the
owner decided with that stated. `FR-005` forbids the silent answer, so the weighted
component **carries the name of what weighted it** — `data_completeness_ratio` — into
the output. Calling it *"confidence"* without saying what was measured is precisely the
defect this feature exists to prevent, and the name is the thing that stops it.

## Multiplied per component, never into a total

`D-A2`: the score is ``(magnitude * confidence, reach * confidence)``, compared **term
by term**. Multiplying a TOTAL would need the composed score `D-A` refuses; multiplying
each component keeps the lexicographic order intact and leaves `T014`'s tie rule — which
compares component by component and never by a composed score — untouched.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from ..contracts import ComponentAbsence, PriorityComponent, PriorityReasonCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Sequence

__all__ = ["CONFIDENCE_FACTOR_NAME", "confidence_of", "weigh"]

#: What the factor IS, carried into every weighted component. A name rather than a
#: sentence, so the output states the measurement instead of describing it.
CONFIDENCE_FACTOR_NAME = "data_completeness_ratio"


def confidence_of(finding: object) -> Decimal | None:
    """The candidate's `completeness_ratio`, exact, or ``None`` when unmeasured.

    Read through the candidate's own `freshness` record — never recomputed here, and
    never defaulted. A finding whose freshness is missing altogether answers ``None``
    for the same reason an unmeasured ratio does: **this feature did not observe it.**

    The float is converted through `str` rather than through `Decimal(float)`, because
    `Decimal(0.9)` is `0.90000000000000002220446049250313080847263336181640625` and a
    factor that arrives with invented precision makes two runs differ in the last
    digits for no reason a reader could explain.
    """
    freshness = getattr(finding, "freshness", None)
    ratio = getattr(freshness, "completeness_ratio", None)
    if ratio is None:
        return None
    return Decimal(str(ratio))


def weigh(
    components: Sequence[PriorityComponent], confidence: Decimal | None
) -> tuple[PriorityComponent, ...]:
    """Multiply every obtained component by the confidence factor, naming the factor.

    **An unmeasured confidence turns every component into a named absence**, not into
    an unweighted value. Leaving the components as they were read would publish an
    ordering that looks weighted and is not — `D-C1` decided the refusal, and this is
    where it takes effect.

    A component that was ALREADY absent stays absent with its own reason. The reason it
    carries is the more specific one: *this component could not be obtained* says more
    than *the weight could not be applied*.
    """
    weighted: list[PriorityComponent] = []
    for component in components:
        if component.value is None:
            weighted.append(component)
            continue
        if confidence is None:
            weighted.append(
                PriorityComponent(
                    name=component.name,
                    read_from=component.read_from,
                    absence=ComponentAbsence(
                        reason=PriorityReasonCode.PRIORITY_CONFIDENCE_NOT_MEASURED
                    ),
                )
            )
            continue
        weighted.append(
            PriorityComponent(
                name=component.name,
                read_from=component.read_from,
                value=component.value * confidence,
                weighted_by=CONFIDENCE_FACTOR_NAME,
            )
        )
    return tuple(weighted)
