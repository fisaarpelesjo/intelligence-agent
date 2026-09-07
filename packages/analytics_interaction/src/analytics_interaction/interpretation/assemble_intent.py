"""Resolved intent assembly — T087 (FR-005, FR-026; SC-001, SC-005).

**Step 9.** Every slot has been filled or has failed; this turns the outcomes
into a ``ResolvedIntent``, or refuses.

    No concept absent from the catalog appears in a resolved intent.
    — `tasks.md` T087

That is the whole guarantee, and it is why this module accepts *resolutions*
rather than strings. A ``TermResolution`` can only exist with a
``resolved_to`` that `001`'s access-filtered surface returned, so the intent is
built from identifiers that were already governed and already authorised. There
is no path here that takes a name.

**Nothing is guessed and nothing is silently dropped.** An unresolved required
slot refuses; an ambiguous one refuses; a term that resolved to nothing is not
quietly omitted. `FR-005` requires *every* element of intent to resolve, and a
request built from the slots that happened to work would answer a different
question from the one asked — with no sign to the reader that it had.

**Clarification is not issued here.** The escalation this module performs is a
refusal carrying the governed code; issuing a sealed contract is Phase 12 and is
unavailable anyway while `D-21` is undeclared. Returning "here is a partial
intent and also a refusal" would give a caller something to use, which is exactly
what a refusal must not do.

**Authorization is required by the signature.** ``authorized`` is a keyword-only
``AuthorizedContext``, so no intent can be assembled before step 2 — and the
fingerprint carried alongside is checked against the one resolution ran under, so
an intent cannot be assembled from terms resolved for somebody else.
"""

from __future__ import annotations

from datetime import date

from ..authorization.context_preflight import AuthorizedContext
from ..contracts._base import ContractViolation, build
from ..contracts.intake import DeclaredLanguage
from ..contracts.intent import ResolvedIntent, ResolvedPeriod, SlotKind, TermResolution
from ..contracts.reason_codes import InterpretationReasonCode
from ..identity.authorization_fingerprint import derive_authorization_fingerprint
from .slots import FILL_ORDER

__all__ = [
    "REQUIRED_SLOTS",
    "assemble_resolved_intent",
    "resolved_identifiers",
    "unresolved_slots",
]

#: Slots a governed request cannot be built without. A metric names what is being
#: asked; a period bounds it. `002`'s ``AnalyticsQuery`` requires both, so an
#: intent missing either could never become a request — refusing here says so
#: while the reader can still act on it.
#:
#: Dimensions, sources, filters and comparisons are genuinely optional: `002`
#: declares them optional, and inventing one would be inventing a question.
REQUIRED_SLOTS: frozenset[SlotKind] = frozenset({SlotKind.METRIC, SlotKind.PERIOD})


def resolved_identifiers(
    resolutions: tuple[TermResolution, ...], slot: SlotKind
) -> tuple[str, ...]:
    """Governed identifiers for ``slot``, in **fill order then question order**.

    Deterministic by construction: the input order is the order the terms
    appeared in the question, and this preserves it rather than sorting. Sorting
    would be equally deterministic and would lose which term the user wrote
    first, which is what ``TermRef`` positions are for.

    Duplicates are collapsed. The same metric named twice is one metric, and a
    request carrying it twice would be a different request from the one the
    question asked.
    """
    seen: list[str] = []
    for resolution in resolutions:
        if resolution.slot is not slot or resolution.resolved_to is None:
            continue
        if resolution.resolved_to not in seen:
            seen.append(resolution.resolved_to)
    return tuple(seen)


def unresolved_slots(resolutions: tuple[TermResolution, ...]) -> tuple[SlotKind, ...]:
    """Slots that were attempted and produced no governed identifier.

    Returned in fill order so a refusal names them in the order they were tried,
    which is the order a caller would fix them in.
    """
    attempted = {resolution.slot for resolution in resolutions}
    resolved = {resolution.slot for resolution in resolutions if resolution.resolved_to is not None}
    return tuple(slot for slot in FILL_ORDER if slot in attempted - resolved)


def assemble_resolved_intent(
    resolutions: tuple[TermResolution, ...],
    *,
    authorized: AuthorizedContext,
    auth_fingerprint: str,
    period: ResolvedPeriod | None,
    language: DeclaredLanguage,
    reference_date: date,
    as_of: date | None,
    catalog_release: str,
    policy_version: str,
    vocabulary_version: str,
) -> ResolvedIntent:
    """Assemble the intent, or refuse. **No partial intent is ever returned.**

    ``auth_fingerprint`` is the fingerprint resolution ran under. It is compared
    against the one derived from ``authorized`` now, so an intent cannot be
    assembled from terms discovered under a different authorization context —
    stale, swapped or replayed. `002` learned this the hard way when its ledger
    keyed on identity alone; the split is applied here before the same mistake
    can be made.

    ``as_of`` is carried **exactly as the caller supplied it**, including
    ``None``. It is never filled from ``reference_date`` — the two answer
    different questions, and a derivation would silently pin every question to
    the day it asked about rather than to the definitions in force.

    ``period`` may be ``None`` only if no period slot was attempted; a period
    that was attempted and failed has already refused above.
    """
    expected = derive_authorization_fingerprint(authorized)
    if auth_fingerprint != expected:
        # Names neither fingerprint. A caller who could compare them could probe
        # for the shape of somebody else's context.
        raise ContractViolation(
            InterpretationReasonCode.AUTHORIZATION_CONTEXT_UNRESOLVABLE,
            "the resolution was performed under a different authorization context",
        )

    outstanding = unresolved_slots(resolutions)
    if outstanding:
        raise ContractViolation(
            InterpretationReasonCode.INTENT_AMBIGUOUS,
            "the question leaves "
            + ", ".join(slot.value for slot in outstanding)
            + " unresolved; no partial intent is produced",
        )

    metrics = resolved_identifiers(resolutions, SlotKind.METRIC)
    if not metrics:
        raise ContractViolation(
            InterpretationReasonCode.QUESTION_NOT_ANALYTICAL,
            "the question resolved no governed metric",
        )

    if period is None:
        raise ContractViolation(
            InterpretationReasonCode.PERIOD_EXPRESSION_NOT_GOVERNED,
            "the question resolved no governed period",
        )

    return build(
        ResolvedIntent,
        metrics=metrics,
        dimensions=resolved_identifiers(resolutions, SlotKind.DIMENSION),
        filters=(),
        sources=resolved_identifiers(resolutions, SlotKind.SOURCE),
        period=period,
        comparison=None,
        resolutions=resolutions,
        language=language,
        reference_date=reference_date,
        as_of=as_of,
        catalog_release=catalog_release,
        policy_version=policy_version,
        vocabulary_version=vocabulary_version,
    )
