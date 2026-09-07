"""Closed-formula membership and the governed zero baseline — T106 (FR-071; SC-040).

    **DO NOT INVENT A ROUNDING OR ZERO-BASELINE RULE** — `tasks.md` T106

That instruction is the whole design. Four things about a comparison formula are
governed content and **none of them is decided here**: which formulas exist,
what unit each produces, what happens at a zero baseline, and whether any
quantisation applies. This module resolves them from `D-18` and refuses whenever
the answer is absent, ambiguous or something it cannot execute.

## Two independent gates, both closed

1. **`D-18` must declare the formula.** The effective formula set is resolved
   through `governance/vocabulary.py`; an id it does not list refuses
   ``CALCULATION_NOT_SUPPORTED``. The set ships empty, so **today every
   comparison refuses at this gate** — designed, not missing.
2. **This feature must be able to compute it.** `compute.py`'s registry
   implements the three ids `contracts/governed-content.md` names. A `D-18`
   formula outside it refuses too.

Both directions matter. The first stops a formula nobody approved from running;
the second stops an approved formula from being quietly approximated by a
neighbouring operation that happens to be implemented.

## The zero baseline

`D-18` requires every formula to declare a ``zero_baseline`` rule, because every
formula has *some* behaviour there and something has to say which. What this
feature can then do with the declared rule is bounded by the contract:
``DerivedFigure.value`` is a required ``Decimal``, so a comparison either
produces a number or does not exist. There is no representation for "undefined",
"infinite" or "not applicable".

So exactly one declared rule is executable — :data:`REFUSE_RULE` — and every
other declared rule refuses as *unrecognised*. The two refusals are deliberately
distinguishable in their detail, because they mean different things: one is the
governed rule being applied, the other is this feature admitting it cannot apply
the governed rule. Collapsing them would hide a contract gap behind a governance
decision.

**No local default.** Nothing here divides by zero defensively, substitutes a
zero, yields a null or reports "new". The rule comes from the content or the
comparison refuses.

## Quantisation

``quantisation`` is optional on the schema because *no governed rounding* is a
legitimate governed decision. A formula that **does** declare one refuses: this
feature applies no presentation rounding, and applying a governed rounding rule
would require interpreting its wording — which is inventing a rounding rule with
extra steps.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from ..contracts._base import ContractViolation
from ..contracts.reason_codes import InterpretationReasonCode
from ..governance.vocabulary import resolve_comparison_formulas
from .compute import DIVIDING_OPERATIONS, OPERATIONS

if TYPE_CHECKING:  # pragma: no cover - typing only
    from datetime import date

    from ..governance.schemas import ComparisonFormula, ComparisonFormulas

__all__ = [
    "EXECUTABLE_ZERO_BASELINE_RULES",
    "REFUSE_RULE",
    "assert_baseline_is_usable",
    "resolve_formula",
]

#: The one zero-baseline rule this feature can carry out: refuse the comparison.
#: Named as a constant rather than written inline so `T106`'s suite can assert
#: *which* rule is executable, and so the set below cannot grow by accident.
REFUSE_RULE = "refuse_comparison"

#: The closed executable set. One member, for the reason the module docstring
#: gives: ``DerivedFigure.value`` is a required ``Decimal``, so "produce no
#: number but still return a comparison" is not a representable outcome. Widening
#: this set requires widening the contract first, in that order.
EXECUTABLE_ZERO_BASELINE_RULES: frozenset[str] = frozenset({REFUSE_RULE})


def resolve_formula(
    formula_id: str,
    *,
    on: date,
    instances: tuple[ComparisonFormulas, ...] | None = None,
) -> ComparisonFormula:
    """The governed formula, if `D-18` declares it and this feature can compute it.

    Raises ``ContentUnresolvable`` — carrying
    ``INTERPRETATION_VOCABULARY_UNRESOLVABLE`` — when no single complete formula
    set is in force. That covers the shipped state (**zero effective
    instances**), the ambiguous state (**more than one**), and the incomplete
    state (**an effective set declaring no formula**). All three refuse, and none
    substitutes a previously effective set.

    ``instances`` is injectable **for fixtures only**. It is not a runtime
    switch: no `src/` module supplies one, and the fixture-containment scan
    asserts it.
    """
    governed = resolve_comparison_formulas(on, instances=instances)

    declared = {formula.id: formula for formula in governed.formulas}
    formula = declared.get(formula_id)
    if formula is None:
        # The detail names no formula id from the governed set. A refusal that
        # listed what *is* available would disclose governed content to a caller
        # who asked for something else.
        raise ContractViolation(
            InterpretationReasonCode.CALCULATION_NOT_SUPPORTED,
            "the requested comparison is not a governed formula; "
            "it is refused, never approximated by one that is",
        )

    if formula.id not in OPERATIONS:
        raise ContractViolation(
            InterpretationReasonCode.CALCULATION_NOT_SUPPORTED,
            "the governed formula names an operation this feature cannot compute",
        )

    if formula.quantisation is not None:
        raise ContractViolation(
            InterpretationReasonCode.CALCULATION_NOT_SUPPORTED,
            "the governed formula declares a quantisation this feature does not apply; "
            "no rounding is invented in its place",
        )

    if formula.zero_baseline not in EXECUTABLE_ZERO_BASELINE_RULES:
        raise ContractViolation(
            InterpretationReasonCode.CALCULATION_NOT_SUPPORTED,
            "the governed zero-baseline rule is not one this feature can carry out; "
            "no local behaviour is substituted for it",
        )

    return formula


def assert_baseline_is_usable(formula: ComparisonFormula, baseline: Decimal) -> None:
    """Apply the governed zero-baseline rule. **No local guard.**

    Only formulas that divide by the baseline can reach a zero-baseline
    condition, so an absolute difference over a zero baseline proceeds — refusing
    it would be this feature inventing a restriction the arithmetic does not have
    and the governed rule does not state.

    When the condition *is* reached, the declared rule decides. Today the only
    executable rule refuses, so the comparison refuses — and the detail says the
    governed rule was applied, distinguishing it from ``resolve_formula``'s
    refusal for a rule this feature could not carry out at all.
    """
    if formula.id not in DIVIDING_OPERATIONS:
        return
    if baseline != Decimal(0):
        return
    raise ContractViolation(
        InterpretationReasonCode.CALCULATION_NOT_SUPPORTED,
        "the baseline is zero and the governed zero-baseline rule refuses the comparison",
    )
