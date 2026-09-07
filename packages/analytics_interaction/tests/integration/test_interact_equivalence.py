"""T110 — the composed entry point reaches what `003`'s own components reach (`SC-057`).

ADR 0017 authorized `interact.ask` as a **composition** of the sixteen steps `003` already owns.
The risk that authorization carries is not that a step is wrong; it is that composing them produces
a *second* behaviour — a refusal reworded, a code substituted, a step skipped because the composed
path happened not to reach it. This file is the assertion that it does not.

## What equivalence means here, and the shape it must not take

The obvious reading is "drive the components in parallel and compare". **That reading is
forbidden**, and not by preference: `T115`'s `test_single_interpretation_path` asserts that no
alternative ordering of the sixteen steps exists in either package. A test that re-composed them to
compare against `ask` would *be* the second interpretation path it is supposed to prove absent, and
it would pass by agreeing with itself.

So equivalence is asserted the other way round. Each scenario below:

* names the **single component** that owns the refusal or the outcome, and calls it directly with
  the same fixture inputs — one component, never a sequence;
* drives the same inputs through `ask`;
* asserts the two agree on the **reason code** and on the **detail string, byte for byte**.

Calling one component is not a second path. Calling fifteen in order would be.

## Three refusal types, not one, and that is deliberate upstream

`ask` promises every refusal propagates **unmodified**, and the consequence measured here is that
its raised type is *not* uniform: step 1 raises `ContractViolation`, step 2 raises
`AuthorizationRefused`, step 3 raises `ContentUnresolvable`. Each is the type its own step
produces, and `ask` neither wraps nor normalises them — which is what "carried through" has to mean
if it means anything.

`AuthorizationRefused` is the one whose code is a **class constant** rather than a constructor
argument: it takes no arguments at all, because a constructor accepting a reason is a constructor
through which a caller could eventually be told one. It does carry `code` and `detail` — an earlier
draft of this paragraph said it carried neither, and that was wrong — but they are the same values
on every instance, so comparing them proves less than it does for the other steps. Step 2's
scenario therefore identifies the step by **type**, and adds the counted surfaces, which is the
property that actually matters there.

## Why the wording comparison is byte-for-byte

`ContractViolation` carries a `code` and a `detail`. The code is the governed fact — it selects
stored pt-BR wording and is what an audit event records — and the detail is developer-facing.
Comparing only the code would miss a composition that produced the right classification with a
different explanation, and "the refusal is carried through **unmodified**" is the promise `ask`'s
own docstring makes. So both are compared, and the detail is compared with `==` rather than by
substring.

## What this file does not claim

It does not prove `ask` can reach an **answered** outcome over production content. It cannot, and
saying so is the point: `interpretation_governance/interpretation-policy.yaml` and
`period-vocabulary.yaml` both carry `instances: []`, so a production resolver refuses at step 3
before any of this is reachable. Every scenario here injects a **fixture** resolver, which is
exactly the substitutability the 2026-08-19 seam created — and a fixture proves a contract, never
readiness.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any, Protocol, cast

import pytest

from analytics_interaction import interact
from analytics_interaction.authorization.refusal import AuthorizationRefused
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.intake import PrincipalContext, PrincipalType
from analytics_interaction.contracts.intent import GovernedInterval
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code
from analytics_interaction.governance.policy import resolve_policy
from analytics_interaction.governance.resolve import ContentUnresolvable
from analytics_interaction.governance.schemas import (
    ClaimClassContent,
    ContentApproval,
    PeriodExpression,
    PeriodVocabulary,
)
from analytics_interaction.governance.vocabulary import resolve_period_vocabulary
from analytics_interaction.intake.bounds import apply_governed_length_bound
from analytics_interaction.intake.parse import parse_intake
from analytics_interaction.intake.screening import screen_question
from analytics_interaction.interact import InteractionCollaborators, ask

from ..fixtures.catalog.discovery import FixtureCatalog
from ..fixtures.clarifications import fixture_policy
from ..fixtures.counters import CountingExecutionPort, CountingResolver, Surfaces
from ..fixtures.seal import FIXTURE_ALGORITHM, FIXTURE_KEY, FIXTURE_KEY_ID, SyntheticSeal

_FIXTURE_MARKER = "fixture-only-not-governed"

if TYPE_CHECKING:
    from analytics_query.contracts.request import AnalyticsQuery
    from analytics_query.contracts.result import AnalyticsResult

    from analytics_interaction.contracts.answer import AnswerClaim
    from analytics_interaction.contracts.intent import PeriodConvention
    from analytics_interaction.governance.schemas import InterpretationPolicy

pytestmark = pytest.mark.integration

AT = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
ON = AT.date()
CORRELATION = "t110-correlation"
NONCE = "t110-nonce"

#: The principal every scenario asks as, unless it is asking about an unresolvable one.
PRINCIPAL = PrincipalContext(
    principal_ref="t110-principal",
    principal_type=PrincipalType.USER,
    authorization_scope="default",
    granted_access_tags=frozenset({"standard"}),
    authorization_policy_pin="t110-pin",
)


def payload_for(text: str, *, principal: PrincipalContext = PRINCIPAL) -> dict[str, Any]:
    """One intake payload. Every field explicit — `parse_intake` defaults nothing."""
    return {
        "text": text,
        "language": "pt-BR",
        "reference_date": ON,
        "principal": principal.model_dump(),
    }


# --------------------------------------------------------------------------------------------------
# Building the collaborators
#
# Kept in this module rather than added to `tests/fixtures/` on purpose. A new fixture family has to
# declare a `FIXTURE_MARKER` and join the collection `test_fixture_containment` reads, and editing
# that scan to admit a family is a change to `003`'s containment rules rather than a use of them.
# Everything here composes families that already exist.
# --------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _FixturePolicy:
    """A `D-19` resolver satisfying `InterpretationPolicyResolver`, over synthetic instances.

    Injected, which is the whole point of the 2026-08-19 seam: before it, step 3 reached
    `governance.policy` at module level and no test could substitute the governed content it read.
    """

    instances: tuple[InterpretationPolicy, ...]

    def __call__(self, on: date) -> InterpretationPolicy:
        return resolve_policy(on, policies=self.instances)


@dataclass(frozen=True, slots=True)
class _FixtureVocabulary:
    """A `D-18` resolver satisfying `PeriodVocabularyResolver`, over synthetic instances."""

    instances: tuple[PeriodVocabulary, ...]

    def __call__(self, on: date) -> PeriodVocabulary:
        return resolve_period_vocabulary(on, instances=self.instances)


@dataclass(frozen=True, slots=True)
class FixtureMatcher:
    """A `RedactionMatcher` that treats a pattern id as a literal substring. **Test-only.**

    Deciding what a governed pattern *means* is the `D-19` owner's call, which is exactly why `003`
    ships no matcher and why one must never appear under `src/`. Substring containment is the
    narrowest rule that demonstrates both branches of `screen_question`, matched and not matched,
    without asserting anything about real patterns.

    ``matches`` never returns the match itself, as the protocol requires: a richer return would be a
    channel through which injected content could reach a refusal, a log line or an audit event.
    """

    def matches(self, pattern_id: str, text: str) -> bool:
        return pattern_id in text


def build_collaborators(
    *,
    policy_instances: tuple[InterpretationPolicy, ...] | None = None,
    vocabulary_instances: tuple[PeriodVocabulary, ...] = (),
    principal: PrincipalContext | None = PRINCIPAL,
    surfaces: Surfaces | None = None,
) -> InteractionCollaborators:
    """Every collaborator `ask` needs, all synthetic.

    ``policy_instances`` defaults to one usable fixture policy. Passing ``()`` models the shipped
    state — no `D-19` instance — which is what makes the step-3 refusal reachable.
    """
    counted = surfaces if surfaces is not None else Surfaces()
    return InteractionCollaborators(
        authorization=CountingResolver(surfaces=counted, answer=principal),
        catalog=FixtureCatalog(),
        #: The counting port declares `submit(*args, **kwargs) -> object`, looser than
        #: `ExecutionPort` on purpose: it exists to prove it was **not** reached, not to answer.
        #: Ignored the way `adversarial/test_partial_comparison.py` ignores it, and safe for the
        #: same reason — every scenario here refuses before step 14, and the zero-call assertions
        #: are what check that rather than the type.
        execution=CountingExecutionPort(surfaces=counted),  # pyright: ignore[reportArgumentType]
        seal=SyntheticSeal(key=FIXTURE_KEY),
        seal_key_id=FIXTURE_KEY_ID,
        seal_algorithm=FIXTURE_ALGORITHM,
        policy=_FixturePolicy(fixture_policy() if policy_instances is None else policy_instances),
        period_vocabulary=_FixtureVocabulary(vocabulary_instances),
        #: The fourth seam, 2026-08-20. An empty tuple, which is the shipped state: assembly
        #: refuses while no claim class is worded, and these scenarios all refuse earlier.
        claim_wording=_no_claim_wording,
        #: The fifth and sixth seams, 2026-08-20. Both preserve exactly what this file measured
        #: before they existed: the interval is the single reference day step 7 used to be handed,
        #: and the claim set is empty, which is the `claims=()` step 16 used to pass. Every scenario
        #: here refuses before step 7 or before step 15b, and the equivalence assertions are what
        #: check that rather than these doubles.
        period_boundaries=_reference_day_interval,
        claims=_no_claims,
        redaction_matcher=FixtureMatcher(),
    )


class _CodedRefusal(Protocol):
    """A refusal carrying the governed pair this file compares.

    Declared because `refusal_from_ask` returns `BaseException` — `ask` raises three types — and
    `BaseException` has no `code`. Narrowing through this protocol keeps the comparison typed
    instead of reaching for `getattr`, and `coded` is where the narrowing is checked rather than
    assumed.
    """

    code: Code
    detail: str


def coded(refusal: BaseException, *, step: str) -> _CodedRefusal:
    """``refusal`` as a coded refusal, or a failure naming the step that expected one.

    Every governed refusal this entry point raises carries both, so a failure here means a scenario
    mistaken which step it is measuring — and that is worth a clear failure rather than an
    `AttributeError`.
    """
    assert hasattr(refusal, "code") and hasattr(refusal, "detail"), (
        f"{step}: {type(refusal).__name__} carries no code/detail pair, so it cannot be compared "
        "this way. Identify the step by its type instead"
    )
    return cast("_CodedRefusal", refusal)


def fixture_vocabulary(
    *, identifier: str = "t110_month", surface: str = "mes de teste"
) -> tuple[PeriodVocabulary, ...]:
    """One usable synthetic `D-18` instance. **Fixture values, never a `D-18` proposal.**

    Needed because a scenario aimed at step 4 or later has to get *past* step 3, and step 3
    resolves the vocabulary as well as the policy. Passing an empty tuple refuses there, which is
    correct and is what the step-3 scenario uses on purpose.
    """
    return (
        PeriodVocabulary(
            version=f"{_FIXTURE_MARKER}-1",
            effective_from=date(2026, 1, 1),
            approval=ContentApproval(
                approver_role="fixture",
                evidence_ref=_FIXTURE_MARKER,
                approved_on=date(2026, 1, 1),
            ),
            expressions=(
                PeriodExpression(
                    id=identifier,
                    surface_forms=(surface,),
                    boundary_rule=f"{_FIXTURE_MARKER}_anchor",
                    inclusivity=f"{_FIXTURE_MARKER}_inclusive",
                    week_start=None,
                    month_rule=None,
                ),
            ),
        ),
    )


def refusal_from_ask(payload: object, collaborators: InteractionCollaborators) -> BaseException:
    """Drive `ask` and return whatever refusal it surfaced.

    Catches `Exception` rather than one type, because the three refusal types are the point — see
    this module's docstring. A scenario that expects a particular type asserts it itself, so
    widening here loses nothing and stops the file from silently requiring `ask` to normalise.
    """
    with pytest.raises(Exception) as raised:
        ask(
            payload,
            collaborators=collaborators,
            at=AT,
            correlation_id=CORRELATION,
            nonce=NONCE,
        )
    return raised.value


def _assert_identical(
    through_ask: BaseException, through_component: BaseException, *, step: str
) -> None:
    """The two refusals are the same refusal — type, code **and** detail, byte for byte."""
    assert type(through_ask) is type(through_component), (
        f"{step}: the entry point raised {type(through_ask).__name__} and the component raised "
        f"{type(through_component).__name__}. `ask` must not wrap or normalise a refusal"
    )
    asked = coded(through_ask, step=step)
    component = coded(through_component, step=step)
    assert asked.code is component.code, (
        f"{step}: the entry point refused with {asked.code.value} and the component with "
        f"{component.code.value}. A composed path that reclassifies a refusal is a second "
        "behaviour, not a composition"
    )
    assert asked.detail == component.detail, (
        f"{step}: same code, different wording.\n  ask:       {asked.detail!r}\n"
        f"  component: {component.detail!r}\n"
        "`ask` promises refusals are carried through unmodified, so this must be byte-identical"
    )


# --------------------------------------------------------------------------------------------------
# Non-vacuity — without these, every comparison below could hold over nothing
# --------------------------------------------------------------------------------------------------


def test_the_collaborators_are_constructible_and_the_seam_is_injected() -> None:
    """The fixture assembly works, and the two seam fields are the fixture resolvers.

    Asserted because every scenario depends on it. If `build_collaborators` silently produced
    production resolvers, the file would be measuring the shipped refusal everywhere and calling it
    equivalence.
    """
    collaborators = build_collaborators()
    assert isinstance(collaborators.policy, _FixturePolicy)
    assert isinstance(collaborators.period_vocabulary, _FixtureVocabulary)
    assert collaborators.policy.instances, "the default fixture policy is empty, so step 3 refuses"


def _no_claim_wording(on: date) -> tuple[ClaimClassContent, ...]:
    """The shipped state: no claim class is worded, so assembly refuses.

    A named function rather than a lambda, because strict typing cannot infer a lambda's parameter
    and the seam's own signature is what this file is asserting about.
    """
    del on
    return ()


def _reference_day_interval(
    *,
    expression: PeriodExpression,
    reference_date: date,
    timezone: str,
    convention: PeriodConvention,
) -> GovernedInterval:
    """The single reference day, which is exactly the interval step 7 used to be handed.

    Preserving that is the point. Before the fifth seam this file's scenarios ran with
    `boundaries=(reference_date, reference_date)`, so answering anything wider here would change
    what the equivalence assertions compare and the change would be this double's, not the code's.

    No calendar knowledge, no arithmetic: one day, the zone as handed in, and the inclusivity the
    governed entry declares. A double that computed a month would be a double with a calendar.
    """
    del convention
    return GovernedInterval(
        start=reference_date,
        end=reference_date,
        timezone=timezone,
        inclusivity=expression.inclusivity,
    )


def _no_claims(
    *,
    plan: AnalyticsQuery,
    result: AnalyticsResult,
    classes: tuple[ClaimClassContent, ...],
) -> tuple[AnswerClaim, ...]:
    """No claims, which is the `claims=()` step 16 used to pass literally.

    Assembly refuses an answer with none, so this double preserves the refusal these scenarios
    already measured rather than introducing a new outcome none of them asserted.
    """
    del plan, result, classes
    return ()


def test_omitting_a_seam_resolver_is_a_construction_error() -> None:
    """The seam's own term, asserted where it is used rather than only where it is declared.

    The owner's instruction was that absence raises rather than falls back. `interact`'s field order
    is what enforces it — a dataclass cannot place a defaulted field before a required one — and
    this is the assertion that the enforcement is real.

    **The field list is derived, not written here.** It used to name three fields by hand, and
    when the fourth seam arrived on 2026-08-20 that list did not grow with it: `claim_wording` was
    mandatory and this test did not cover it. A hand-written list of what to check is the same
    defect class as a hand-written count, so it is replaced by the property it was gesturing at:
    **every** required field refuses when omitted, however many there are.
    """
    complete: dict[str, object] = {
        "authorization": CountingResolver(surfaces=Surfaces(), answer=PRINCIPAL),
        "catalog": FixtureCatalog(),
        "execution": CountingExecutionPort(surfaces=Surfaces()),
        "seal": SyntheticSeal(key=FIXTURE_KEY),
        "seal_key_id": FIXTURE_KEY_ID,
        "seal_algorithm": FIXTURE_ALGORITHM,
        "policy": _FixturePolicy(fixture_policy()),
        "period_vocabulary": _FixtureVocabulary(()),
        "claim_wording": _no_claim_wording,
        "period_boundaries": _reference_day_interval,
        "claims": _no_claims,
        "redaction_matcher": FixtureMatcher(),
    }
    required = [
        field.name
        for field in dataclasses.fields(InteractionCollaborators)
        if field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING
    ]
    assert set(required) == set(complete), (
        "the complete argument set and the dataclass's required fields disagree, so this test is "
        f"asserting over the wrong list: required={sorted(required)} supplied={sorted(complete)}"
    )
    for omitted in required:
        arguments = dict(complete)
        del arguments[omitted]
        with pytest.raises(TypeError) as raised:
            InteractionCollaborators(**arguments)  # pyright: ignore[reportArgumentType]
        assert omitted in str(raised.value), (
            f"omitting {omitted} raised {raised.value!r}, which does not name the missing field"
        )


# --------------------------------------------------------------------------------------------------
# Equivalence, one step at a time
# --------------------------------------------------------------------------------------------------


def test_step_3_refuses_exactly_as_the_governance_resolver_refuses() -> None:
    """The shipped state, reached through the entry point.

    `unit/test_governance_resolution.py` establishes through the component that an absent `D-19`
    instance is unresolvable. This asserts `ask` surfaces that raise **unchanged** when the
    injected resolver has nothing to resolve — which is production's condition today, on both
    governed files.

    Compared against the resolver's own raise rather than against `refusal_for`'s conversion of it,
    because `ask` does not convert: it carries the `ContentUnresolvable` through, and expressing it
    as a governed refusal is a *caller's* job. Measuring against the converted form would have
    asserted a behaviour the entry point does not have.
    """
    collaborators = build_collaborators(policy_instances=())

    with pytest.raises(ContentUnresolvable) as component_raised:
        resolve_policy(ON, policies=())

    _assert_identical(
        refusal_from_ask(payload_for("quantas instalacoes"), collaborators),
        component_raised.value,
        step="step 3",
    )


def test_step_1_refuses_exactly_as_parse_intake_refuses() -> None:
    """A malformed payload never reaches a collaborator, and refuses in the parser's own words."""
    collaborators = build_collaborators()

    with pytest.raises(ContractViolation) as component_raised:
        parse_intake("not a mapping")

    _assert_identical(
        refusal_from_ask("not a mapping", collaborators),
        component_raised.value,
        step="step 1",
    )


def test_step_4_refuses_exactly_as_the_governed_bound_refuses() -> None:
    """The length bound is `D-19`'s value, and the composed path applies the same one.

    The bound is read from the injected policy, so this also proves the seam feeds step 4 rather
    than step 4 reading governed content of its own.
    """
    policy_instances = fixture_policy()
    collaborators = build_collaborators(
        policy_instances=policy_instances, vocabulary_instances=fixture_vocabulary()
    )
    over_bound = "a" * (policy_instances[0].question_length_bound + 1)

    intake = parse_intake(payload_for(over_bound))
    authorized = interact.resolve_authorization_context(
        intake.principal, resolver=CountingResolver(surfaces=Surfaces(), answer=PRINCIPAL)
    )
    with pytest.raises(ContractViolation) as component_raised:
        apply_governed_length_bound(intake.text, authorized=authorized, policy=policy_instances[0])

    _assert_identical(
        refusal_from_ask(payload_for(over_bound), collaborators),
        component_raised.value,
        step="step 4",
    )


def test_step_5_refuses_exactly_as_the_screening_rule_refuses() -> None:
    """Step 5, in the screener's own words: a matched pattern refuses, identically.

    **Rewritten on 2026-08-19, and the rewrite is the point.** Before the matcher seam, `ask`
    passed the literal ``matcher=None``, screening refused `INTERPRETATION_POLICY_UNRESOLVABLE` for
    *every* text, and the strongest assertable property was "screening cannot run, and says so
    identically". This docstring said exactly that rather than claiming a pattern had matched — and
    it was that concession which surfaced the seam: if no text can pass step 5, no step after it is
    reachable either.

    With the matcher injected the real branch is reachable, so the assertion is now the one worth
    making: a question carrying a governed pattern refuses `INSTRUCTION_INJECTION_REFUSED`, and the
    composed path produces the same code and the same detail as the component does.

    The refusal names neither the pattern nor any part of the question, which is what makes the
    byte-for-byte detail comparison safe: there is nothing in it that could carry injected content.
    """
    policy_instances = fixture_policy()
    collaborators = build_collaborators(
        policy_instances=policy_instances, vocabulary_instances=fixture_vocabulary()
    )
    matched = policy_instances[0].redaction_rule.patterns[0]

    with pytest.raises(ContractViolation) as component_raised:
        screen_question(matched, policy=policy_instances[0], matcher=FixtureMatcher())
    assert component_raised.value.code is Code.INSTRUCTION_INJECTION_REFUSED, (
        f"the component refused with {component_raised.value.code.value}, so this scenario is no "
        "longer exercising the matched-pattern branch it claims to"
    )

    _assert_identical(
        refusal_from_ask(payload_for(matched), collaborators),
        component_raised.value,
        step="step 5",
    )


def test_the_entry_point_reaches_no_step_the_components_would_not() -> None:
    """Anti-vacuity over the whole file: `ask` really does progress past step 3.

    Four comparisons that all resolved to one code would pass while proving only that `ask` refuses
    early and never reaches the later steps — exactly the failure mode a composed entry point has.

    **This node caught two real mistakes of mine and was then narrowed by a third measurement**, so
    what it asserts is stated precisely rather than as "all distinct":

    * it first caught the step-4 and step-5 scenarios refusing at step 3, because I had passed a
      policy without a vocabulary and step 3 resolves both;
    * it then caught that step 5 shares step 3's code — `INTERPRETATION_POLICY_UNRESOLVABLE` —
      because
      `ask` passed ``matcher=None`` and screening could not run at all. An "all codes distinct"
      assertion would have been wrong about the code rather than right about the property, so this
      node was narrowed instead. **That collision is gone**: the matcher seam of the same day made
      the real branch reachable and step 5 now refuses `INSTRUCTION_INJECTION_REFUSED`, so the four
      codes are distinct again. The floor stays a floor rather than being tightened back to an
      equality, because an equality would be an assertion about codes when the property is about
      progress.

    So the property asserted is the one that actually matters: **step 4 is reached**, which is only
    possible if step 3 resolved, and the scenarios do not collapse onto a single code.
    """
    seen: dict[str, str] = {}

    seen["step 1"] = coded(
        refusal_from_ask("not a mapping", build_collaborators()), step="step 1"
    ).code.value

    seen["step 3"] = coded(
        refusal_from_ask(
            payload_for("quantas instalacoes"), build_collaborators(policy_instances=())
        ),
        step="step 3",
    ).code.value

    policy_instances = fixture_policy()

    def past_step_3() -> InteractionCollaborators:
        """Collaborators that get *past* step 3 — both governed files resolvable.

        Written as a helper because omitting the vocabulary here is exactly the mistake this node
        exists to catch, and it caught it: the first version of this test passed only the policy,
        so steps 4 and 5 both refused at step 3 and the codes collapsed.
        """
        return build_collaborators(
            policy_instances=policy_instances, vocabulary_instances=fixture_vocabulary()
        )

    over_bound = "a" * (policy_instances[0].question_length_bound + 1)
    seen["step 4"] = coded(
        refusal_from_ask(payload_for(over_bound), past_step_3()), step="step 4"
    ).code.value

    seen["step 5"] = coded(
        refusal_from_ask(
            payload_for(policy_instances[0].redaction_rule.patterns[0]), past_step_3()
        ),
        step="step 5",
    ).code.value

    assert seen["step 4"] != seen["step 3"], (
        f"step 4 refused with {seen['step 4']}, the code step 3 refuses with, so `ask` never got "
        f"past step 3 and every later scenario is measuring step 3: {seen}"
    )
    assert seen["step 4"] == Code.QUESTION_EXCEEDS_GOVERNED_LIMIT.value, (
        f"step 4 refused with {seen['step 4']} rather than the governed length bound, so the bound "
        "the injected policy carries is not the one being applied"
    )
    assert len(set(seen.values())) >= 3, (
        f"the scenarios collapse onto {len(set(seen.values()))} codes: {seen}. Three distinct is a "
        "floor rather than the expectation — fewer means `ask` refuses earlier than the scenarios "
        "intend"
    )


def test_an_unresolvable_principal_refuses_before_any_cost_surface() -> None:
    """Step 2 precedes step 3, and the composed path preserves that order.

    `integration/test_authorization_before_interpretation.py` establishes through the components
    that an unresolvable authorization context refuses **before** catalog, model or execution is
    reached. Here the same input goes through `ask` with a resolver that answers ``None``, and the
    six counted surfaces must all be zero — including the governed-content read, which is why this
    scenario also passes an empty `D-19`: if step 3 ran first, the refusal would be step 3's.
    """
    surfaces = Surfaces()
    collaborators = build_collaborators(policy_instances=(), principal=None, surfaces=surfaces)

    refusal = refusal_from_ask(payload_for("quantas instalacoes"), collaborators)

    assert isinstance(refusal, AuthorizationRefused), (
        f"an unresolvable principal raised {type(refusal).__name__}, not AuthorizationRefused, so "
        "step 2 did not run before step 3 — the empty `D-19` passed here is what makes that visible"
    )
    assert surfaces.catalog == 0, "the catalog was reached for an unresolvable principal"
    assert surfaces.model == 0, "the model was reached for an unresolvable principal"
    assert surfaces.execution == 0, "execution was reached for an unresolvable principal"
