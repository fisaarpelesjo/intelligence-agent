"""Authorization-filtered candidates — T119 (FR-019; SC-023).

**Filtering is never signalled.** When authorization removes every candidate, the
response is byte-identical to "this term is not governed" — the caller learns
neither that filtering happened nor what was omitted.

That equivalence is the whole requirement. "You may not see the three candidates
that matched" is a disclosure: it tells an unauthorized caller that the term
exists, that it resolves, and how many things it resolves to. Repeated across a
vocabulary, it maps the catalog from outside. So an emptied set and an unmatched
term produce the same refusal with the same code and the same detail.

**Nothing is filtered here.** `001`'s discovery surface filters at read time —
filtering is a property of the surface being used, not something this feature
adds on top — so this module receives candidates a principal may already see and
shapes them into ``CandidateRef`` entries. A second filter here would be a second
opinion about access, and the two could disagree.

**Ordering is deterministic** and does not depend on the order `001` happened to
return. Two identical questions produce byte-identical contracts, which is what
lets `SC-005`'s reproducibility claim survive a sealed artifact: a seal computed
over a differently-ordered candidate list is a different seal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..contracts._base import ContractViolation, build
from ..contracts.clarification import CandidateRef
from ..contracts.reason_codes import InterpretationReasonCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterable

    from ..contracts._base import LocalizedRef
    from ..contracts.intent import SlotKind

__all__ = [
    "NOT_GOVERNED_DETAIL",
    "governed_candidates",
    "not_governed",
]

#: The one detail both the emptied-by-authorization case and the never-matched
#: case carry. A single constant rather than two equal literals, so the two
#: refusals cannot drift apart in a later edit — which is the only way this
#: property realistically breaks.
NOT_GOVERNED_DETAIL = "the term is not a governed identifier"


def not_governed() -> ContractViolation:
    """The refusal an unmatched term produces, and an emptied set produces too."""
    return ContractViolation(InterpretationReasonCode.TERM_NOT_GOVERNED, NOT_GOVERNED_DETAIL)


def governed_candidates(
    options: Iterable[tuple[str, LocalizedRef]], *, slot: SlotKind
) -> tuple[CandidateRef, ...]:
    """Shape governed options into contract candidates, deterministically ordered.

    Raises the not-governed refusal when nothing survives. The caller cannot
    distinguish that from a term `001` never matched, and must not be able to.

    Sorted by identifier: the identifier is the governed English name, so the
    order is a property of the catalog rather than of a traversal. Sorting on
    ``distinguishing`` instead would order by pt-BR content, which changes when
    the wording is revised and would silently change every seal.

    A duplicate identifier refuses rather than being collapsed. Two candidates
    with one identifier means the surface returned something incoherent, and
    quietly deduplicating would present a caller with a choice narrower than the
    one that was actually ambiguous.
    """
    entries = tuple(options)
    identifiers = [identifier for identifier, _ in entries]
    if len(set(identifiers)) != len(identifiers):
        raise ContractViolation(
            InterpretationReasonCode.INTENT_AMBIGUOUS,
            "the governed candidate set names one identifier twice",
        )

    if not entries:
        raise not_governed()

    return tuple(
        build(CandidateRef, identifier=identifier, slot=slot, distinguishing=distinguishing)
        for identifier, distinguishing in sorted(entries, key=lambda option: option[0])
    )
