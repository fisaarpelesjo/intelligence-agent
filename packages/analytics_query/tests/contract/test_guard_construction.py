"""Guard 1 — construction — T053 (FR-002; SC-001).

The first of three independent guards, and the one enforced by the type system.
``render`` accepts a ``QueryStructure`` and nothing else, so there is no
signature through which a caller string becomes query text.

This test asserts the property statically rather than by running a query,
because the failure it guards against is a *refactor*: someone adding a
``sql: str`` parameter, a ``raw`` variant, or an f-string that formats request
data into ``text``. All three would pass every behavioural test and defeat the
design.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from analytics_query.compile import render as render_module
from analytics_query.execution.adapter import RenderedQuery

pytestmark = pytest.mark.contract

COMPILE_DIR = Path(render_module.__file__).parent
_MODULES = sorted(COMPILE_DIR.glob("*.py"))


def test_the_scan_sees_the_compile_package() -> None:
    assert len(_MODULES) >= 4


def test_render_accepts_only_a_query_structure() -> None:
    signature = inspect.signature(render_module.render)
    assert list(signature.parameters) == ["structure"]
    annotation = signature.parameters["structure"].annotation
    assert "QueryStructure" in str(annotation)


def test_there_is_no_raw_or_overloaded_render() -> None:
    """No escape hatch beside the front door."""
    exported = {name for name in dir(render_module) if not name.startswith("_")}
    for forbidden in ("render_raw", "render_sql", "render_text", "raw_query", "from_string"):
        assert forbidden not in exported


@pytest.mark.parametrize("path", _MODULES, ids=lambda p: p.name)
def test_no_compile_function_takes_a_bare_string(path: Path) -> None:
    """A `str` parameter in `compile/` is the shape of the defect.

    Values arrive as bound parameters; identifiers arrive resolved from the
    catalog. Neither needs a public function here to accept a raw string.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name.startswith("_"):
            continue
        for arg in [*node.args.args, *node.args.kwonlyargs]:
            if arg.arg == "self" or arg.annotation is None:
                continue
            if ast.unparse(arg.annotation).strip().strip('"') == "str":
                offenders.append(f"{node.name}({arg.arg}: str)")
    assert not offenders, f"{path.name} accepts caller text: {offenders}"


@pytest.mark.parametrize("path", _MODULES, ids=lambda p: p.name)
def test_no_module_interpolates_into_a_text_assignment(path: Path) -> None:
    """Catches an f-string or concatenation building `text` from a value.

    `render` assembles `text` from governed identifiers and generated
    placeholder names only; the emitted-text guard then re-checks the result, so
    this is the static half of a two-sided assertion.
    """
    source = path.read_text(encoding="utf-8")
    for marker in ("% (", ".format(value", "+ value", "+ str(value", 'f"{value'):
        assert marker not in source, f"{path.name} interpolates a value: {marker!r}"


def test_the_rendered_query_separates_text_from_parameters() -> None:
    fields = set(RenderedQuery.__dataclass_fields__)
    assert fields == {"text", "parameters"}
