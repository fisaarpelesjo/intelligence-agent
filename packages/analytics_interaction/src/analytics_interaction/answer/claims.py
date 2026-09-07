"""The four typed claim classes — T124 (FR-034; SC-009).

**Every element carries a class, enforced by type rather than by tag.**

A tag on prose would make `SC-009` a text-inspection exercise — somebody reading
answers and judging whether a sentence sounded like a finding. A type makes it a
contract test, and it structurally prevents an interpretation from reading as a
number: ``INTERPRETATION`` and ``LIMITATION`` cannot carry a value or a unit,
because ``AnswerClaim``'s own validator refuses one.

| Class | Source | Carries a number? |
|---|---|---|
| ``FACTUAL_RESULT`` | a governed result cell, unaltered | yes |
| ``CALCULATED_COMPARISON`` | deterministic arithmetic over two results | yes, derived |
| ``INTERPRETATION`` | what the system understood the question to mean | **no** |
| ``LIMITATION`` | an upstream caveat, suppression note or insufficiency | **no** |

## One constructor per class, and no general one

There is deliberately no ``claim(class_, ...)``. A single constructor taking the
class as a parameter would let a caller build a ``FACTUAL_RESULT`` from a value
it computed, or an ``INTERPRETATION`` that quietly carried a figure — the four
functions below each accept only what their class may hold, so the wrong
combination has no way to be expressed.

:func:`factual` in particular takes a ``ResultCell`` rather than a number. That
is the whole of `FR-033`: the value is **read off a governed result**, never
passed in, so no arithmetic can have happened to it on the way. A suppressed or
absent cell refuses rather than producing a claim about nothing.

## Every message is a pointer

``message`` is a ``LocalizedRef`` — a ``(code, language, content_version)``
triple resolved against governed content at render time. No string is generated,
concatenated from the question, paraphrased or translated (`FR-039`), which is
what makes byte-identity across repeats (`SC-028`) a property of the design
rather than a discipline somebody maintains.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..contracts._base import ContractViolation, LocalizedRef, build
from ..contracts.answer import AnswerClaim, ClaimClass
from ..contracts.reason_codes import InterpretationReasonCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from decimal import Decimal

    from analytics_query.contracts.result import AnalyticsResult, ResultCell

    from ..contracts.answer import ComparisonBasis

__all__ = [
    "calculated",
    "factual",
    "interpretation",
    "limitation",
    "wording_ref",
]


def wording_ref(code: str, *, language: str, content_version: str) -> LocalizedRef:
    """A pointer into governed content. **The only way a claim gets words.**

    A named constructor rather than an inline ``LocalizedRef`` so every message
    on the answer path goes through one place — and so a future reader looking
    for "where does the text come from" finds a function rather than a dozen
    literals.
    """
    return LocalizedRef(code=code, language=language, content_version=content_version)


def factual(
    *,
    subject: str,
    cell: ResultCell,
    unit: str,
    message: LocalizedRef,
) -> AnswerClaim:
    """A warehouse figure, carried unaltered.

    Takes the **cell**, not a number. `FR-033` forbids this feature from
    recomputing a result, and passing a value in would make that unobservable —
    a caller could compute anything and label it factual. Reading it off the
    governed cell means the only figure expressible here is one `002` returned.

    A suppressed or absent cell refuses. A claim built over a withheld value
    would be a factual assertion about a number nobody is allowed to see, and
    substituting zero would fabricate it.
    """
    if cell.suppressed or cell.value is None:
        raise ContractViolation(
            InterpretationReasonCode.DISCLOSURE_WOULD_RECONSTRUCT,
            "a factual claim cannot be made over a withheld or absent value",
        )

    return build(
        AnswerClaim,
        claim_class=ClaimClass.FACTUAL_RESULT,
        subject=subject,
        value=cell.value,
        unit=unit,
        message=message,
    )


def calculated(
    *,
    subject: str,
    value: Decimal,
    unit: str,
    message: LocalizedRef,
    derived_from: tuple[str, str],
    basis: ComparisonBasis,
) -> AnswerClaim:
    """A deterministic difference, marked derived and traceable to both operands.

    ``derived_from`` and ``basis`` are required by the contract for this class
    alone: a factual result derives from the warehouse, and letting one claim to
    derive from two others would make `FR-033`'s prohibition unobservable.

    The value arrives already computed — Phase 10 owns the arithmetic, and
    recomputing it here would be a second implementation free to disagree with
    the first.
    """
    return build(
        AnswerClaim,
        claim_class=ClaimClass.CALCULATED_COMPARISON,
        subject=subject,
        value=value,
        unit=unit,
        message=message,
        derived_from=derived_from,
        basis=basis,
    )


def interpretation(*, subject: str, message: LocalizedRef) -> AnswerClaim:
    """What the system understood the question to mean. **Carries no number.**

    Structurally, not by convention: the contract refuses a value or a unit on
    this class, so an interpretation cannot be mistaken for a finding however it
    is rendered downstream.
    """
    return build(
        AnswerClaim,
        claim_class=ClaimClass.INTERPRETATION,
        subject=subject,
        message=message,
    )


def limitation(*, subject: str, message: LocalizedRef) -> AnswerClaim:
    """An upstream caveat, suppression note or insufficiency. **Carries no number.**

    Distinct from ``caveats``: the caveat set is the prominent, counted surface
    `FR-085` requires, while a limitation claim is how a limitation appears
    *among the claims* when the answer states one. Neither substitutes for the
    other, and burying a caveat here instead of in the caveat set is exactly what
    `T127`'s counting makes detectable.
    """
    return build(
        AnswerClaim,
        claim_class=ClaimClass.LIMITATION,
        subject=subject,
        message=message,
    )


def cell_for(result: AnalyticsResult) -> ResultCell:
    """The one metric cell a single-figure result carries.

    Exactly one row and one metric cell, or refuse. A breakdown is not a single
    figure, and picking a row would be this feature choosing which one the answer
    is about.
    """
    metrics = [column for column in result.columns if column.is_metric]
    if len(result.rows) != 1 or len(metrics) != 1:
        raise ContractViolation(
            InterpretationReasonCode.INTENT_AMBIGUOUS,
            "a single-figure claim needs exactly one row and one metric column",
        )
    (row,) = result.rows
    if len(row.cells) != 1:
        raise ContractViolation(
            InterpretationReasonCode.INTENT_AMBIGUOUS,
            "the row does not carry exactly its one metric cell",
        )
    return row.cells[0]
