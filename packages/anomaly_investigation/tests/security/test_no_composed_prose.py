"""This feature composes no prose — T029 (`FR-013`, third half of `SC-003`).

**The strongest guarantee here, and the one closest to `004`'s `T090`.** A
dimension label arriving from a warehouse row may read *"queda causada por mudança
de preço"*. It is **still delivered** — withholding source data would be a worse
feature — but as the value of a named field, never as a sentence a reader would
attribute to us.

`FR-013` and `FR-014` together leave the output as **structured values plus one
literal warning**. So the check is structural: on any path that reaches an emitted
field, no string may be **built**.

**What "built" means, precisely**, because a rule that banned every `+` would ban
arithmetic and a rule that banned every f-string would ban error messages nobody
emits:

* an **f-string** whose parts include a value — `JoinedStr` with a `FormattedValue`;
* `str.format`, `str.join`, `%`-formatting, and `+` between strings;
* applied to code that can reach an **emitted** contract.

**The one literal that may exist is the warning**, and it is transported: the
contract compares it byte-for-byte against the baseline, so it cannot be a
paraphrase and cannot be assembled.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.security

SRC = Path(__file__).resolve().parents[2] / "src" / "anomaly_investigation"

#: String-building method names. `format` and `join` are the two that read as
#: innocent; `%` and `+` are caught structurally below.
COMPOSING_METHODS = frozenset({"format", "join", "format_map"})

#: Emitted contracts. **Named, because the exemption below is only defensible if
#: this list is what the exemption is measured against.**
EMITTED = ("candidate.py", "investigation.py", "segment.py", "run.py")

#: The only fields of an emitted contract that may hold a free string, **listed by
#: owning class rather than by field name** so a `text` appearing elsewhere is not
#: quietly excused by sharing a name.
#:
#: All three are **transported, never composed**: the warning is compared
#: byte-for-byte against the baseline; `upstream_code` carries another layer's word
#: verbatim; and `SourceValue.text` is the whole point of `FR-014` — the source's
#: own text, delivered as the value of a named field that says where it came from.
ALLOWED_FREE_TEXT: dict[str, frozenset[str]] = {
    "CandidateFinding": frozenset({"causality_warning"}),
    "Investigation": frozenset({"causality_warning"}),
    "SourceValue": frozenset({"text"}),
    "Withholding": frozenset({"upstream_code"}),
}


def _diagnostic_nodes(tree: ast.AST) -> set[int]:
    """Every node inside a `raise`, or inside an exception class, by identity.

    **The exemption, and it is narrow.** A message inside `raise ValueError(...)`
    is a developer-facing detail: pydantic wraps it in a `ValidationError` that
    never reaches an emitted field. `FR-013` is about what this feature *writes
    into an output*, and refusing every f-string everywhere would ban the
    diagnostics that make a refusal debuggable — while catching nothing a reader
    would ever see.

    **The exemption is not taken on faith.** The test below measures that no
    emitted contract field is assigned composed text, which is the claim the
    exemption rests on.
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
    assert any(p.name == "candidate.py" for p in MODULES)


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_no_module_interpolates_a_value_into_a_string(path: Path) -> None:
    """f-strings carrying a value, anywhere in the package.

    **A bare f-string with no placeholder is not composition** — it is a literal
    wearing a prefix — so the check looks for `FormattedValue`, not for
    `JoinedStr`.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    diagnostic = _diagnostic_nodes(tree)
    offences: list[str] = []
    for node in ast.walk(tree):
        if id(node) in diagnostic:
            continue
        if isinstance(node, ast.JoinedStr) and any(
            isinstance(part, ast.FormattedValue) for part in node.values
        ):
            offences.append(ast.unparse(node)[:70])
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

    Restricted to a literal operand on purpose: `a + b` over two `Decimal`s is
    arithmetic this feature does, and banning it would ban the reconciliation.
    **What it cannot do is glue text.**
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


def test_the_scan_would_catch_a_composed_label() -> None:
    """**Proof the scan bites**, rather than a claim that it does.

    The exact sentence `FR-014` forbids, run through the same predicates. Without
    this, the emptiness above could be an artefact of a check that matches
    nothing.
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


def test_the_governed_warning_is_a_literal_and_not_assembled() -> None:
    """The one sentence that may exist is **transported**, not composed.

    It lives as a module-level constant and the contract compares it byte-for-byte
    against the baseline, so it can be neither paraphrased nor built.
    """
    source = (SRC / "contracts" / "candidate.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    warning = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) == "REQUIRED_CAUSALITY_WARNING" for t in node.targets)
    )
    assert isinstance(warning.value, ast.Constant)
    assert isinstance(warning.value.value, str)


@pytest.mark.parametrize("name", EMITTED)
def test_no_emitted_field_is_free_text_except_the_governed_warning(name: str) -> None:
    """**The requirement measured where it lives: the fields, not the modules.**

    An earlier version of this file asserted that emitted modules compose nothing
    *at all*, including inside a `raise`. That was rigour I invented: `FR-013` is
    about **what this feature writes into an output**, and a `ValueError` message
    never reaches one. Keeping it would have forced a choice between a test whose
    name lied and mutilating diagnostics that make a refusal debuggable.

    What the requirement actually needs is that **no emitted field can hold a
    sentence of ours**. Every field is a number, an enum, a window, a record, a
    bounded name, or a `SourceValue` — which carries the source's text and says so.
    The exceptions are exact and both are transported: `causality_warning`, which
    the contract compares byte-for-byte against the baseline, and `upstream_code`,
    which carries another layer's word verbatim.
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
            if annotation == "str" or annotation.startswith("str "):
                free_text.append(f"{klass.name}.{field}: {annotation}")

    assert not free_text, f"{name} declares free text fields: {free_text}"


def test_the_exemption_is_narrow_and_measured() -> None:
    """The four emitted contracts are the ones this feature hands out.

    Named here so the exemption above cannot quietly widen: if a fifth emitted
    contract appears and is not added, this fails.
    """
    contracts = {
        p.name
        for p in (SRC / "contracts").glob("*.py")
        if p.name not in {"__init__.py", "_base.py", "reason_codes.py", "rule.py"}
    }
    assert contracts == set(EMITTED)
