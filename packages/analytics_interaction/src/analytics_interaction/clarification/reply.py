"""A reply is a question — T118 (FR-018; SC-012).

**No elevated trust.** Free text in a clarification reply re-enters the sequence
from step 1 under exactly the same rules. A reply that introduces a new metric,
period, filter, calculation or operator is a **new question**, not a
continuation.

The temptation this guards against is specific and reasonable-sounding: the
caller has already been authorized, already had a question interpreted, already
been shown a governed candidate set — surely their reply can be trusted a little
more? No. Every one of those facts is about the *previous* turn. The reply is
untrusted text that arrived after them, and treating it as continuation-shaped
would let a caller append an ungoverned filter to a question that had already
passed screening.

## What a reply may do

**Select one identifier from the sealed candidate set.** That is the entire
permitted vocabulary of a continuation, and it is enforced structurally: the
response type carries one identifier and one slot, and validation refuses any
identifier the sealed set does not contain.

A selection outside the set is not narrowed, corrected or fuzzily matched to the
nearest member — it refuses. `001`'s ambiguity rules already decided what the
governed options were, and a "did you mean" here would be this feature choosing
among them after promising not to (`FR-015`).

## What a reply may not do

Introduce a slot, a filter, a period, a calculation, an operator or an
identifier. None of those is expressible: :class:`ClarificationReply` declares
two fields and forbids extras, so an attempt to smuggle one arrives as
``extra_forbidden`` rather than as a field a validator has to remember to reject.

Free text in a reply is not carried here at all. It re-enters at step 1 as a new
question — screened, bounded and interpreted from scratch — which is what
`FR-018` means by "no elevated trust".

## After application

Deterministic resolution resumes under fresh authorization. This module
constructs no ``AnalyticsQuery`` and reaches no warehouse: that is Phase 8's
builder and Phase 9's port, reached only once the intent is complete.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from ..contracts._base import ContractViolation, InteractionModel
from ..contracts.intent import SlotKind
from ..contracts.reason_codes import InterpretationReasonCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..contracts.clarification import ClarificationContract

__all__ = [
    "ClarificationReply",
    "apply_reply",
]


class ClarificationReply(InteractionModel):
    """One selection from a sealed candidate set. **Two fields, extras forbidden.**

    ``slot`` is carried as well as ``identifier`` so a reply cannot silently
    answer a different slot from the one the contract left unresolved. Both are
    checked against the contract; neither is trusted on its own.

    There is deliberately no ``text``, no ``notes``, no ``refine`` and no
    ``additional_filters``. A reply that wants to say more is a new question, and
    the absence of a field is what makes that structural rather than a rule
    somebody enforces.
    """

    slot: SlotKind
    identifier: str = Field(min_length=1)


def apply_reply(contract: ClarificationContract, reply: ClarificationReply) -> str:
    """The chosen governed identifier, or refuse. **No partial intent is released.**

    Returns the identifier rather than a mutated intent: assembling the resolved
    intent is the interpretation layer's job, and returning a half-built one from
    here would be a partial result escaping a validation function.

    Four ways to fail, and each refuses whole:

    * the reply answers a **different slot** from the unresolved one;
    * the identifier is **not in the sealed candidate set** — foreign or
      fabricated, and indistinguishable to this feature, which is correct: both
      are things the issuer did not offer;
    * the identifier is in the set but under a **different slot** — a candidate
      cannot be borrowed across slots;
    * the set names it **twice**, which means the contract itself is incoherent.

    Matching is exact. No case folding, no whitespace trimming, no prefix match:
    a normalisation here would let ``"Installs "`` select ``"installs"``, and
    accepting an identifier by repairing it is how a closed set stops being
    closed.
    """
    if reply.slot is not contract.unresolved:
        raise ContractViolation(
            InterpretationReasonCode.CLARIFICATION_CONTEXT_MISMATCH,
            "the reply answers a slot the clarification did not leave unresolved",
        )

    matching = [
        candidate
        for candidate in contract.candidates
        if candidate.identifier == reply.identifier and candidate.slot is reply.slot
    ]

    if len(matching) > 1:
        raise ContractViolation(
            InterpretationReasonCode.INTENT_AMBIGUOUS,
            "the sealed candidate set names one identifier twice",
        )

    if not matching:
        # The detail names no candidate. Listing what *was* offered would tell a
        # caller who guessed an identifier which governed names exist — the same
        # disclosure `FR-019` forbids when authorization empties a set.
        raise ContractViolation(
            InterpretationReasonCode.TERM_NOT_GOVERNED,
            "the reply selects an identifier the clarification did not offer",
        )

    return matching[0].identifier
