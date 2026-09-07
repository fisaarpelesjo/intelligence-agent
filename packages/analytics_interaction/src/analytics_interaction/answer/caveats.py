"""Caveat propagation and counting — T126, T127 (FR-084, FR-085; SC-047, SC-048).

**Byte-identical, origin-attributed, never merged or deduplicated across sides.**

A caveat is upstream wording — `001`'s message registry or `002`'s provenance
limitations — and it reaches the answer verbatim. It is never re-worded,
softened, summarised, truncated, translated or downgraded. ``message_pt_br`` is
the one string in this feature that is **not** a ``LocalizedRef``, precisely
because rendering it through this layer's registry would *be* the re-wording the
rule forbids.

## Nothing is ever deduplicated. Not across origins, not within one

Every occurrence survives. Two sides carrying the same caveat stay two caveats,
**and so do two occurrences from one side** — because multiplicity is
information this layer cannot interpret.

An earlier form of this module collapsed repeats within a single origin, on the
reasoning that `001` stating one limitation twice about one side is one
limitation. That reasoning was wrong, and worth recording: a repeat may be two
distinct upstream decisions, two evaluations, two pieces of evidence or two
segments of one range that happened to produce the same governed code. Deciding
they are "really" one is an interpretation of governed output — exactly what this
layer must not perform. Collapsing them tells the reader one thing was qualified
once when it was qualified twice, and nothing downstream can recover the
difference.

So the rule has no exception: **every occurrence is carried**.

## "Prominent" as a testable property

`FR-085` asks for prominence, which as "put it near the top" would be
untestable and unenforceable across channels a later feature will build. Expressed
structurally it is a contract test:

1. **required** — the set is an explicit collection, not an absent field;
2. **counted** — ``total`` equals the carried count, so a consumer rendering a
   subset is *detectable* rather than merely wrong;
3. **origin-attributed** — a reader can tell verdict from side A from side B;
4. **byte-preserved** — see above.

The count is what makes the difference. A downstream renderer that showed three
of five caveats produces an answer whose own ``total`` contradicts it, and that
contradiction is checkable without reading a word of the wording.

## Ordering is deterministic, and determinism is not achieved by removing anything

Stable **encounter order**: groups in the order the caller passed them, and
within each group the order upstream produced. The caller passes them in
provenance order — verdict, then side A, then side B — so the order is a property
of where the caveats came from.

Sorting was the alternative and it is worse here. A sort needs a total order, and
two occurrences identical in code and origin have none — so a sort would either
be unstable between them or would need a tiebreaker that reintroduced
deduplication by the back door. Encounter order is already total, already
deterministic for equal inputs, and preserves the sequence a reader would see
upstream.

`SC-028` requires byte-identical answers for equal inputs. Equal inputs arrive in
equal order, so equal answers come out.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..contracts._base import ContractViolation, build
from ..contracts.answer import AttributedCaveat, CaveatOrigin, CaveatSet
from ..contracts.reason_codes import InterpretationReasonCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterable

    from semantic_catalog.validation.decision import CatalogDecision

__all__ = [
    "PROVENANCE_ORDER",
    "carry_caveats",
    "caveats_from_decision",
    "caveats_from_limitations",
]

#: The provenance order a caller passes groups in — verdict first, then each
#: side. Declared so the convention is written down rather than implied by call
#: sites, and **not** used as a sort key: :func:`carry_caveats` preserves
#: encounter order and sorts nothing.
PROVENANCE_ORDER: tuple[CaveatOrigin, ...] = (
    CaveatOrigin.VERDICT,
    CaveatOrigin.SIDE_A,
    CaveatOrigin.SIDE_B,
    CaveatOrigin.SINGLE,
)


def caveats_from_decision(
    decision: CatalogDecision, *, origin: CaveatOrigin
) -> tuple[AttributedCaveat, ...]:
    """Every limitation `001` stated, carried whole.

    ``Limitation`` gives both the code and the governed pt-BR message, so nothing
    has to be looked up and nothing can be re-worded on the way. The code is
    mapped back onto `001`'s own enum rather than kept as a string: a caveat
    whose code this build does not recognise refuses, because carrying one would
    put an uninterpretable governed fact into an answer.
    """
    from semantic_catalog.contracts.reason_codes import ReasonCode as CatalogReasonCode

    carried: list[AttributedCaveat] = []
    for limitation in decision.limitations:
        try:
            code = CatalogReasonCode(limitation.code)
        except ValueError as exc:
            raise ContractViolation(
                InterpretationReasonCode.INTAKE_MALFORMED,
                "the decision carries a limitation code this build does not recognise",
            ) from exc
        carried.append(
            build(
                AttributedCaveat,
                code=code,
                message_pt_br=limitation.message_pt_br,
                origin=origin,
            )
        )
    return tuple(carried)


def caveats_from_limitations(
    codes: Iterable[str],
    *,
    origin: CaveatOrigin,
    wording: dict[str, str],
) -> tuple[AttributedCaveat, ...]:
    """`002`'s provenance limitations, which carry a **code and no message**.

    ``ResultProvenance.limitations`` is a tuple of codes; the wording lives
    upstream. So ``wording`` is supplied by the caller, holding the governed
    text for each code — and a code with no supplied wording **refuses**.

    That refusal is `FR-086`'s all-or-withheld rule reaching down to a single
    caveat: an answer whose caveats cannot be carried in full is withheld, never
    trimmed, and composing a sentence here for a code whose governed wording was
    unavailable would be exactly the invented text `FR-039` forbids.
    """
    from analytics_query.contracts.reason_codes import AnalyticsReasonCode as QueryReasonCode

    carried: list[AttributedCaveat] = []
    for raw in codes:
        text = wording.get(raw)
        if not text:
            raise ContractViolation(
                InterpretationReasonCode.INTERPRETATION_VOCABULARY_UNRESOLVABLE,
                "a governed caveat has no stored wording; the answer is withheld, never trimmed",
            )
        try:
            code = QueryReasonCode(raw)
        except ValueError as exc:
            raise ContractViolation(
                InterpretationReasonCode.INTAKE_MALFORMED,
                "a provenance limitation names a code this build does not recognise",
            ) from exc
        carried.append(build(AttributedCaveat, code=code, message_pt_br=text, origin=origin))
    return tuple(carried)


def carry_caveats(*groups: tuple[AttributedCaveat, ...]) -> CaveatSet:
    """Combine attributed caveats into the counted set. **Every occurrence kept.**

    No deduplication of any kind — not across origins, not within one, not by
    code, not by wording. ``total`` is the number of **occurrences carried**, not
    the number of distinct ``(code, origin)`` pairs, so three identical caveats
    produce a total of three.

    Two occurrences that differ in wording are also both kept. The authoritative
    contract does not define same-code-same-origin as a contradiction, so
    refusing there would discard a valid repeated occurrence to enforce a rule
    nobody wrote.

    Order is encounter order: groups as passed, occurrences as produced. Nothing
    is sorted, because a sort over occurrences with no total order between them
    would need a tiebreaker — and the obvious tiebreaker is the collapse this
    function exists not to perform.

    There is deliberately no ``set``, ``dict``, ``frozenset`` or ``unique`` on
    this path. `T126`'s suite scans for them: a container that cannot hold
    duplicates is how deduplication returns without anybody deciding to add it.
    """
    carried: list[AttributedCaveat] = []
    for group in groups:
        carried.extend(group)
    return build(CaveatSet, caveats=tuple(carried), total=len(carried))
