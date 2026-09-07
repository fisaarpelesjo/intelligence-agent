"""Term resolution — T070 (FR-006, FR-048, FR-090; SC-052).

`FR-048` is this module's: a fabricated identifier refuses here, and refuses because
`001`'s outcome shape says nothing matched — never because a threshold in this feature
declined to coerce it.

`001`'s discovery surface is the **sole** source of candidates. It matches names,
pt-BR labels, descriptions, synonyms and glossary terms, tolerates informal and
misspelled pt-BR, and **filters by access before returning** — so authorization
filtering is not something this feature adds on top, it is a property of the
surface being used.

**No local index, cache or derived term table exists** (`FR-090`). Building one
would create a second, unfiltered copy of the catalog's vocabulary, and the first
time it went stale it would resolve a term the catalog no longer governs. `T071`
asserts the absence.

**This module adds no matching of its own.** No fuzzy comparison, no similarity
threshold, no spell correction, no embedding, no model call. `001` owns the one
threshold in the stack and states why it is fixed; this feature calls
``CatalogApi.resolve`` and records what came back.

**Authorization is required by the signature.** ``authorized`` is a keyword-only
``AuthorizedContext``, which only the step-2 preflight produces — so no catalog
read can happen before authorization, and the ordering is a property of the call
graph rather than a rule somebody remembers.

## Recording *how* it matched

`FR-006` requires every resolution to record how it matched, and that record is
disclosed to the user so a misinterpretation is visible rather than silent. Four
of `001`'s six match kinds have a governed counterpart in this feature's closed
``MatchKind``:

| `001` | `003` |
|---|---|
| ``CANONICAL_NAME`` | ``CANONICAL_ID`` |
| ``LABEL`` | ``LABEL`` |
| ``SYNONYM`` | ``SYNONYM_FORMAL`` |
| ``GLOSSARY`` | ``GLOSSARY_TERM`` |

``DESCRIPTION`` and ``FUZZY`` have **no representable counterpart**. That is not
an oversight in either contract: a description match means the term appeared in
prose *about* the metric rather than in any governed naming of it, and a fuzzy
match is string distance rather than a naming at all. `003`'s ``MatchKind`` is
closed and declares neither.

So a term whose only match is by description or string distance **does not
resolve**. It is reported ``TERM_NOT_GOVERNED``, because this feature cannot
truthfully record how it matched and `FR-006` forbids resolving without that
record. Refusing is the fail-closed reading; the alternative is disclosing a
match kind the contract does not have, or claiming a governed naming that never
happened.

`003` also declares ``SYNONYM_INFORMAL`` and ``SYNONYM_ABBREVIATION``, which
`001` does not distinguish. They are simply never produced today — a narrower
produced set than the declared one is safe, where the reverse would not be.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.search.api import AccessContext
from semantic_catalog.search.outcomes import Ambiguous, Resolved
from semantic_catalog.search.resolve import Candidate
from semantic_catalog.search.resolve import MatchKind as CatalogMatchKind

from ..authorization.context_preflight import AuthorizedContext
from ..contracts._base import ContractViolation, LocalizedRef, build
from ..contracts.clarification import CandidateRef
from ..contracts.intent import MatchKind, ResolutionBasis, SlotKind, TermRef, TermResolution
from ..contracts.reason_codes import InterpretationReasonCode
from .outcomes import SlotOutcome, TermOutcome, classify

__all__ = [
    "REPRESENTABLE_MATCH_KINDS",
    "CatalogDiscovery",
    "TermRequest",
    "access_context_for",
    "candidate_refs",
    "discover",
    "match_kind_for",
    "ordered_candidates",
    "resolve_term",
]

#: `001` match kind to this feature's governed match kind. See the module
#: docstring on why ``DESCRIPTION`` and ``FUZZY`` are absent.
REPRESENTABLE_MATCH_KINDS: dict[CatalogMatchKind, MatchKind] = {
    CatalogMatchKind.CANONICAL_NAME: MatchKind.CANONICAL_ID,
    CatalogMatchKind.LABEL: MatchKind.LABEL,
    CatalogMatchKind.SYNONYM: MatchKind.SYNONYM_FORMAL,
    CatalogMatchKind.GLOSSARY: MatchKind.GLOSSARY_TERM,
}


@runtime_checkable
class CatalogDiscovery(Protocol):
    """`001`'s discovery surface, as narrowly as this feature uses it.

    A ``Protocol`` rather than `001`'s concrete ``CatalogApi`` for two reasons,
    and the second is the load-bearing one:

    * **narrowness** — this feature calls exactly one method. Depending on the
      whole class would let a later edit reach ``get_metric``, ``search`` or the
      bundle without that widening being visible in a signature;
    * **substitutability** — a fixture must be able to stand here. Typing against
      the concrete class would make the only testable path a real built bundle,
      and the disclosure-symmetry tests need to control what a caller may see.

    ``CatalogApi`` satisfies it structurally, so production wiring passes the
    real thing and nothing adapts anything.
    """

    def resolve(self, query: str, *, access: AccessContext) -> SlotOutcome:
        """The access-filtered three-way outcome for ``query``."""
        ...


@dataclass(frozen=True, slots=True)
class TermRequest:
    """One user term to resolve: where it sat, and which slot it is being read as.

    Carries the **position**, never the text, for the reason `FR-053` gives —
    and the surface separately, because `001`'s surface needs the string to
    search. The string is a parameter, not a field: it travels into the search
    and no further, so nothing downstream can persist it by accident.
    """

    term: TermRef
    slot: SlotKind


def access_context_for(authorized: AuthorizedContext, *, on: date) -> AccessContext:
    """`001`'s access vocabulary, built from the resolved authorization context.

    Note what is **not** passed: the granted tag set. `001`'s registry decides
    authorization from the principal type, the authorization scope and the
    evaluation date, and handing it a pre-computed answer would move that
    decision out of governed data — which is exactly the metric-level verdict
    `FR-088` keeps upstream.
    """
    scope = authorized.context.authorization_scope
    if not scope:
        # Unreachable through the preflight, which refuses an unresolved scope.
        # Asserted rather than assumed: a context that arrived another way must
        # not silently become an empty scope the registry might treat as valid.
        raise ContractViolation(
            InterpretationReasonCode.AUTHORIZATION_CONTEXT_UNRESOLVABLE,
            "the authorization context carries no scope",
        )
    return AccessContext(
        principal_type=PrincipalType(authorized.context.principal_type),
        authorization_scope=scope,
        on=on,
    )


def discover(
    surface: str,
    *,
    catalog: CatalogDiscovery,
    authorized: AuthorizedContext,
    on: date,
) -> SlotOutcome:
    """`001`'s three-way outcome for ``surface``, access-filtered.

    One call, one surface. The catalog is reached only here, and only with an
    ``AuthorizedContext`` in hand.
    """
    return catalog.resolve(surface, access=access_context_for(authorized, on=on))


def match_kind_for(candidate: Candidate) -> MatchKind | None:
    """This feature's governed match kind, or ``None`` when unrepresentable."""
    return REPRESENTABLE_MATCH_KINDS.get(candidate.kind)


def ordered_candidates(candidates: tuple[Candidate, ...]) -> tuple[Candidate, ...]:
    """`001`'s stable ordering — score, then match kind, then identifier.

    Reused rather than re-derived. Ordering candidates by any key of this
    feature's own would let two runs disagree, and would let a weaker match
    displace an exact one.
    """
    return tuple(sorted(candidates, key=lambda candidate: candidate.sort_key))


def candidate_refs(
    outcome: SlotOutcome, *, slot: SlotKind, content_version: str, language: str
) -> tuple[CandidateRef, ...]:
    """The authorised candidates, as governed references.

    **Identifiers and governed pointers only.** ``CandidateRef.distinguishing``
    is a ``LocalizedRef`` into governed content, never a built string and never a
    span of the question — so a candidate list cannot carry an analytical value,
    a filter value or the user's words.

    Unrepresentable candidates are dropped, for the reason in the module
    docstring: a candidate this feature cannot say how it matched is one it
    cannot offer.
    """
    if not isinstance(outcome, Ambiguous):
        return ()
    return tuple(
        build(
            CandidateRef,
            identifier=candidate.metric_id,
            slot=slot,
            distinguishing=LocalizedRef(
                code=InterpretationReasonCode.INTENT_AMBIGUOUS.value,
                language=language,
                content_version=content_version,
            ),
        )
        for candidate in ordered_candidates(outcome.candidates)
        if match_kind_for(candidate) is not None
    )


def resolve_term(
    request: TermRequest,
    surface: str,
    *,
    catalog: CatalogDiscovery,
    authorized: AuthorizedContext,
    on: date,
    basis: ResolutionBasis = ResolutionBasis.ENUMERATED_MEMBERSHIP,
) -> TermResolution:
    """Resolve one term against the governed vocabulary, or refuse.

    Deterministic: the same surface, the same catalog release and the same
    authorization context always produce the same resolution, because every
    ordering decision is `001`'s and no threshold of this feature's own
    participates.

    Four outcomes:

    * **resolved** — exactly one authorised candidate, matched by a governed
      naming this feature can record;
    * **ambiguous** — several authorised candidates. ``INTENT_AMBIGUOUS``, never
      a silent pick of the top scorer;
    * **not governed** — nothing matched, *or* nothing the caller may see. The
      two are byte-identical by construction, because `001` filters before
      deciding the shape;
    * **unrepresentable** — matched only by description or string distance.
      ``TERM_NOT_GOVERNED``; see the module docstring.
    """
    outcome = discover(surface, catalog=catalog, authorized=authorized, on=on)
    shape = classify(outcome)

    if shape is TermOutcome.NOT_GOVERNED:
        raise ContractViolation(
            InterpretationReasonCode.TERM_NOT_GOVERNED,
            "no governed concept corresponds to the term; it is never coerced to a nearest match",
        )

    if shape is TermOutcome.AMBIGUOUS:
        raise ContractViolation(
            InterpretationReasonCode.INTENT_AMBIGUOUS,
            "the term resolves to more than one governed candidate",
        )

    if not isinstance(outcome, Resolved):  # pragma: no cover - narrowed by `classify`
        raise ContractViolation(
            InterpretationReasonCode.TERM_NOT_GOVERNED,
            "the discovery surface returned an outcome shape this feature does not know",
        )

    kind = match_kind_for(outcome.candidate)
    if kind is None:
        raise ContractViolation(
            InterpretationReasonCode.TERM_NOT_GOVERNED,
            "the term matched no governed naming of a concept; a match this "
            "feature cannot record is a match it does not claim",
        )

    return build(
        TermResolution,
        term=request.term,
        slot=request.slot,
        resolved_to=outcome.candidate.metric_id,
        matched_via=kind,
        confidence_basis=basis,
    )
