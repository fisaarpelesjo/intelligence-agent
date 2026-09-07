"""This feature composes no prose — T020 (`FR-013`).

**Inherited from `005:T029` rather than rediscovered, including its correction.**
`005` first wrote this node against MODULES — no string built anywhere in the package —
and had to correct it: a message inside `raise ValueError(...)` never reaches an output,
and banning it forced a choice between a test whose name lied and mutilating the
diagnostics that make a refusal debuggable.

**So the criterion is the FIELD.** No emitted field may hold a sentence this feature
composed. The module-level scan is kept as the outer ring, with the same narrow
exemption for diagnostics, because a composed sentence that reaches a field has to be
built somewhere first.

## What this feature has that `005` did not

Every string field here is a `GovernedName` — lower snake case, bounded at sixty-four
characters — except `caveats`. **A field typed that way cannot hold a sentence at all**,
and that is asserted by construction rather than by reading the annotations: the pattern
refuses the exact prose `spec.md` § 2 warns about.

`caveats` is the one free-text field, in both the placed and the unplaced finding, and
it is **transported**: `FR-011` requires the input finding's caveats to arrive at the
output position unchanged, and `T021` measures that they arrive byte for byte. A caveat
is the source's sentence, delivered as the value of a named field, never ours.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from insights_prioritisation.contracts import PriorityComponent

pytestmark = pytest.mark.security

SRC = Path(__file__).resolve().parents[2] / "src" / "insights_prioritisation"

#: String-building method names. `format` and `join` are the two that read as innocent;
#: `%` and `+` are caught structurally below.
COMPOSING_METHODS = frozenset({"format", "join", "format_map"})

#: The emitted contracts. **Named, because the exemption below is only defensible if
#: this list is what the exemption is measured against**, and a node asserts the list
#: still equals what the directory holds.
EMITTED = ("component.py", "ordering.py", "prioritised.py", "run.py")

#: The only fields of an emitted contract that may hold free text, **listed by owning
#: class rather than by field name** so a `caveats` appearing elsewhere is not quietly
#: excused by sharing a name. Both are transported verbatim — see `T021`.
ALLOWED_FREE_TEXT: dict[str, frozenset[str]] = {
    "PrioritisedFinding": frozenset({"caveats"}),
    "NotPrioritisable": frozenset({"caveats"}),
}

#: `str` as a whole word inside an annotation. Catches `str`, `str | None` and
#: `tuple[str, ...]`, and does not catch `GovernedName`, which is the bounded type.
BARE_STR = re.compile(r"\bstr\b")


def _diagnostic_nodes(tree: ast.AST) -> set[int]:
    """Every node inside a `raise`, or inside an exception class, by identity.

    **The exemption, and it is narrow.** A message inside `raise` is developer-facing:
    pydantic wraps it in a `ValidationError` that never reaches an emitted field.
    `FR-013` is about what this feature WRITES INTO AN OUTPUT.

    **The exemption is not taken on faith.** The field-level node below measures the
    claim it rests on.
    """
    inside: set[int] = set()
    for node in ast.walk(tree):
        exception_class = isinstance(node, ast.ClassDef) and any(
            isinstance(base, ast.Name) and base.id.endswith(("Error", "Exception", "Violation"))
            for base in node.bases
        )
        if isinstance(node, ast.Raise) or exception_class:
            for descendant in ast.walk(node):
                inside.add(id(descendant))
    return inside


def _modules() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


MODULES = _modules()


def test_the_walk_reaches_the_package() -> None:
    """A scan that read nothing would report success by doing nothing."""
    assert MODULES
    assert {p.name for p in MODULES} >= {"prioritised.py", "ties.py", "within_class.py"}


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_no_module_interpolates_a_value_into_a_string(path: Path) -> None:
    """f-strings carrying a value, anywhere in the package.

    **A bare f-string with no placeholder is not composition** — it is a literal wearing
    a prefix — so the check looks for `FormattedValue`, not for `JoinedStr`.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    diagnostic = _diagnostic_nodes(tree)
    offences = [
        ast.unparse(node)[:70]
        for node in ast.walk(tree)
        if id(node) not in diagnostic
        and isinstance(node, ast.JoinedStr)
        and any(isinstance(part, ast.FormattedValue) for part in node.values)
    ]
    assert not offences, f"{path.name} interpolates: {offences}"


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_no_module_calls_a_string_composing_method(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    diagnostic = _diagnostic_nodes(tree)
    offences = [
        ast.unparse(node)[:70]
        for node in ast.walk(tree)
        if id(node) not in diagnostic
        and isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in COMPOSING_METHODS
    ]
    assert not offences, f"{path.name} composes: {offences}"


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_no_module_concatenates_or_percent_formats(path: Path) -> None:
    """`+` and `%` where either side is a string literal.

    Restricted to a literal operand on purpose: `a + b` over two `Decimal` components is
    arithmetic this feature will do the day `D-A` is answered, and banning it would ban
    the composition. **What it cannot do is glue text.**
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    diagnostic = _diagnostic_nodes(tree)
    offences: list[str] = []
    for node in ast.walk(tree):
        if id(node) in diagnostic:
            continue
        if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Add | ast.Mod):
            continue
        sides = (node.left, node.right)
        if any(isinstance(s, ast.Constant) and isinstance(s.value, str) for s in sides):
            offences.append(ast.unparse(node)[:70])
    assert not offences, f"{path.name}: {offences}"


@pytest.mark.parametrize("name", EMITTED)
def test_no_emitted_field_is_free_text_except_the_transported_caveats(name: str) -> None:
    """**The requirement measured where it lives: the fields, not the modules.**

    Every field is a number, an enum, an instant, a nested contract, or a bounded name.
    The two exceptions are `caveats` on the placed and the unplaced finding, and both
    are transported: the input finding's own sentences, arriving unchanged.
    """
    tree = ast.parse((SRC / "contracts" / name).read_text(encoding="utf-8"))
    free_text: list[str] = []

    for klass in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
        allowed = ALLOWED_FREE_TEXT.get(klass.name, frozenset())
        for node in klass.body:
            if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
                continue
            field = node.target.id
            if field.startswith("_") or field in allowed:
                continue
            annotation = ast.unparse(node.annotation)
            if BARE_STR.search(annotation):
                free_text.append(f"{klass.name}.{field}: {annotation}")

    assert not free_text, f"{name} declares free text fields: {free_text}"


def test_the_exemption_is_narrow_and_measured() -> None:
    """The emitted contracts are the ones this feature hands out.

    Named here so the exemption above cannot quietly widen: if a fifth emitted contract
    appears and is not added, this fails rather than letting its fields go unscanned.
    """
    contracts = {
        p.name
        for p in (SRC / "contracts").glob("*.py")
        if p.name not in {"__init__.py", "_base.py", "reason_codes.py"}
    }
    assert contracts == set(EMITTED)


def test_a_governed_name_cannot_hold_the_sentence_the_spec_warns_about() -> None:
    """**The type refuses prose, so the field cannot carry it even if someone tried.**

    The annotation scan above proves no field is DECLARED free text. This proves the
    declared type is not free text either — the shape of composed sentence `spec.md` § 2
    warns about, refused by the pattern rather than by review.
    """
    for prose in (
        "o segmento brasil puxou a queda",
        "Downloads caiu porque o preco mudou",
        "a" * 65,
    ):
        with pytest.raises(ValidationError):
            PriorityComponent(name=prose, read_from="candidate_finding", value=None)


def test_the_scan_would_catch_a_composed_label() -> None:
    """**Proof the scan bites**, rather than a claim that it does.

    The sentence `FR-013` forbids, run through the same three predicates. Without this,
    the emptiness above could be an artefact of a check that matches nothing.
    """
    composed = (
        "def render(label):\n"
        '    return "O segmento " + label + " puxou a queda"\n'
        "def render_two(label):\n"
        '    return f"O segmento {label} puxou a queda"\n'
        "def render_three(label):\n"
        '    return "O segmento {} puxou".format(label)\n'
    )
    tree = ast.parse(composed)

    interpolated = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.JoinedStr) and any(isinstance(p, ast.FormattedValue) for p in n.values)
    ]
    methods = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr in COMPOSING_METHODS
    ]
    glued = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.BinOp)
        and isinstance(n.op, ast.Add | ast.Mod)
        and any(isinstance(s, ast.Constant) and isinstance(s.value, str) for s in (n.left, n.right))
    ]

    assert interpolated, "the f-string predicate does not bite"
    assert methods, "the format predicate does not bite"
    assert glued, "the concatenation predicate does not bite"


def test_the_field_scan_would_catch_a_free_text_field() -> None:
    """**Proof the field predicate bites**, on each of the three shapes it must catch.

    And that it does NOT catch the bounded name, which is the whole reason the emitted
    contracts come back clean.
    """
    declared = (
        "class Emitted:\n"
        "    headline: str\n"
        "    subtitle: str | None\n"
        "    notes: tuple[str, ...]\n"
        "    name: GovernedName\n"
    )
    tree = ast.parse(declared)
    caught = [
        node.target.id
        for klass in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
        for node in klass.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and BARE_STR.search(ast.unparse(node.annotation))
    ]
    assert caught == ["headline", "subtitle", "notes"], (
        "the free-text predicate missed a shape, or caught the bounded name"
    )
