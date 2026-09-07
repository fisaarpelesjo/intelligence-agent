"""Operator abstention — T077 (FR-011; SC-012).

`002` declares a **closed operator allowlist**: ``eq``, ``ne``, ``in``,
``not_in``, ``between``. A question needing anything else — greater-than,
contains, starts-with, regex, like — **abstains**.

    Never approximated with a permitted operator. — `tasks.md` T077

That prohibition is the whole content of this module, and it is worth stating why
approximation is so tempting and so wrong. "vendas acima de 1000" has an obvious
near-translation into ``between(1000, <some ceiling>)``, and the ceiling would be
invented. "país que contém 'bras'" has an obvious near-translation into
``in(...)`` over a guessed value list. Both would return a number, and neither
would answer the question asked — the user would have no way to tell, because the
answer would look exactly like a correct one.

So there is **no approximation path here at all**. Not a disabled one, not a
flagged one: the function returns a governed operator or raises, and no branch
maps an ungoverned operator to a permitted one.

The allowlist is imported from `002`'s public contract rather than restated. A
second copy would eventually disagree with the one the request contract actually
enforces, and the disagreement would surface as a request rejected downstream
after this layer had already told the user it was fine.
"""

from __future__ import annotations

from analytics_query.contracts.operators import OPERATOR_ARITY, Arity, GovernedOperator

from ..contracts._base import ContractViolation
from ..contracts.reason_codes import InterpretationReasonCode

__all__ = [
    "GOVERNED_OPERATORS",
    "arity_of",
    "require_governed_operator",
]

#: The closed allowlist, derived from `002`'s enum.
GOVERNED_OPERATORS: frozenset[str] = frozenset(op.value for op in GovernedOperator)


def require_governed_operator(operator: str) -> GovernedOperator:
    """The governed operator, or abstain.

    Matched on the exact governed spelling. No case folding, no aliasing, no
    "equals" → ``eq`` convenience: each of those is a small approximation, and
    the point of this module is that there are none.
    """
    try:
        return GovernedOperator(operator)
    except ValueError as exc:
        raise ContractViolation(
            InterpretationReasonCode.CALCULATION_NOT_SUPPORTED,
            "the comparison the question needs is outside the governed operator "
            "set and is never approximated with a permitted one",
        ) from exc


def arity_of(operator: GovernedOperator) -> Arity:
    """How many values ``operator`` takes, per `002`'s matrix.

    Exposed so an interpretation can tell "this operator needs two values" from
    "this question supplied two values" without re-deriving `002`'s table.
    """
    return OPERATOR_ARITY[operator]
