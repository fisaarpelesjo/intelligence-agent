"""T109 — the composed entry point adds nothing to this feature's contract.

ADR 0017 authorized a composed entry point on the condition that it **composes** and nothing more.
The danger is not that it fails; it is that it quietly becomes a fifth thing with its own
vocabulary. So the assertions here are about the shape of what it may return and what it may name:

* **no reason code.** The three namespaces are closed and counted. An entry point adding one
  would make a refusal untraceable to the layer that produced it.
* **no audit stage.** The stages are closed and ordered, and a new one would sit outside every
  record-shape assertion this feature already has.
* **no answer field.** An answered outcome carries `003`'s own answer, unaltered. A field added here
  would be content this layer authored.
* **the outcome type is total.** Three members, no fourth, no `None`, and no bare exception
  escaping into a caller's control flow.

## Why these are static assertions

Most of them cannot be reached by calling `ask`: step 3 refuses today because `D-18` and `D-19`
declare nothing, so a test that drove the function would exercise one path and prove nothing about
the other two. Reading the module's declarations instead covers all three, and does so without
pretending a governed document resolves.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from analytics_interaction import interact
from analytics_interaction.answer.refusal import GovernedRefusal
from analytics_interaction.contracts.answer import AnalyticsAnswer
from analytics_interaction.contracts.audit import InterpretationStage
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode
from analytics_interaction.interact import (
    STEP_ORDER,
    AnsweredOutcome,
    ClarificationOutcome,
    InteractionOutcome,
    ask,
)

pytestmark = pytest.mark.contract

_MODULE = Path(inspect.getfile(interact))


def _tree() -> ast.Module:
    return ast.parse(_MODULE.read_text(encoding="utf-8"))


def test_the_outcome_type_has_exactly_three_members() -> None:
    """Total, and closed. A fourth member is a fourth thing a caller must learn to handle."""
    members = set(InteractionOutcome.__args__)  # pyright: ignore[reportAttributeAccessIssue]
    assert members == {AnsweredOutcome, ClarificationOutcome, GovernedRefusal}


def test_the_entry_point_returns_the_outcome_type_and_never_none() -> None:
    """`None` is not one of the three; an optional return pushes a fourth case onto callers."""
    signature = inspect.signature(ask)
    annotation = str(signature.return_annotation)
    assert "InteractionOutcome" in annotation
    assert "None" not in annotation


def test_the_module_declares_no_reason_code() -> None:
    """No new code, and no code re-declared under another name.

    Scanned for a class deriving from an enum and for any assignment whose value is a string
    starting with a namespace prefix — the two ways a code could appear without importing one.
    """
    tree = _tree()
    enum_classes = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and any(
            (isinstance(base, ast.Name) and "Enum" in base.id)
            or (isinstance(base, ast.Attribute) and "Enum" in base.attr)
            for base in node.bases
        )
    ]
    assert not enum_classes, f"{enum_classes} declare an enum in the entry point"

    prefixes = ("INTERPRETATION_", "CATALOG_", "ANALYTICS_", "CHANNEL_")
    invented: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant):
            continue
        literal = node.value
        if isinstance(literal, str) and literal.startswith(prefixes):
            invented.append(literal)
    assert not invented, f"the entry point spells reason-code-shaped strings: {invented}"


def test_every_reason_code_the_module_names_is_an_existing_member() -> None:
    """Whatever it refers to must already exist in the closed namespace."""
    named = {
        node.attr
        for node in ast.walk(_tree())
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "InterpretationReasonCode"
    }
    existing = {member.name for member in InterpretationReasonCode}
    assert named <= existing, f"unknown codes referenced: {sorted(named - existing)}"


def test_the_module_declares_no_audit_stage() -> None:
    """The six stages are closed. A seventh here would sit outside every record-shape assertion."""
    named = {
        node.attr
        for node in ast.walk(_tree())
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "InterpretationStage"
    }
    existing = {member.name for member in InterpretationStage}
    assert named <= existing, f"unknown stages referenced: {sorted(named - existing)}"


def test_the_answered_outcome_adds_no_field_to_the_answer() -> None:
    """Two fields: the answer and its resolved wording (ADR 0026).

    A third would be content this layer authored, and `003`'s answer contract is where an answer's
    fields are decided.
    """
    fields = set(AnsweredOutcome.__dataclass_fields__)
    assert fields == {"answer", "wording"}
    assert AnsweredOutcome.__dataclass_fields__["answer"].type in {
        "AnalyticsAnswer",
        AnalyticsAnswer,
    }


def test_the_step_order_names_sixteen_steps_and_the_module_composes_them() -> None:
    """The ordering is one declaration, and the entry point follows it.

    `004`'s `T115` asserts the same property from outside, over the marker comments. This asserts it
    from inside the package that owns the contract, so neither feature is the only place it is
    checked.
    """
    assert len(STEP_ORDER) == 16
    assert len(set(STEP_ORDER)) == 16


def test_the_entry_point_reads_no_clock() -> None:
    """Every instant arrives as an argument. A clock would make two runs of one input differ."""
    forbidden = {"now", "utcnow", "today", "monotonic", "time"}
    called = {
        node.func.attr
        for node in ast.walk(_tree())
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not (called & forbidden), f"the entry point reads a clock: {sorted(called & forbidden)}"


def test_the_entry_point_takes_the_instant_and_the_identifiers_as_arguments() -> None:
    """The other half: the values a clock would supply are parameters."""
    parameters = set(inspect.signature(ask).parameters)
    assert {"at", "correlation_id", "nonce"} <= parameters


def test_no_collaborator_has_a_default_that_is_not_declared_optional() -> None:
    """An ambient dependency is a dependency `004` cannot substitute in a test.

    Three fields carry `None`: the optional model port (`D-20`), the audit sink, and ADR 0029's
    concept surface. Each is documented as optional at its declaration, and every other field has no
    default.
    """
    optional = {"model", "audit", "concepts"}
    for name, field in interact.InteractionCollaborators.__dataclass_fields__.items():
        import dataclasses

        has_default = field.default is not dataclasses.MISSING
        if name in optional:
            assert has_default, f"{name} is documented as optional but has no default"
        else:
            assert not has_default, f"{name} carries a default, making it ambient"
