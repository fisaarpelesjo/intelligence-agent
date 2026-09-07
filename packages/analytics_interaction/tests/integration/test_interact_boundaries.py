"""T111 — every refusal happens at its **required** step, and not at a later one (`SC-057`).

`T110` asserts that a refusal `ask` surfaces is byte-identical to the component's. This file
asserts something `T110` cannot: that the refusal happened **where the contract says it must**.
Those are different claims. A composition that ran step 5 before step 2 would still surface step
5's exact refusal — and would have read untrusted text before establishing who was asking.

## How "at its required step" is made checkable

Two shapes, and the second is the one that earns the file:

* **isolation** — an input that violates exactly one step's condition refuses with that step's
  code;
* **precedence** — an input that violates two steps' conditions refuses with the **earlier** one.
  This is what proves ordering rather than coincidence: if step 4 ran before step 2, a question
  that is both over-long and asked by an unresolvable principal would refuse with step 4's code.

Step 2 additionally carries a **counted** property: the six cost surfaces must all read zero,
because an unresolvable principal must not have caused a catalog read, a model call or an
execution.

## What this file covers, and what it cannot

Reachable through `ask` and covered here: steps **1, 2, 3, 4, 5, 6 and 7**.

Steps **10, 11, 13 and 14 are not reachable** through `ask` today, and the reason is measured
rather than assumed — but the reason is **not** the one this paragraph used to give.

It used to say step 7 passes `intake.text` — the *whole question* — to `resolve_governed_period`,
which matches by exact equality, so no input could be both a period surface and carry a metric.
`F12`'s correction removed that: step 7 now calls `resolve_period_in_question`, which searches the
question for the expression it *contains* over the same spans step 6 resolves terms across.

What still makes the four steps unreachable is the **other half** of the gap, unchanged: production
`D-18` declares no expression. `interpretation_governance/period-vocabulary.yaml` carries
`instances: []`, so the search finds nothing and step 7 raises
`PERIOD_EXPRESSION_NOT_GOVERNED` for every question. Closing that is `D-18`'s owner's governed act
and is not in this file's gift, so the four steps are named here as uncovered instead of being
simulated. `T111` is therefore **not** marked complete on this file alone.

The distinction is worth the words: after `F12`, a *populated* vocabulary would make these steps
reachable, which was not true before. The blocker moved from a mechanism this repository controls to
a governed record it does not.

## Collaborator builders are imported, not copied

`build_collaborators` and its fixtures live in `test_interact_equivalence`. Importing them keeps
one definition; copying them would create a second that drifts. They are not promoted to
`tests/fixtures/` because a new fixture family there has to declare a `FIXTURE_MARKER` and join the
collection `test_fixture_containment` reads, and editing that scan is a change to `003`'s
containment rules rather than a use of them.
"""

from __future__ import annotations

import pytest

from analytics_interaction.authorization.refusal import AuthorizationRefused
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code
from analytics_interaction.interact import InteractionCollaborators

from ..fixtures.counters import SURFACES, Surfaces
from .test_interact_equivalence import (
    build_collaborators,
    coded,
    fixture_policy,
    fixture_vocabulary,
    payload_for,
    refusal_from_ask,
)

pytestmark = pytest.mark.integration

#: A question naming a governed metric by a pt-BR surface with no underscore. `segment` treats
#: `_` as a boundary — Unicode category `Pc` — so a canonical id like `active_users` never forms
#: one span, and using one here would test segmentation rather than ordering.
GOVERNED_QUESTION = "instalacoes"

#: A text no governed vocabulary recognises, for scenarios that must not resolve anything.
UNGOVERNED_QUESTION = "palavra-que-nao-existe-no-catalogo"


def _usable(**overrides: object) -> InteractionCollaborators:
    """Collaborators whose governed content resolves, so a scenario can reach step 4 and beyond."""
    arguments: dict[str, object] = {
        "policy_instances": fixture_policy(),
        "vocabulary_instances": fixture_vocabulary(),
    }
    arguments.update(overrides)
    return build_collaborators(**arguments)  # pyright: ignore[reportArgumentType]


def _bound() -> int:
    """`D-19`'s governed question-length bound, read from the fixture instance."""
    return fixture_policy()[0].question_length_bound


def _matched_pattern() -> str:
    """The first pattern `D-19`'s redaction rule declares, as authored in the fixture."""
    return fixture_policy()[0].redaction_rule.patterns[0]


# --------------------------------------------------------------------------------------------------
# Isolation — one violated condition, one expected step
# --------------------------------------------------------------------------------------------------


def test_step_1_refuses_a_malformed_intake() -> None:
    """Structure first. Nothing downstream can be trusted to read an unparsed payload."""
    refusal = coded(refusal_from_ask("not a mapping", _usable()), step="step 1")
    assert refusal.code is Code.INTAKE_MALFORMED


def test_step_2_refuses_an_unresolvable_principal_with_every_surface_at_zero() -> None:
    """The counted property, over **all six** surfaces rather than the three that are easy.

    `Surfaces.counts()` is compared against a dict built from `SURFACES`, so a seventh surface
    added upstream and left unchecked fails here. Six separate assertions would not.
    """
    surfaces = Surfaces()
    refusal = refusal_from_ask(
        payload_for(GOVERNED_QUESTION), _usable(principal=None, surfaces=surfaces)
    )

    assert isinstance(refusal, AuthorizationRefused), (
        f"an unresolvable principal raised {type(refusal).__name__}, not AuthorizationRefused"
    )
    assert surfaces.counts() == dict.fromkeys(SURFACES, 0), (
        f"an unresolvable principal reached a cost surface: {surfaces.counts()}"
    )


def test_step_3_refuses_when_the_governed_policy_is_unresolvable() -> None:
    """The shipped state of `D-19`, reached through the entry point."""
    refusal = coded(
        refusal_from_ask(payload_for(GOVERNED_QUESTION), _usable(policy_instances=())),
        step="step 3",
    )
    assert refusal.code is Code.INTERPRETATION_POLICY_UNRESOLVABLE


def test_step_3_refuses_when_the_governed_vocabulary_is_unresolvable() -> None:
    """`D-18`'s half of step 3, asserted separately because it is a separate governed record.

    A single step-3 scenario would pass while one of the two reads was missing entirely.
    """
    refusal = coded(
        refusal_from_ask(payload_for(GOVERNED_QUESTION), _usable(vocabulary_instances=())),
        step="step 3",
    )
    assert refusal.code is Code.INTERPRETATION_VOCABULARY_UNRESOLVABLE


def test_step_4_refuses_a_question_over_the_governed_bound() -> None:
    """The bound is `D-19`'s value, not a constant in this feature."""
    over_bound = "a" * (_bound() + 1)

    refusal = coded(refusal_from_ask(payload_for(over_bound), _usable()), step="step 4")
    assert refusal.code is Code.QUESTION_EXCEEDS_GOVERNED_LIMIT


def test_step_5_refuses_text_the_governed_redaction_rule_matches() -> None:
    """Screening runs on untrusted text, and a match refuses without naming what matched."""
    matched = _matched_pattern()

    refusal = coded(refusal_from_ask(payload_for(matched), _usable()), step="step 5")
    assert refusal.code is Code.INSTRUCTION_INJECTION_REFUSED
    assert matched not in refusal.detail, (
        "the refusal detail carries the matched pattern, which is a channel for injected content"
    )


def test_step_7_refuses_a_period_no_governed_expression_covers() -> None:
    """Step 7, and the wall this file documents.

    Reached only because steps 1 to 6 passed, which is what makes it a boundary rather than an
    accident. It is also where every analytical question stops today — see this module's docstring.
    """
    refusal = coded(refusal_from_ask(payload_for(GOVERNED_QUESTION), _usable()), step="step 7")
    assert refusal.code is Code.PERIOD_EXPRESSION_NOT_GOVERNED


# --------------------------------------------------------------------------------------------------
# Precedence — two violated conditions, the earlier step wins
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "overrides", "text_kind", "expected"),
    [
        (
            "step 1 before step 2",
            {"principal": None},
            "malformed",
            Code.INTAKE_MALFORMED,
        ),
        (
            "step 3 before step 4",
            {"policy_instances": ()},
            "over_bound",
            Code.INTERPRETATION_POLICY_UNRESOLVABLE,
        ),
        (
            "step 3 before step 5",
            {"policy_instances": ()},
            "matched_pattern",
            Code.INTERPRETATION_POLICY_UNRESOLVABLE,
        ),
        (
            "step 4 before step 5",
            {},
            "over_bound_and_matched",
            Code.QUESTION_EXCEEDS_GOVERNED_LIMIT,
        ),
        (
            "step 5 before step 7",
            {},
            "matched_pattern",
            Code.INSTRUCTION_INJECTION_REFUSED,
        ),
    ],
)
def test_the_earlier_step_wins_when_two_conditions_are_violated(
    label: str, overrides: dict[str, object], text_kind: str, expected: Code
) -> None:
    """Ordering, asserted by conflict rather than by reading the source.

    Each row violates two steps' conditions at once. If the composition ran them in any other
    order, the later step's code would surface — which is exactly what a contract test can catch
    and a control-flow scan cannot, because a scan reads the order somebody wrote rather than the
    order that runs.

    Step 2 is the one case where the *earlier* step is asserted by type instead of by code, because
    `AuthorizationRefused`'s code is a class constant, identical on every instance, so the type is
    what identifies the step rather than the code.
    """
    matched = _matched_pattern()
    bound = _bound()

    texts: dict[str, object] = {
        "malformed": "not a mapping",
        "over_bound": payload_for("a" * (bound + 1)),
        "matched_pattern": payload_for(matched),
        "over_bound_and_matched": payload_for(matched + "a" * (bound + 1)),
    }

    refusal = refusal_from_ask(texts[text_kind], _usable(**overrides))
    assert coded(refusal, step=label).code is expected, f"{label}: ordering does not hold"


def test_step_2_precedes_step_3_even_though_step_3_would_also_refuse() -> None:
    """The precedence row that cannot be expressed as a code comparison.

    Both conditions are violated: the principal is unresolvable **and** no `D-19` instance exists.
    If step 3 ran first the refusal would be `ContentUnresolvable`; step 2 running first makes it
    `AuthorizationRefused`, and that is the ordering the contract requires — nothing may be read on
    behalf of a principal who was never established.
    """
    refusal = refusal_from_ask(
        payload_for(GOVERNED_QUESTION), _usable(principal=None, policy_instances=())
    )
    assert isinstance(refusal, AuthorizationRefused), (
        f"step 3 refused before step 2: got {type(refusal).__name__}"
    )


# --------------------------------------------------------------------------------------------------
# Non-vacuity
# --------------------------------------------------------------------------------------------------


def test_the_covered_steps_reach_distinct_codes() -> None:
    """Six isolation scenarios, and they must not collapse onto one early refusal.

    Without this, every assertion above could be measuring step 1 while claiming to measure its own
    step — the failure mode a composed entry point has, and one this file's own author hit twice
    while writing `T110`.
    """
    matched = _matched_pattern()
    bound = _bound()

    seen = {
        "step 1": coded(refusal_from_ask("not a mapping", _usable()), step="s1").code,
        "step 3 policy": coded(
            refusal_from_ask(payload_for(GOVERNED_QUESTION), _usable(policy_instances=())),
            step="s3p",
        ).code,
        "step 3 vocabulary": coded(
            refusal_from_ask(payload_for(GOVERNED_QUESTION), _usable(vocabulary_instances=())),
            step="s3v",
        ).code,
        "step 4": coded(
            refusal_from_ask(payload_for("a" * (bound + 1)), _usable()), step="s4"
        ).code,
        "step 5": coded(refusal_from_ask(payload_for(matched), _usable()), step="s5").code,
        "step 7": coded(
            refusal_from_ask(payload_for(GOVERNED_QUESTION), _usable()), step="s7"
        ).code,
    }

    assert len(set(seen.values())) == len(seen), (
        f"the isolation scenarios collapse onto fewer codes than steps: "
        f"{ {name: code.value for name, code in seen.items()} }"
    )


def test_the_uncovered_steps_are_named_rather_than_silently_skipped() -> None:
    """The four steps this file cannot reach, asserted to still be unreachable.

    A test that merely *documented* the gap in prose would go stale the moment `D-18` arrives, and
    nobody would notice that the gap had closed. This fails instead, which is the signal to write
    the scenarios for steps 10, 11, 13 and 14 rather than to relax the assertion.

    ## Why this node survived `T111` being marked complete

    On 2026-08-19 the owner narrowed `T111`'s criterion to the reachable steps and the task was
    marked. This node was **not** deleted with the removed half of the criterion, and that is
    deliberate: marking a task is a statement about scope, not a discovery that the missing coverage
    stopped mattering. Steps 10, 11, 13 and 14 are still unwritten and still needed.

    So what it signals changed, and only that. It used to mean "`T111` cannot be marked yet". It now
    means "the deferred coverage can come back" — the ledger row records exactly which four steps
    were removed from the criterion, and this failing node is what tells someone the removal has
    expired. Deleting it would have made the narrowing permanent by accident.
    """
    refusal = coded(refusal_from_ask(payload_for(GOVERNED_QUESTION), _usable()), step="the wall")
    assert refusal.code is Code.PERIOD_EXPRESSION_NOT_GOVERNED, (
        f"an analytical question now refuses with {refusal.code.value} rather than at step 7. The "
        "period gap may have closed — if so, steps 10, 11, 13 and 14 became reachable and T111's "
        "remaining scenarios must be written rather than this assertion adjusted"
    )
