"""Answer assembly — T123 (FR-032, FR-038, FR-039, FR-098; SC-007, SC-011, SC-028).

**Governed content only. No string is generated, concatenated from user input,
paraphrased or translated.**

Every user-facing string in an answer is a ``LocalizedRef`` — a
``(code, language, content_version)`` triple resolved against
`interpretation_governance/` at render time. There is no format call, no join, no
template with a slot for a question span, and no model. That is what makes
byte-identity across repeats (`SC-028`) a property of the design rather than a
discipline somebody maintains.

The one exception is a caveat's ``message_pt_br``, which carries upstream wording
verbatim — because rendering it through this layer's registry would *be* the
re-wording `FR-084` forbids.

## Nothing here reads a clock, a random source or a global

``reference_date`` and ``as_of`` come from the resolved intent and are disclosed
**independently** (`FR-098`): the same sentence asked under a different reference
date or a different pin is a different interpretation, and deriving one from the
other would collapse two identity members into one. `on` is supplied for the
`D-18`/`D-19` resolution and never defaulted to today.

## The gates, in order

1. **governed claim wording** — `D-18`'s ``claim-classes.yaml``. It ships empty,
   so **every answer refuses today**. Designed, not missing: an answer whose
   claim classes have no governed wording would have to invent labels for
   "factual result" and "calculated comparison", which is the wording decision
   `D-18` exists to make;
2. **disclosure evaluation** — `D-19`, and only when the answer carries an
   insufficiency notice. A notice states that data behind the answer is
   insufficient, and whether stating it could help reconstruct a suppressed
   figure is `D-19`'s cross-question judgement. Gating unconditionally would
   refuse plain answers that need no such judgement;
3. **provenance completeness** — incomplete provenance abstains, never warns;
4. **caveat completeness** — all-or-withheld;
5. **construction** — through the contract, so its own cross-field validator runs.

Each gate refuses before the next runs, so a refused answer never partially
exists.

## Channel-neutral

No format, no markup, no length limit, no thread id, no webhook field, no
provider metadata. A later chat or email feature renders this contract; it does
not re-derive meaning from it, and there is no field it could be given that would
change what the answer says.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..compliance.gates import CapabilitySurface, require_surface
from ..contracts._base import ContractViolation, build
from ..contracts.answer import AnalyticsAnswer
from ..contracts.reason_codes import InterpretationReasonCode
from ..governance.vocabulary import resolve_claim_classes
from .provenance import carry_provenance
from .withhold import assert_caveats_are_releasable

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterable
    from datetime import date

    from analytics_query.contracts.result_provenance import ResultProvenance

    from ..compliance.readiness import ReadinessRecord
    from ..contracts.answer import AnswerClaim, CaveatOrigin, CaveatSet, InsufficiencyNotice
    from ..contracts.intent import ResolvedIntent
    from ..governance.schemas import ClaimClassContent

__all__ = ["assemble_answer", "governed_claim_wording"]


def governed_claim_wording(
    *,
    on: date,
    instances: tuple[ClaimClassContent, ...] | None = None,
) -> ClaimClassContent:
    """The `D-18` claim-class wording in force, or refuse.

    Raises ``ContentUnresolvable`` carrying
    ``INTERPRETATION_VOCABULARY_UNRESOLVABLE`` when no single complete instance
    is effective — which covers the shipped state (**zero instances**), the
    ambiguous state (**more than one**) and the incomplete state (**one that does
    not cover every contract-declared class**).

    ``instances`` is injectable **for fixtures only**. No `src/` module supplies
    one, and the fixture-containment scan asserts it.
    """
    return resolve_claim_classes(on, instances=instances)


def assemble_answer(
    intent: ResolvedIntent,
    *,
    claims: tuple[AnswerClaim, ...],
    caveats: CaveatSet,
    provenance: tuple[ResultProvenance, ...],
    required_caveats: Iterable[tuple[str, CaveatOrigin]] = (),
    insufficiency: tuple[InsufficiencyNotice, ...] = (),
    on: date,
    wording: tuple[ClaimClassContent, ...] | None = None,
    records: Iterable[ReadinessRecord] | None = None,
) -> AnalyticsAnswer:
    """Assemble one governed answer, or refuse. **Nothing partial is released.**

    Everything disclosed comes from the intent: the language, both dates and all
    three governing versions. Passing them separately would let an answer
    disclose a resolution different from the one that produced the number, and
    the contract's own validator refuses that — this function removes the
    opportunity rather than relying on the check.

    ``required_caveats`` is what upstream stated, as ``(code, origin)`` pairs. It
    is separate from ``caveats`` on purpose: the set is what the caller assembled
    and the requirement is what must be in it, and comparing a collection against
    itself proves nothing.
    """
    # 1. governed claim wording. Refuses today: `D-18` ships empty.
    wording_in_force = governed_claim_wording(on=on, instances=wording)

    # 2. disclosure evaluation, only where the answer needs that judgement.
    if insufficiency:
        require_surface(CapabilitySurface.DISCLOSURE_EVALUATION, records=records)

    # 3. provenance — incomplete abstains rather than warning.
    carried = carry_provenance(*provenance)

    # 4. caveats — all, or the answer is withheld.
    assert_caveats_are_releasable(caveats, required=required_caveats)

    # 5. every claim's class must have governed wording in force.
    _assert_every_claim_class_is_worded(claims, wording_in_force)

    return build(
        AnalyticsAnswer,
        interpreted=intent,
        claims=claims,
        caveats=caveats,
        provenance=carried,
        insufficiency=insufficiency,
        language=intent.language,
        reference_date=intent.reference_date,
        as_of=intent.as_of,
        catalog_release=intent.catalog_release,
        policy_version=intent.policy_version,
        vocabulary_version=intent.vocabulary_version,
    )


def _assert_every_claim_class_is_worded(
    claims: tuple[AnswerClaim, ...], wording: ClaimClassContent
) -> None:
    """A claim whose class has no governed wording cannot be presented.

    ``resolve_claim_classes`` already requires the effective content to cover
    every **contract-declared** class, so this is narrower: it checks the classes
    this particular answer uses, which is what a renderer will actually look up.

    Refusing here rather than at render time means the failure surfaces while an
    answer is being built, not while somebody is reading one.
    """
    worded = {entry.claim_class for entry in wording.classes}
    unworded = sorted(
        {claim.claim_class.value for claim in claims if claim.claim_class not in worded}
    )
    if unworded:
        raise ContractViolation(
            InterpretationReasonCode.INTERPRETATION_VOCABULARY_UNRESOLVABLE,
            "a claim class carried by this answer has no governed wording in force",
        )
