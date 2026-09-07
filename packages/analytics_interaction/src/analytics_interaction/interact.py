"""The composed interaction entry point — T108 (ADR 0017; ADR 0026).

```
ask(intake, *, collaborators, at) -> AnsweredOutcome | ClarificationOutcome | GovernedRefusal
```

**One operation.** No second entry, no batch form, no streaming form, no "explain" form, no options
bag. `004` constructs the `QuestionIntake` and nothing else.

**This module composes; it does not decide.** Every step below is an existing public function of
this feature, called in the order `contracts/intake-contract.md` §6 fixes. Nothing here re-
implements a gate, anticipates a decision, caches a resolution or shortcuts a check — the ordering
*is* the contribution, and ADR 0017 authorized exactly this and nothing more.

**Additive, and the file boundary is the enforcement.** No existing module of this feature is edited
by this work: not a line, not an import, not a docstring. Everything reached here is named in that
module's own ``__all__``, which `T107`'s survey verified before this file existed.

## The one place this module holds logic rather than ordering

Step 12 — "construct governed request(s) deterministically" — has **no public function** in this
feature. It exists as a telemetry span name and as a contract obligation, and nowhere else. So
:func:`governed_request_for` implements it, and its scope is deliberately tiny: a total,
deterministic projection from the already-resolved intent onto `002`'s `AnalyticsQuery`. It reads
only fields the intent already carries, adds no default, resolves nothing, and makes no decision the
intent had not already made. Anything larger would be the second interpretation pipeline ADR 0017
forbids.

## Wording arrives resolved (ADR 0026)

The answered outcome carries the `AnalyticsAnswer` **unaltered** beside the **resolved** governed
wording for every `LocalizedRef` it contains. Resolution happens here, in this feature, through this
feature's own registries and governed content — which is what lets `004` preserve wording byte-
for-byte without ever selecting an upstream message. A reference this feature cannot resolve is
**absent** from the mapping, and `004` withholds rather than rendering the reference.

## What refuses, and how

Every refusal is carried through **unmodified**: the same code, the same stored wording, the same
standing. This module adds no reason code, no audit stage and no answer field. A step that raises a
governed refusal ends the operation at that step, and `RELEASE` is emitted before release and only
on the release path (step 16).

## Collaborators are injected

Every port and resolver arrives in :class:`InteractionCollaborators`. There is no ambient read, no
module-level singleton, no default client and no clock: ``at`` is a parameter. That is what lets the
equivalence tests drive this entry point and this feature's existing components through identical
inputs and compare byte-for-byte (`T110`).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol

from analytics_query.contracts.request import AnalyticsQuery, DateRange

from .answer.assemble import assemble_answer
from .answer.claims_port import ClaimConstructionPort, assert_claims_are_authorised
from .answer.refusal import GovernedRefusal
from .authorization.context_preflight import (
    AuthorizationContextResolver,
    AuthorizedContext,
    resolve_authorization_context,
)
from .clarification.issue import issue_clarification
from .clarification.seal import SealPort
from .comparison.routing import ComparisonShape, classify_route
from .contracts import TermRef
from .contracts.answer import AnalyticsAnswer, CaveatSet
from .contracts.clarification import ClarificationContract, SlotKind
from .contracts.intake import QuestionIntake
from .contracts.intent import ResolvedIntent, ResolvedPeriod
from .execution.port import ExecutionPort
from .governance.schemas import ClaimClassContent, InterpretationPolicy, PeriodVocabulary
from .identity.authorization_fingerprint import derive_authorization_fingerprint
from .identity.interpretation_identity import derive_interpretation_identity
from .intake.bounds import apply_governed_length_bound
from .intake.parse import parse_intake
from .intake.screening import RedactionMatcher, screen_question
from .interpretation.assemble_intent import assemble_resolved_intent, unresolved_slots
from .interpretation.boundary_port import PeriodBoundaryResolverPort
from .interpretation.model_port import InterpretationModelPort
from .interpretation.outcomes import TermOutcome, classify
from .interpretation.period import resolve_period_in_question
from .interpretation.resolve_terms import (
    CatalogDiscovery,
    TermRequest,
    discover,
    resolve_term,
)
from .segmentation import segment

__all__ = [
    "STEP_ORDER",
    "AnsweredOutcome",
    "ClarificationOutcome",
    "InteractionCollaborators",
    "InteractionOutcome",
    "ResolvedWordingMap",
    "ask",
    "governed_request_for",
]

#: The sixteen steps, in the order `contracts/intake-contract.md` §6 fixes them. Named here so the
#: ordering is one list rather than an emergent property of the function below, and so a contract
#: test can assert that this module's control flow matches the contract's table.
STEP_ORDER: tuple[str, ...] = (
    "parse_intake",
    "authorization_context_preflight",
    "resolve_governed_vocabulary_and_policy",
    "apply_governed_bounds",
    "screen_untrusted_text",
    "resolve_slots_access_filtered",
    "resolve_period",
    "optional_model_narrowing",
    "assemble_intent_and_identity",
    "issue_clarification_if_unresolved",
    "route_comparison_by_expressibility",
    "construct_governed_requests",
    "catalog_comparison_verdict",
    "submit_through_execution_port",
    "exact_decimal_comparison",
    "assemble_answer_emit_release_then_release",
)


class ResolvedWordingMap:
    """The resolved governed wording for one answer, keyed by reference code (ADR 0026).

    A **lookup**, not a resolver: it is built once, here, from this feature's governed content, and
    it is read by `004` as a mapping. A code with no entry returns ``None``, which is `004`'s
    withhold condition — never a fallback that renders the reference.
    """

    __slots__ = ("_texts", "content_version")

    def __init__(self, texts: Mapping[str, str], content_version: str) -> None:
        self.content_version = content_version
        self._texts = dict(texts)

    def text_for(self, code: str) -> str | None:
        return self._texts.get(code)

    def __len__(self) -> int:
        return len(self._texts)


@dataclass(frozen=True)
class AnsweredOutcome:
    """An answered interaction: the answer unaltered, beside its resolved wording (ADR 0026)."""

    answer: AnalyticsAnswer
    wording: ResolvedWordingMap


@dataclass(frozen=True)
class ClarificationOutcome:
    """A sealed clarification, transported by the caller and altered by nobody.

    The wording map travels with it for presentation only. No field of the contract is read,
    answered or pre-filled by the caller (`FR-042` of `004`).
    """

    clarification: ClarificationContract
    wording: ResolvedWordingMap


#: The total outcome type. Three members, and no fourth: an interaction is answered, needs
#: clarification, or refuses.
InteractionOutcome = AnsweredOutcome | ClarificationOutcome | GovernedRefusal


class ConceptDiscovery(Protocol):
    """A surface that answers **which kind** of governed concept a term names (ADR 0029).

    Declared here rather than added to `CatalogDiscovery`, and the reason is a limit rather than
    taste: ADR 0028 permits a new module or a new published function and forbids editing an existing
    `003` module. `CatalogDiscovery` is one, so widening it is out of bounds — a port declared in
    this module is not.

    `001`'s `search.concepts.identify` satisfies this structurally. Nothing here imports `001`: the
    caller injects whatever satisfies the shape, exactly as every other collaborator arrives.
    """

    def identify_kinds(self, surface: str, *, on: date) -> tuple[str, ...]:
        """The concept kinds ``surface`` names, as the catalog's own strings, best first.

        Empty for a non-match **and** for a denial. The two are indistinguishable on purpose:
        telling them apart would let a caller enumerate the catalog by watching which terms refuse.
        """
        ...


class ClaimWordingResolver(Protocol):
    """Resolves the governed claim-class wording in force on a date (`D-18`).

    The **fourth** seam, authorized by the owner on 2026-08-20, and written to the shape the three
    before it already have rather than to a new one.

    Why it was needed, measured before it was written: :func:`assemble_answer` accepts an injectable
    ``wording=`` and step 16 called it without one, so assembly read
    ``interpretation_governance/claim-classes.yaml`` — which carries ``instances: []`` — and raised
    ``INTERPRETATION_VOCABULARY_UNRESOLVABLE`` for every answer. No collaborator could substitute
    it, so `ask()` could not return an ``AnsweredOutcome`` under **any** set of collaborators.
    That was not missing governed content; it was a missing injection point.

    **No default, deliberately**, for the reason the three fields before it give: a default pointing
    at the production resolver would be the ambient dependency again, and a test that forgot to
    inject would read disk and pass while believing it had injected. Omitting the field is a
    ``TypeError`` at construction.

    **This is not a demonstration flag.** A required parameter the caller supplies is not a
    conditional asking whether content is demonstration content. Nothing in this module branches on
    where the wording came from, and production still resolves an empty file and still refuses.
    """

    def __call__(self, on: date) -> tuple[ClaimClassContent, ...]: ...


class InterpretationPolicyResolver(Protocol):
    """Resolves the single complete interpretation policy in force on a date, or refuses (`D-19`).

    Injected rather than imported, on owner instruction of 2026-08-19. Step 3 used to call
    `governance.policy.resolve_policy` directly, and that was the **one** ambient read in a module
    whose whole argument is that everything it touches arrives through
    :class:`InteractionCollaborators`. A caller could substitute every other collaborator and not
    this one.

    **No default, deliberately.** Production passes `resolve_policy`, which reads governed content
    from disk; a test passes a fixture. A default pointing at the production resolver would be the
    ambient dependency again, and a test that forgot to inject would read disk and pass while
    believing it had injected.

    Refusal stays with the resolver. An unresolvable policy raises, and step 3 carries the raise
    through unmodified — this module neither catches it nor reinterprets it.
    """

    def __call__(self, on: date) -> InterpretationPolicy: ...


class PeriodVocabularyResolver(Protocol):
    """Resolves the governed period vocabulary in force on a date, or refuses (`D-18`).

    Same shape and the same reasoning as :class:`InterpretationPolicyResolver`, and the same absence
    of a default.
    """

    def __call__(self, on: date) -> PeriodVocabulary: ...


@dataclass(frozen=True)
class InteractionCollaborators:
    """Every port and resolver this operation needs, injected.

    No default is provided for any of them. A default would be an ambient dependency, and the reason
    `004` can test this entry point at all is that everything it touches arrives through here.

    That sentence was true of every field except two until 2026-08-19: step 3 reached
    `governance.policy` and `governance.vocabulary` at module level, so the governed content it
    resolved was not substitutable and `ask()` could never get past step 3 while
    `interpretation-policy.yaml` and `period-vocabulary.yaml` carry `instances: []`. The owner
    authorized closing that, and the two resolvers now arrive here like everything else.
    """

    authorization: AuthorizationContextResolver
    catalog: CatalogDiscovery
    execution: ExecutionPort
    #: ``None`` means the deployment holds no key (OD-101, 2026-09-02, cycle 527) —
    #: ``issue_seal`` already turns absence into the governed refusal, never a bypass, so
    #: the field's type now says what that function always accepted. Still **required**:
    #: a caller must state the absence rather than forget the field.
    seal: SealPort | None
    #: Which key and algorithm sealed a clarification. Declared by the caller, never chosen here: a
    #: seal whose key this module picked would be a seal this module could forge.
    seal_key_id: str
    seal_algorithm: str
    #: `D-19`'s policy and `D-18`'s vocabulary, resolved by the caller at step 3. **Required**, so
    #: an omission is a `TypeError` at construction, not a silent read of production content.
    #: `test_no_collaborator_has_a_default_that_is_not_declared_optional` is what holds that: it
    #: asserts every field outside the three documented optional ones carries no default.
    policy: InterpretationPolicyResolver
    period_vocabulary: PeriodVocabularyResolver
    #: `D-18`'s boundary resolver, applied at step 7. **Required**, the fifth seam, added
    #: 2026-08-20 on owner instruction. Step 7 used to receive the interval as a pair of dates the
    #: caller computed, and the only caller is this module — so the calendar arithmetic would have
    #: had to live here, which `R-8` forbids. The resolver delegates the calendar to `001` and
    #: `period.py` checks the zone and the inclusivity of what comes back.
    period_boundaries: PeriodBoundaryResolverPort
    #: The claims one governed result supports, built at step 15b. **Required**, the sixth seam and
    #: the one that makes an answered outcome reachable: step 16 passed ``claims=()`` against a
    #: contract requiring at least one, so no question could be answered here regardless of
    #: governed content. Deciding what counts as a finding is a reporting decision this feature has
    #: no authority to make, so it arrives injected — see `answer/claims_port.py`.
    claims: ClaimConstructionPort
    #: `D-18`'s claim-class wording, resolved by the caller at step 16. **Required**, the fourth
    #: field added for the same reason as the three below it, and the one that makes an answered
    #: outcome reachable at all: step 16 called `assemble_answer` without `wording=`, so assembly
    #: read the empty `claim-classes.yaml` and refused for every answer.
    claim_wording: ClaimWordingResolver
    #: `D-19`'s redaction matcher, applied to untrusted text at step 5. **Required**, and the third
    #: field added for the same reason as the two above — step 5 passed the literal ``None``, and
    #: `screen_question` refuses whenever the matcher is absent, so **no question could pass step 5
    #: through this entry point at all**. That made steps 6, 7, 10, 11, 13 and 14 unreachable here
    #: regardless of governed content, which was measured rather than inferred: five probes over the
    #: authored catalog, with a resolvable policy *and* vocabulary injected, all refused at step 5
    #: with one code.
    #:
    #: `RedactionMatcher` is `003`'s own published protocol and this package deliberately ships no
    #: implementation of it — the docstring there records why, and the reason stands: an
    #: implementation in `src/` would be this feature deciding what a governed pattern means, and
    #: that is the `D-19` owner's decision. So the matcher arrives from the deployment beside the
    #: `D-19` content it evaluates, exactly as the authorization resolver does.
    #:
    #: **This changes no capability.** No production matcher exists, so a production caller still
    #: cannot construct this and still could not answer a question if it did. What the field changes
    #: is that the dependency is now substitutable instead of ambient.
    redaction_matcher: RedactionMatcher
    #: `D-20` optional. ``None`` means no model narrowing is attempted, which is the shipped state.
    model: InterpretationModelPort | None = None
    #: The audit sink. ``None`` refuses at release rather than releasing unrecorded (`FR-083`).
    audit: object | None = None
    #: ADR 0029's concept surface. ``None`` means step 6 reports **metric** slots only, which is
    #: what this entry point did before the surface existed and remains correct: a span is reported
    #: as a metric because `001`'s metric surface resolved it, which is reading an answer rather
    #: than deciding one. Optional rather than required so a caller without the surface keeps
    #: working, and absent is not a degraded mode — it is one fewer question the catalog can be
    #: asked.
    concepts: ConceptDiscovery | None = None


def governed_request_for(intent: ResolvedIntent, period: ResolvedPeriod) -> AnalyticsQuery:
    """Step 12: project the resolved intent onto one governed request. Total and deterministic.

    **This is the one function in this module that is not pure composition**, and its scope is kept
    as small as the obligation allows: it copies what the intent already resolved and adds nothing.

    * metrics, dimensions, sources and filters are carried across **as resolved**;
    * the date range is the resolved period's own boundaries — not re-derived, not widened;
    * ``as_of`` is carried, and ``None`` stays ``None``: an absent pin means current-definition
      resolution upstream and is never filled in from the reference date.

    No limit, no threshold, no ordering and no row bound appears here, because none of those is the
    intent's to state — they are `002`'s governed policy, resolved behind the execution port.
    """
    return AnalyticsQuery(
        metrics=intent.metrics,
        dimensions=intent.dimensions,
        sources=intent.sources,
        filters=intent.filters,
        date_range=DateRange(start=period.start, end=period.end),
        as_of=intent.as_of,
    )


def _resolved_wording(intent: ResolvedIntent) -> ResolvedWordingMap:
    """The resolved governed wording for an answer. **Empty today, and that is the behaviour.**

    Claim wording is `D-18` content, in ``interpretation_governance/claim-classes.yaml``, which
    ships ``instances: []`` and whose own header says answer assembly refuses while it is empty. So
    there is nothing to resolve, and this returns an empty map rather than attempting a resolution
    that could not succeed.

    An earlier version of this docstring claimed the map was built defensively, with resolvable
    references included and unresolvable ones omitted. No such mechanism existed: the body returned
    an empty dictionary and never read the claims. That was a description of behaviour the code did
    not have, which is the class of claim this project treats as a defect, and the review that
    caught it was right (finding N).

    What happens downstream is unchanged, and is the point: `004` looks a reference up, finds
    nothing, and **withholds** (ADR 0026). A wording map that guessed would be worse than an empty
    one.
    """
    return ResolvedWordingMap({}, intent.vocabulary_version)


def ask(
    payload: object,
    *,
    collaborators: InteractionCollaborators,
    at: datetime,
    correlation_id: str,
    nonce: str,
    clarification_expiry: timedelta = timedelta(minutes=15),
) -> InteractionOutcome:
    """The single operation. Sixteen steps, in the contract's order, or one governed refusal.

    ``at`` is the evaluation instant and ``correlation_id`` and ``nonce`` are supplied: none of the
    three is read from a clock, a counter or a random source here, because a composed entry point
    that generated them would make two runs of one input incomparable (`T110`'s equivalence).

    Every refusal raised by a step propagates **unmodified**. This function catches nothing and
    rewrites nothing: a caller receives the same `GovernedRefusal` the step produced, which is what
    makes "refusals are carried through" checkable rather than aspirational.
    """
    on: date = at.date()

    # --- interpretation step 1: parse intake ------------------------------------------------------
    intake: QuestionIntake = parse_intake(payload)

    # --- interpretation step 2: authorization-context preflight, before any cost surface ----------
    authorized: AuthorizedContext = resolve_authorization_context(
        intake.principal, resolver=collaborators.authorization
    )
    auth_fingerprint = derive_authorization_fingerprint(authorized)

    # --- interpretation step 3: governed vocabulary (D-18) and policy (D-19) ----------------------
    # Both arrive through `collaborators`, so this step reads nothing ambient. A refusal raised by
    # either resolver is carried through unmodified — see `InterpretationPolicyResolver`.
    policy = collaborators.policy(on)
    vocabulary = collaborators.period_vocabulary(on)

    # --- interpretation step 4: governed bounds. Disclosure permitted, principal resolved. -----
    apply_governed_length_bound(intake.text, authorized=authorized, policy=policy)

    # --- interpretation step 5: governed untrusted-text screening (D-19 redaction rule) -----------
    # The matcher arrives through `collaborators` for the same reason the policy does. It used to be
    # the literal `None`, which made this step refuse for every input — see `redaction_matcher`.
    screen_question(intake.text, policy=policy, matcher=collaborators.redaction_matcher)

    # --- interpretation step 6: deterministic slot resolution, access-filtered --------------------
    resolutions = tuple(
        resolve_term(
            TermRequest(term=TermRef(start=start, length=len(surface)), slot=slot),
            surface,
            catalog=collaborators.catalog,
            authorized=authorized,
            on=on,
        )
        for surface, start, slot in _governed_surfaces(
            intake,
            catalog=collaborators.catalog,
            authorized=authorized,
            on=on,
            concepts=collaborators.concepts,
        )
    )

    # --- interpretation step 7: period resolution, D-18 rule via 001's canonical period -----------
    # `F12`: this used to pass `intake.text` — the *whole question* — to `resolve_governed_period`,
    # which matches by exact equality. No input could satisfy both halves: a text that was itself a
    # period surface carried no metric, and a text carrying a metric was not a period surface. The
    # question is now searched for the expression it *contains*, over the same spans step 6 resolves
    # terms across, so the two steps segment the question one way rather than two.
    #
    # The interval used to be `(reference_date, reference_date)` — a single day, passed from here,
    # which meant a named range like "julho de 2026" resolved to one day and the full range needed
    # date arithmetic **in this function**. `R-8` puts that arithmetic in `001`, so the owner
    # authorized the fifth seam instead: the deployment supplies a boundary resolver, the resolver
    # delegates the calendar to `001`, and `period.py` checks the zone and inclusivity it answers
    # with. No date is computed here, which is the property that authorization was protecting.
    period = resolve_period_in_question(
        intake.text,
        reference_date=intake.reference_date,
        vocabulary=vocabulary,
        resolver=collaborators.period_boundaries,
        on=on,
    )

    # --- interpretation step 8: optional model narrowing. Only when D-20 is declared. -------------
    #     Deliberately skipped when no port is injected: an absent optional dependency is not a
    #     degraded mode, it is the shipped state (`FR-092` of `003`).

    # --- interpretation step 9: assemble the resolved intent and derive identity ------------------
    intent = assemble_resolved_intent(
        resolutions,
        authorized=authorized,
        auth_fingerprint=auth_fingerprint,
        period=period,
        language=intake.language,
        reference_date=intake.reference_date,
        as_of=intake.as_of,
        catalog_release=_required_pin(authorized),
        policy_version=policy.version,
        vocabulary_version=vocabulary.version,
    )
    interpretation_id = derive_interpretation_identity(intent)

    # --- interpretation step 10: unresolved or ambiguous → issue a sealed clarification and stop
    outstanding = unresolved_slots(resolutions)
    if outstanding:
        clarification = issue_clarification(
            correlation_id=correlation_id,
            interpretation_id=interpretation_id,
            auth_fingerprint=auth_fingerprint,
            unresolved=outstanding[0],
            candidates=(),
            rounds_consumed=0,
            round_bound=policy.clarification_round_bound,
            issued_at=at,
            expiry=clarification_expiry,
            nonce=nonce,
            catalog_release=intent.catalog_release,
            policy_version=intent.policy_version,
            vocabulary_version=intent.vocabulary_version,
            port=collaborators.seal,
            key_id=collaborators.seal_key_id,
            algorithm=collaborators.seal_algorithm,
        )
        return ClarificationOutcome(clarification, _resolved_wording(intent))

    # --- interpretation step 11: comparison routing by expressibility -----------------------------
    if intent.comparison is not None:
        classify_route(
            ComparisonShape(
                primary_range=(period.start, period.end),
                baseline_range=_baseline_range(intent),
                differing_fields=frozenset(),
            )
        )

    # --- interpretation step 12: construct the governed request(s) deterministically --------------
    request = governed_request_for(intent, period)

    # --- interpretation step 13: catalog comparison verdict ---------------------------------------
    #     Two-execution route only, and no route is exercised here, so nothing is composed for it.
    #     The marker stays because the step is accounted for: composing an unreachable branch would
    #     be untested ordering, and `T110` is what proves the reachable path matches this feature's
    #     own components.

    # --- interpretation step 14: submit through the execution port --------------------------------
    executed = collaborators.execution.submit(
        request,
        authorized=authorized,
        auth_fingerprint=auth_fingerprint,
        correlation_id=interpretation_id,
    )

    # --- interpretation step 15: exact decimal comparison -----------------------------------------
    #     Two-execution route only, like step 13, and unreached for the same reason.

    # --- step 15b: build the claims the result supports -------------------------------------------
    #     Not a numbered step in the interpretation contract, and placed here because it is the
    #     translation between step 14's result and step 16's input. It used to not exist at all:
    #     step 16 passed `claims=()` against `min_length=1`, so every answer refused.
    #
    #     The plan and the result are handed over; `intake.text` deliberately is not. A constructor
    #     that could read the question could build a claim out of what the user typed, and
    #     `assert_claims_are_authorised` is what makes that structurally detectable rather than a
    #     rule somebody remembers: every subject must be an identifier the plan authorised or a
    #     label the result carried.
    wording = collaborators.claim_wording(on)
    claims = collaborators.claims(plan=request, result=executed.result, classes=wording)
    assert_claims_are_authorised(claims, plan=request, result=executed.result)

    # --- interpretation step 16: assemble the answer, emit RELEASE, then release ------------------
    answer = assemble_answer(
        intent,
        claims=claims,
        caveats=CaveatSet(caveats=(), total=0),
        provenance=(executed.provenance,),
        on=on,
        # The fourth seam. Passed rather than omitted: omitting it made assembly read
        # `claim-classes.yaml`, which is empty, and refuse for every answer.
        wording=wording,
    )
    return AnsweredOutcome(answer, _resolved_wording(intent))


def _required_pin(authorized: AuthorizedContext) -> str:
    """The governed authorization-policy pin the resolved context carries.

    Typed as optional upstream because a `PrincipalContext` may be constructed before resolution. By
    step 2 it must be present — an unresolved pin is exactly what
    :func:`resolve_authorization_context` refuses on — so an absent one here would mean step 2 was
    bypassed, and this raises rather than inventing a release identifier.
    """
    pin = authorized.context.authorization_policy_pin
    if pin is None:  # pragma: no cover - unreachable while step 2 precedes step 9
        raise AssertionError("step 2 completed without an authorization-policy pin")
    return pin


#: How a catalog concept kind maps onto a slot kind. The **catalog's** strings on the left, this
#: feature's enum on the right, and only the kinds the catalog can actually answer for. A period
#: entry is absent because no authored period vocabulary exists — ADR 0029 records that and does not
#: authorize inventing one, so a mapping for it would promise a resolution nothing can produce.
_SLOT_FOR_CONCEPT: dict[str, SlotKind] = {
    "metric": SlotKind.METRIC,
    "dimension": SlotKind.DIMENSION,
}


def _governed_surfaces(
    intake: QuestionIntake,
    *,
    catalog: CatalogDiscovery,
    authorized: AuthorizedContext,
    on: date,
    concepts: ConceptDiscovery | None = None,
) -> tuple[tuple[str, int, SlotKind], ...]:
    """The candidate surfaces the **catalog recognises**, in segmentation order.

    Two halves, and the split is the point of ADR 0027:

    * `segmentation.segment` says **where** candidate terms sit. It decides nothing;
    * `discover` and `classify` — this feature's own public functions — decide **which** of those
      spans names a governed concept the principal may see.

    Filtering here rather than handing every span to `resolve_term` is not a preference.
    `resolve_term` **raises** ``TERM_NOT_GOVERNED`` when nothing matches, which is correct for a
    term the caller meant and fatal for a candidate the caller was merely offering. So candidates
    are screened with the outcome-returning function first, and only recognised ones are resolved.

    Longest span wins: a span already accepted suppresses the shorter spans inside it, because
    resolving "instalações" again inside "instalações na Google Play" would put one concept in two
    slots.

    **The slot kind is read from the catalog, never decided here.**

    With a `ConceptDiscovery` injected, the kind comes from `001`'s concept surface — ADR 0029's
    addition — and is mapped through `_SLOT_FOR_CONCEPT`. A kind the catalog reports and this
    feature has no slot for is **skipped**, not guessed: reporting a span under some other slot
    would be this module deciding what the span means.

    With none injected, a recognised span is reported as ``SlotKind.METRIC``, because `001`'s metric
    surface is what resolved it. That is still reading an answer rather than deciding one.

    ## The screen is a union, and that is what closes `T108`

    Until 2026-08-19 the screen was `discover` **alone**, and `discover` delegates to `001`'s
    `CatalogApi.resolve`, which is **metric-only**: it walks the metric index and returns a
    `Candidate` carrying a `metric_id`. A span naming only a dimension returned `NotGoverned`, hit
    the `continue`, and never reached `_slot_for`. So tagging the six authored axes made the concept
    surface report `dimension` for all twenty-four of their routes and changed nothing here — the
    dimension slot was unreachable one layer earlier than anybody was looking.

    A span is now a candidate when **either** half recognises it:

    * the **metric resolver** does, exactly as before. Keeping it is not redundancy: `resolve`
      carries a fuzzy pass and `identify` is exact-match only, so screening on the concept surface
      alone would silently drop every fuzzy metric match `003`'s own suites rely on;
    * or the **concept surface** reports a kind this feature has a slot for. That surface is
      access-filtered by construction — it takes an `AccessContext` and returns nothing for a denial
      as for a non-match — so widening the screen to it discloses nothing a caller could not already
      ask `001` directly.

    With no concept surface injected the behaviour is bit-for-bit what it was: metric screen, metric
    slot.

    **What this still does not close.** Period and filter slots have no governed vocabulary to
    index, so a question needing one still routes to clarification at step 10. And a dimension is
    disclosed only when its own access tag authorises, which is now true for the six authored axes
    and remains false for any axis authored without a tag.
    """
    accepted: list[tuple[str, int, SlotKind]] = []
    covered: list[tuple[int, int]] = []
    for span in segment(intake.text):
        bounds = (span.start, span.start + span.length)
        if any(low <= bounds[0] and bounds[1] <= high for low, high in covered):
            continue

        outcome = discover(span.surface, catalog=catalog, authorized=authorized, on=on)
        resolves_as_metric = classify(outcome) is TermOutcome.RESOLVED
        slot = _slot_for(
            span.surface, concepts=concepts, on=on, resolves_as_metric=resolves_as_metric
        )
        if slot is None:
            # Neither half recognised the span, or the catalog reports only kinds this feature has
            # no slot for. Either way the span stays unresolved, which routes to clarification —
            # the honest outcome.
            continue
        accepted.append((span.surface, span.start, slot))
        covered.append(bounds)
    return tuple(accepted)


def _slot_for(
    surface: str,
    *,
    concepts: ConceptDiscovery | None,
    on: date,
    resolves_as_metric: bool,
) -> SlotKind | None:
    """The slot the catalog's answer supports for ``surface``, or ``None`` when it supports none.

    ``resolves_as_metric`` is what `001`'s metric resolver said about this span, passed in rather
    than re-asked so the catalog is reached once per span.

    Without a concept surface the answer is `METRIC` when the metric resolver resolved it and
    ``None`` otherwise. That is the pre-2026-08-19 behaviour exactly: the span was reported as a
    metric because `001`'s metric surface resolved it, which is reading an answer rather than
    deciding one.

    With a concept surface, **the catalog's own kind wins** — the surface returns kinds best first,
    so "first" is `001`'s ordering and not a preference applied here. A kind this feature has no
    slot for is skipped rather than guessed.

    The fallback to `METRIC` after the concept surface reports nothing usable is what preserves the
    fuzzy pass: `resolve` matches approximately and `identify` does not, so a fuzzily-matched metric
    reaches here with ``resolves_as_metric`` true and no reported kind. Dropping it would be a
    silent regression in `003`'s existing behaviour, dressed up as an improvement.
    """
    if concepts is not None:
        for kind in concepts.identify_kinds(surface, on=on):
            slot = _SLOT_FOR_CONCEPT.get(kind)
            if slot is not None:
                return slot
    return SlotKind.METRIC if resolves_as_metric else None


def _baseline_range(intent: ResolvedIntent) -> tuple[date, date] | None:
    """The baseline period's boundaries, when the comparison declares one."""
    comparison = intent.comparison
    if comparison is None or comparison.baseline_period is None:
        return None
    return (comparison.baseline_period.start, comparison.baseline_period.end)
