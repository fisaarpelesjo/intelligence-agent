"""Cross-question reconstruction — T153 (FR-049; SC-024).

    A sequence of questions by one principal MUST NOT be able to reconstruct a
    suppressed figure. The judgement is governed by `D-19`'s disclosure rule;
    absent that rule, any question needing the judgement refuses. — `FR-049`

    Evidence: refused under the `D-19` disclosure rule; with the rule absent, the
    question refuses. — `tasks.md` T153

## The attack

One question returns a total. A second returns the same total minus one small
cohort. The difference is the cohort — and the cohort was suppressed precisely
because it was too small to disclose. Neither answer breaks a rule on its own;
the pair does, and nothing that looks at one question can see it.

## What this feature can and cannot do about it

Detecting it needs **memory of the principal's earlier questions**, which is state,
and this feature holds none. So there are exactly two honest positions, and the
shipped one is the first:

* **`D-19` absent** — the judgement cannot be made, so any question that would need
  it refuses. That is a real capability loss and is what happens today;
* **`D-19` present** — the rule names a window and what to do on reconstruction
  risk. Evaluating it still requires a store this feature does not own, so the
  rule's presence changes *which* refusal applies, not whether one applies.

What must not exist is a third position: a claim that reconstruction is prevented.
This file asserts the absence of that claim as directly as it asserts the refusals,
because the claim is the dangerous artefact — a reviewer reading "cross-question
disclosure: enforced" would stop looking for the store that would have to back it.

## Why the shipped half is asserted first

The tempting shape for this file is a fixture-enabled suite proving the rule is
honoured. That suite would be green today and would describe behaviour nobody can
run, so the shipped refusal comes first and the fixture-backed shape second, with
its limits stated.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

import analytics_interaction
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code
from analytics_interaction.governance.policy import load_policies, resolve_policy
from analytics_interaction.governance.resolve import ContentUnresolvable
from analytics_interaction.governance.schemas import DisclosureRule
from analytics_interaction.intake.screening import screen_question

from ..conftest import ON
from ..fixtures.clarifications import FIXTURE_MARKER, fixture_policy

pytestmark = pytest.mark.adversarial

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent

#: Question pairs whose *difference* is the suppressed figure.
#:
#: Held as pairs, because a single question is not the attack and a corpus of
#: single questions would test the wrong thing. Each pair is a plausible pair of
#: legitimate questions — which is why the rule has to be governed rather than
#: guessed at from wording.
DIFFERENCING_PAIRS: tuple[tuple[str, str, str], ...] = (
    (
        "total-minus-one-country",
        "installs em julho",
        "installs em julho excluindo o Brasil",
    ),
    (
        "widening-window",
        "installs de 1 a 30 de julho",
        "installs de 1 a 29 de julho",
    ),
    (
        "cohort-split",
        "installs por plataforma em julho",
        "installs em julho apenas Android",
    ),
    (
        "version-slice",
        "installs em julho",
        "installs em julho na versão 3.1.0",
    ),
    (
        "store-slice",
        "installs em julho",
        "installs em julho somente na App Store",
    ),
)

PAIR_IDS = [name for name, _, _ in DIFFERENCING_PAIRS]


# --- the corpus is a corpus of pairs ---------------------------------------------


def test_every_case_is_a_pair_whose_difference_is_the_target() -> None:
    """A single question is not the attack.

    Asserted so a later edit that flattened this into a list of questions would
    fail rather than quietly testing single-question suppression, which a different
    suite already covers.
    """
    assert len(DIFFERENCING_PAIRS) == 5
    for _, first, second in DIFFERENCING_PAIRS:
        assert first != second
        assert first.split()[0] == second.split()[0], "both halves ask about the same metric"


# --- the shipped state: the judgement cannot be made, so nothing proceeds --------


def test_no_disclosure_rule_is_in_force_today() -> None:
    """**The premise.** `D-19` ships with no approved instance.

    Stated first, because every refusal below follows from it — and because a
    future turn that authors a policy would make this fail loudly rather than
    silently changing what the rest of this file proves.
    """
    assert load_policies() == ()
    with pytest.raises(ContentUnresolvable):
        resolve_policy(ON)


@pytest.mark.parametrize("pair", DIFFERENCING_PAIRS, ids=PAIR_IDS)
def test_both_halves_of_every_pair_refuse_today(pair: tuple[str, str, str]) -> None:
    """**The load-bearing assertion for the shipped state.**

    Neither half proceeds, so no difference can be taken. The refusal is the
    policy-unresolvable one rather than a reconstruction-specific code, and that is
    correct: the system has not decided the question is dangerous, it has decided
    it cannot tell.
    """
    _, first, second = pair
    for text in (first, second):
        with pytest.raises(ContractViolation) as raised:
            screen_question(text, policy=None, matcher=None)
        assert raised.value.code is Code.INTERPRETATION_POLICY_UNRESOLVABLE


@pytest.mark.parametrize("pair", DIFFERENCING_PAIRS, ids=PAIR_IDS)
def test_the_refusal_does_not_depend_on_asking_the_first_half(
    pair: tuple[str, str, str],
) -> None:
    """Order-independent, because there is no memory of the first question.

    Which is the honest reason and worth pinning: an implementation that refused
    the second half *because* of the first would have state, and this feature's
    whole design says it does not.
    """
    _, first, second = pair
    outcomes: list[str] = []
    for text in (first, second, first, second):
        with pytest.raises(ContractViolation) as raised:
            screen_question(text, policy=None, matcher=None)
        outcomes.append(str(raised.value))
    assert len(set(outcomes)) == 1


# --- fixture-enabled: the rule's shape, and what it still cannot do -------------


def test_the_governed_rule_names_a_window_and_an_action() -> None:
    """**Fixture-only.** `D-19` remains open; this is the schema, not its content.

    Three fields, all required together. A rule carrying a window but no action, or
    an action but no window, does not construct — so there is no representable
    configuration in which the system knows how far to look back but not what to do
    about what it finds.
    """
    rule = fixture_policy()[0].cross_question_disclosure
    assert isinstance(rule, DisclosureRule)
    assert set(DisclosureRule.model_fields) == {
        "rule_id",
        "window_questions",
        "on_reconstruction_risk",
    }
    assert rule.window_questions > 0
    assert rule.on_reconstruction_risk
    assert FIXTURE_MARKER in rule.rule_id


@pytest.mark.parametrize(
    "incomplete",
    [
        pytest.param({"window_questions": 0}, id="zero-window"),
        pytest.param({"window_questions": -1}, id="negative-window"),
        pytest.param({"on_reconstruction_risk": ""}, id="no-action"),
        pytest.param({"rule_id": ""}, id="no-identifier"),
    ],
)
def test_an_incomplete_rule_does_not_construct(incomplete: dict[str, object]) -> None:
    """A partially-authored rule is not partially usable.

    The failure this forecloses: a window of zero reading as "look back nowhere",
    which is indistinguishable from "the rule is off" and would silently disable
    the control while the policy file said it was configured.
    """
    fields: dict[str, object] = {
        "rule_id": f"{FIXTURE_MARKER}-disclosure",
        "window_questions": 5,
        "on_reconstruction_risk": "refuse",
    }
    fields.update(incomplete)
    with pytest.raises(Exception) as raised:
        DisclosureRule(**fields)  # pyright: ignore[reportArgumentType]
    assert raised.value is not None


def test_a_present_rule_does_not_make_reconstruction_detectable() -> None:
    """**The honest limit, asserted rather than left to a reader's assumption.**

    With a synthetic policy in hand, screening runs and a question can proceed —
    and the pair is *still* undetectable, because evaluating a window of five
    questions requires remembering five questions. The rule's presence changes
    which refusal applies, not whether the sequence can be seen.
    """
    policy = fixture_policy()[0]

    class _Abstaining:
        def matches(self, pattern_id: str, text: str) -> bool:
            return False

    for _, first, second in DIFFERENCING_PAIRS:
        assert screen_question(first, policy=policy, matcher=_Abstaining()) is None
        assert screen_question(second, policy=policy, matcher=_Abstaining()) is None


# --- no module claims the control is enforced ------------------------------------


def test_no_module_keeps_a_history_of_questions() -> None:
    """The store that would be needed does not exist.

    Scanned as AST identifiers rather than text, so a docstring explaining that
    there is no history does not read as one. The names are the ones such a store
    would arrive under — and ``window`` is included even though it is innocuous
    elsewhere, because a per-principal question window is exactly the shape.
    """
    forbidden = (
        "question_history",
        "question_log",
        "asked_questions",
        "principal_history",
        "question_window",
        "recent_questions",
        "seen_questions",
        "disclosure_ledger",
    )
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            name = (
                node.id
                if isinstance(node, ast.Name)
                else node.attr
                if isinstance(node, ast.Attribute)
                else node.name
                if isinstance(node, ast.FunctionDef | ast.ClassDef)
                else ""
            )
            if name and any(banned in name.lower() for banned in forbidden):
                offenders.append(f"{path.relative_to(SRC).as_posix()}: {name}")
    assert not offenders, f"a question history exists: {offenders}"


def test_nothing_claims_cross_question_disclosure_is_enforced() -> None:
    """The dangerous artefact is the claim, not the gap.

    A reviewer reading "enforced" stops looking for the store that would have to
    back it. So no module may export a name asserting the control is active.
    """
    forbidden = (
        "reconstruction_prevented",
        "disclosure_enforced",
        "cross_question_enforced",
        "sequence_checked",
    )
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        offenders += [
            f"{path.relative_to(SRC).as_posix()}: {banned}"
            for banned in forbidden
            if banned in text
        ]
    assert not offenders, f"a module claims the control is enforced: {offenders}"


def test_the_scan_would_catch_a_planted_history() -> None:
    """A denylist never shown to fire proves nothing."""
    planted = ast.parse("class QuestionHistory:\n    recent_questions = []\n")
    names = {
        node.name if isinstance(node, ast.ClassDef) else getattr(node, "id", "")
        for node in ast.walk(planted)
    }
    assert any(
        "recent_questions" in name.lower() or "questionhistory" in name.lower() for name in names
    )
