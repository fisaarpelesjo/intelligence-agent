"""Source versus dimension value — T075 (FR-011; SC-012).

``google_play`` is simultaneously a governed **source id** and a governed
**store dimension value**. When the question does not determine which one the
user meant, the system **clarifies rather than choosing** (`FR-011`, spec `US5`
scenario 4).

**This is ambiguity in the governed vocabulary itself**, not a parsing weakness.
Resolving it by convention — "prefer source" — would silently answer a different
question roughly half the time, and the user would have no way to tell which.

The disambiguation is **structural**, decided by what else the question already
resolved rather than by weighing the words:

| Situation | Role |
|---|---|
| The term sits where a source belongs and no store dimension resolved | ``source`` |
| A ``store`` dimension resolved and the term is one of its values | ``dimension_value`` |
| Both readings survive | **ambiguous** — clarify, never choose |

Note the asymmetry with the fill order: `slots.py` fills ``source`` before
``dimension_value`` precisely so this function usually has the evidence it needs
by the time the value slot is reached.

**Clarification is unavailable today.** `D-21` is undeclared, so an ambiguous
role refuses with ``SLOT_ROLE_AMBIGUOUS`` instead of clarifying. That is the
designed fail-closed behaviour, not a gap: the alternative is guessing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..contracts._base import ContractViolation
from ..contracts.intent import SlotKind
from ..contracts.reason_codes import InterpretationReasonCode

__all__ = [
    "RoleReading",
    "RoleVerdict",
    "resolve_role",
]


class RoleReading(StrEnum):
    """Which governed role a term was read as."""

    SOURCE = "source"
    DIMENSION_VALUE = "dimension_value"


@dataclass(frozen=True, slots=True)
class RoleVerdict:
    """The reading, and the governed slot it fills.

    A frozen record rather than a bare enum so a caller cannot reconstruct the
    slot from the reading with a mapping of its own and get it subtly wrong.
    """

    reading: RoleReading
    slot: SlotKind


_SOURCE_VERDICT = RoleVerdict(reading=RoleReading.SOURCE, slot=SlotKind.SOURCE)
_VALUE_VERDICT = RoleVerdict(reading=RoleReading.DIMENSION_VALUE, slot=SlotKind.DIMENSION_VALUE)


def resolve_role(
    term: str,
    *,
    governed_source_ids: frozenset[str],
    dimension_values: frozenset[str],
    resolved_dimensions: frozenset[str],
) -> RoleVerdict:
    """Which role ``term`` fills, or refuse as ambiguous.

    ``governed_source_ids`` and ``dimension_values`` come from `001`'s
    access-filtered surface — this module authors neither, and a term absent
    from both is not this function's problem: it never resolved, so there is no
    role to decide.

    ``resolved_dimensions`` is what the question already established. It is the
    only disambiguating evidence used, and it is deliberately narrow: anything
    richer would be inferring intent from phrasing, which is the guess this
    function exists to avoid.

    The four cases are exhaustive:

    * neither — ``TERM_NOT_GOVERNED``. Nothing to disambiguate;
    * source only — the source reading;
    * value only — the value reading, and only when its dimension resolved;
    * both — ambiguous, unless a dimension the value belongs to already
      resolved, which settles it.
    """
    is_source = term in governed_source_ids
    is_value = term in dimension_values

    if not is_source and not is_value:
        raise ContractViolation(
            InterpretationReasonCode.TERM_NOT_GOVERNED,
            "the term names neither a governed source nor a governed dimension value",
        )

    if is_source and not is_value:
        return _SOURCE_VERDICT

    if is_value and not is_source:
        if not resolved_dimensions:
            # A value with no dimension behind it is a value of nothing. Refusing
            # here rather than guessing the dimension keeps `permitted_values`
            # the dimension's property, not the question's.
            raise ContractViolation(
                InterpretationReasonCode.TERM_NOT_GOVERNED,
                "a dimension value cannot resolve before its dimension does",
            )
        return _VALUE_VERDICT

    # Both readings are governed. Only an already-resolved dimension settles it.
    if resolved_dimensions:
        return _VALUE_VERDICT

    raise ContractViolation(
        InterpretationReasonCode.SLOT_ROLE_AMBIGUOUS,
        "the term is both a governed source and a governed dimension value, and "
        "the question does not determine the role",
    )
