"""Exact comparison arithmetic — T104 (FR-070; SC-040).

**Exact decimal. No binary floating point anywhere in the path.**

A float difference is not reproducible in its last digits across platforms, and
`SC-005` requires identical output for identical input. ``0.1 + 0.2`` is the
canonical demonstration, but the case that actually bites is subtler: two
warehouses returning the same decimal, one via a float column, produce figures
that differ in the sixteenth digit and compare unequal. `T105` scans the path for
a float and fails on one.

**This module rounds nothing.** Not to two places, not to the metric's declared
precision, not "for display". Any quantisation is a governed rule in
`comparison-formulas.yaml` (`D-18`), and a formula declaring one this feature
cannot apply refuses rather than being approximated — inventing a rounding here
would silently decide how every percentage in the product reads (`R-12`).

**The operations are named by the approved contract, not chosen here.**
`contracts/governed-content.md` §D-18 declares the formula ``id`` field as
``absolute_difference | ratio | percentage_change``, and
`comparison-contract.md` §7 names the same three as the closed set. So the
registry below implements exactly those and **refuses every other id** — a
formula `D-18` declares but this feature cannot compute is
``CALCULATION_NOT_SUPPORTED``, never approximated by a neighbouring one
(`FR-071`).

Each operation is an unambiguous arithmetic definition over two exact decimals:

| id | value |
|---|---|
| ``absolute_difference`` | ``primary - baseline`` |
| ``ratio`` | ``primary / baseline`` |
| ``percentage_change`` | ``(primary - baseline) / baseline * 100`` |

The ``* 100`` in the third is what the word *percentage* means — it is the
definition of the named formula, not a presentation choice, not a unit conversion
and not a quantisation. The **unit** is a separate governed matter and comes from
the formula's declared ``unit_rule``, carried verbatim.

**Division is never guarded locally.** A zero baseline is governed by `D-18`
(`FR-071`), and `formula.py` applies that rule *before* an operation runs. There
is deliberately no ``if baseline == 0`` fallback here: a local guard would be the
convention this feature is forbidden to invent, wearing a safety check's clothes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal
from types import MappingProxyType

from ..contracts._base import ContractViolation, build
from ..contracts.comparison import DerivedFigure
from ..contracts.reason_codes import InterpretationReasonCode

__all__ = [
    "OPERATIONS",
    "derive_figure",
    "to_exact",
]


def _absolute_difference(primary: Decimal, baseline: Decimal) -> Decimal:
    return primary - baseline


def _ratio(primary: Decimal, baseline: Decimal) -> Decimal:
    return primary / baseline


def _percentage_change(primary: Decimal, baseline: Decimal) -> Decimal:
    return (primary - baseline) / baseline * Decimal(100)


#: The closed set, keyed by the governed formula id. Membership here is what
#: makes "computable" a property of the code rather than a claim in a comment,
#: and `formula.py` checks a `D-18` formula against it before anything runs.
#:
#: A ``MappingProxyType`` so no caller can register a fourth operation at
#: runtime — a registrable formula set would be an ungoverned formula set.
OPERATIONS: Mapping[str, Callable[[Decimal, Decimal], Decimal]] = MappingProxyType(
    {
        "absolute_difference": _absolute_difference,
        "ratio": _ratio,
        "percentage_change": _percentage_change,
    }
)

#: Operations whose definition divides by the baseline. Named so `formula.py` can
#: ask "does a zero baseline matter here?" without re-deriving it from the
#: arithmetic — an absolute difference over a zero baseline is perfectly
#: well-defined and must not be refused as though it divided.
DIVIDING_OPERATIONS: frozenset[str] = frozenset({"ratio", "percentage_change"})


def to_exact(value: object) -> Decimal:
    """Lift a governed cell value to an exact decimal, or refuse.

    ``int`` and ``Decimal`` are the two forms `002`'s ``ResultCell`` declares, and
    both lift exactly. **``float`` is refused rather than converted**: converting
    one would produce the exact decimal of a value that was already imprecise —
    ``Decimal(0.1)`` is ``0.1000000000000000055511151231257827…`` — and the
    result would look exact while carrying the error the ban exists to prevent.

    A ``str`` is refused too. ``Decimal("1.5")`` is exact, but accepting strings
    here would let an ungoverned value reach the arithmetic through a path the
    cell contract does not sanction, and `FR-073` is explicit that nothing but
    this comparison's own executions participates.
    """
    if isinstance(value, bool):
        # Before the ``int`` branch: ``bool`` is an ``int`` in Python, and a
        # comparison over True and False is not arithmetic anybody asked for.
        raise ContractViolation(
            InterpretationReasonCode.COMPARISON_SIDE_INVALID,
            "a boolean is not a governed metric value",
        )
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    raise ContractViolation(
        InterpretationReasonCode.COMPARISON_SIDE_INVALID,
        "the side's value is not an exact numeric type; it is refused, never converted",
    )


def derive_figure(
    *,
    formula_id: str,
    unit: str,
    primary: object,
    baseline: object,
    derived_from: tuple[str, str],
    basis: str,
) -> DerivedFigure:
    """Compute the difference exactly, and record what produced it.

    ``formula_id`` must already have been resolved against `D-18` and checked for
    membership — `formula.py` owns that, and this function refuses an unknown id
    rather than trusting the caller, because an unchecked id reaching here would
    mean the governed set was bypassed.

    ``unit`` is the formula's declared ``unit_rule``, carried verbatim. This
    function neither derives nor converts it.

    ``derived_from`` names both operands' claims, so the figure is traceable to
    the two sides it came from and cannot be presented as a factual result.
    """
    operation = OPERATIONS.get(formula_id)
    if operation is None:
        raise ContractViolation(
            InterpretationReasonCode.CALCULATION_NOT_SUPPORTED,
            "the governed formula names an operation this feature cannot compute; "
            "it is refused, never approximated by a neighbouring one",
        )

    value = operation(to_exact(primary), to_exact(baseline))
    return build(
        DerivedFigure,
        value=value,
        unit=unit,
        derived_from=derived_from,
        basis=basis,
    )
