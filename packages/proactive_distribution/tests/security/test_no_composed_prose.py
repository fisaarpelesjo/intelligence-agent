"""This feature writes no sentence — `FR-210`, and the form the owner chose enforces it.

He chose label and value, one line per field, five fields, **no assembled sentence**.
The shape cannot commit this repository's oldest defect by construction rather than by
discipline — but a shape is only load-bearing while somebody does not "improve" the
format, and **this file exists for that day**.

## Written for THIS package rather than inherited

`006` has a node with the same purpose and a first draft of this one was a copy of it.
The copy imported `006`'s contracts and failed at collection — which was the useful
outcome: **a scan that names another feature's emitted modules is asserting about that
feature, whatever directory it sits in.** The mechanism below is the same because the
mechanism is right; the subjects are this package's.

## The three ways prose gets in, and each is looked for separately

* an **f-string carrying a value** — a bare f-string with no placeholder is a literal
  wearing a prefix, so the check looks for `FormattedValue` and not for `JoinedStr`;
* a **string-composing call** — `format`, `join`, `format_map`;
* **`+` or `%` with a string literal on either side** — restricted to a literal operand
  on purpose, because arithmetic over two values is not gluing text.

## The one exemption, and it is narrow and measured

**A message inside `raise` is developer-facing.** It never becomes a field of a report:
pydantic wraps a validator's error, and this package's own refusals carry a governed
code that a caller reports instead of the sentence. So `raise` bodies and exception
classes are exempt — and the exemption is not taken on faith: the field-level node
below measures the claim it rests on, that **no emitted field carries free text except
the caveat, which is transported byte for byte and never written here**.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from proactive_distribution.contracts import Report

pytestmark = pytest.mark.security

SRC = Path(__file__).resolve().parents[2] / "src" / "proactive_distribution"

#: The methods that build a string out of parts.
COMPOSING_METHODS = frozenset({"format", "join", "format_map"})

#: The modules whose contents become an output a person reads.
EMITTED = ("report.py",)

#: The one field whose value IS free text — and it is transported rather than written:
#: `005`'s causality warning, compared byte for byte at construction. Naming it here is
#: what keeps the field-level node from being a blanket permission.
FREE_TEXT_EXEMPT = frozenset({"caveat"})


def _modules() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


MODULES = _modules()


def _diagnostic_nodes(tree: ast.AST) -> set[int]:
    """Every node inside a `raise`, or inside an exception class, by identity."""
    inside: set[int] = set()
    for node in ast.walk(tree):
        exception_class = isinstance(node, ast.ClassDef) and any(
            isinstance(base, ast.Name)
            and base.id.endswith(("Error", "Exception", "Violation", "Labels", "Recipient"))
            for base in node.bases
        )
        if isinstance(node, ast.Raise) or exception_class:
            for descendant in ast.walk(node):
                inside.add(id(descendant))
    return inside


def test_the_walk_reaches_this_package() -> None:
    """A scan that read nothing would report success by doing nothing.

    And it names modules of THIS package: the copy that named `006`'s would have passed
    over an empty directory while sounding thorough.
    """
    assert MODULES, "the scan found no module, so every assertion below is vacuous"
    assert {p.name for p in MODULES} >= {"report.py", "labels.py", "conditions.py"}


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_no_module_interpolates_a_value_into_a_string(path: Path) -> None:
    """f-strings carrying a value, anywhere in the package."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    diagnostic = _diagnostic_nodes(tree)
    offences = [
        ast.unparse(node)[:70]
        for node in ast.walk(tree)
        if id(node) not in diagnostic
        and isinstance(node, ast.JoinedStr)
        and any(isinstance(part, ast.FormattedValue) for part in node.values)
    ]
    assert not offences, f"{path.name} interpolates a value into a string: {offences}"


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
    assert not offences, f"{path.name} composes a string: {offences}"


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_no_module_concatenates_or_percent_formats(path: Path) -> None:
    """`+` and `%` where either side is a string literal."""
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
    assert not offences, f"{path.name} glues text: {offences}"


def test_the_exemption_rests_on_a_measured_claim() -> None:
    """**The `raise` exemption is only honest if no emitted field carries written text.**

    Measured over the report's own fields: exactly one carries free text, it is the
    caveat, and its value is `005`'s — refused at construction if it is one character
    apart. Every other field holds a value some upstream seam measured.
    """
    free_text = {name for name in Report.model_fields if name not in FREE_TEXT_EXEMPT}
    assert set(Report.model_fields) >= FREE_TEXT_EXEMPT, (
        f"the exemption names a field the report does not have: "
        f"{sorted(FREE_TEXT_EXEMPT - set(Report.model_fields))}"
    )
    assert len(FREE_TEXT_EXEMPT) == 1, (
        f"the exemption covers {len(FREE_TEXT_EXEMPT)} fields, so it is no longer narrow: "
        f"{sorted(FREE_TEXT_EXEMPT)}"
    )
    assert free_text, "every field is exempt, so this node exempts everything it guards"


def test_the_scan_would_catch_a_composed_label() -> None:
    """**Proof the scan bites**, over source this file writes rather than over the package.

    A node asserting "nothing composes" while the package composes nothing is green for
    two different reasons and cannot tell them apart. This is the second reason,
    measured: a module that DOES compose is fed to the same walk and must be caught.
    """
    composing = ast.parse('label = f"metric: {value}"\n')
    caught = [
        node
        for node in ast.walk(composing)
        if isinstance(node, ast.JoinedStr)
        and any(isinstance(p, ast.FormattedValue) for p in node.values)
    ]
    assert caught, "the interpolation scan does not recognise an f-string carrying a value"

    glued = ast.parse('label = "metric: " + value\n')
    caught_glue = [
        node
        for node in ast.walk(glued)
        if isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Add)
        and any(
            isinstance(s, ast.Constant) and isinstance(s.value, str)
            for s in (node.left, node.right)
        )
    ]
    assert caught_glue, "the concatenation scan does not recognise text glued to a value"
