"""`T910`, `FR-902` — the caller carries no word of the message, and the budget stays at seven.

## The cheap and obvious failure of spec `009`

An automated path that quietly diverges from the manual one, so that **the thing tested and the
thing delivered stop being the same thing**. It starts small: a heading the caller adds "just for
the scheduled run", a KPI it skips because it was noisy at four in the morning, a word about the
day. `008` spent eleven cycles deciding what the message says, with his word on every one of them,
and none of those decisions is the caller's to re-take.

So this walks the caller's syntax tree and refuses the material a message is made of. It reads a
file in `tools/`, which no other node in this package does, and that is deliberate: **the file is
where the defect would live, and a guard that cannot reach it is the tautology of cycle 408.**
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from daily_reporting.report import template

pytestmark = pytest.mark.security

#: `tests/security/` -> `tests/` -> package -> `packages/` -> repository.
REPO = Path(__file__).resolve().parents[4]
CALLER = REPO / "apps" / "telegram-bot" / "run_daily.py"
METRICS = REPO / "semantic" / "metrics"

#: The modules that decide what the message says. The caller must not reach any of them.
THE_MESSAGE = ("daily_reporting.report", "summary", "template", "scope")

#: What a rendered line is made of, in the vocabulary this repository already guards. Matched as
#: substrings, so each one has to be a token that cannot occur in ordinary prose.
FORMATTING = ("{:", "%.", ":.2f", "ljust", "rjust", "<b>", "·")

#: The units a number wears. Matched as WHOLE WORDS: `pp` as a substring hits "happen", and a node
#: that fires on a docstring is a node people learn to work around.
UNITS = frozenset({"pp", "%", "R$", "US$"})


def _tree() -> ast.Module:
    return ast.parse(CALLER.read_text(encoding="utf-8"))


def _strings() -> list[str]:
    """Every string literal in the caller **except the docstrings**.

    A docstring never reaches the message, and a guard that fires on one teaches people to write
    worse documentation to keep it quiet.
    """
    tree = _tree()
    documentation = {
        id(node.body[0].value)
        for node in [tree, *ast.walk(tree)]
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in documentation
    ]


def _kpi_names() -> set[str]:
    found: set[str] = set()
    for path in sorted(METRICS.glob("*.yaml")):
        payload: object = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        typed = cast("dict[str, Any]", payload)
        if typed.get("kind") != "metric":
            continue
        for raw in cast("tuple[object, ...] | list[object]", typed.get("versions") or ()):
            if isinstance(raw, dict):
                version = cast("dict[str, Any]", raw)
                kpi = version.get("kpi_name")
                if isinstance(kpi, str):
                    found.add(kpi)
    return found


def test_the_caller_exists_where_this_node_looks() -> None:
    """A guard pointed at a path that moved is a guard that passes forever."""
    assert CALLER.is_file(), f"{CALLER} is missing; this node would forbid nothing"


def test_the_caller_names_no_kpi() -> None:
    """**Which KPIs the reader sees is the shape of the report**, decided by the catalog.

    A caller naming one has either added it or dropped it, and both are `008`'s to decide.
    """
    names = _kpi_names()
    assert names, "no KPI names were read; this node would forbid nothing"

    offending = sorted({text for text in _strings() if text in names})
    assert not offending, f"the caller names KPIs: {offending}"


def test_the_caller_carries_none_of_his_authored_words() -> None:
    """**The caller spends none of the budget, whatever the budget currently is.**

    The number is read off the module and asserted here so that a budget which moves silently
    fails: it stood at eight until 2026-09-06 and at twelve after `OD-147`, `OD-150` and
    `OD-151` rebuilt both line shapes. What this node guards is unchanged — the caller holds
    none of those strings, because the words a reader sees belong to `008` and not to whatever
    happens to call it.
    """
    authored = set(template.AUTHORED_WORDS)
    assert len(authored) == 12, f"the authored budget moved to {len(authored)} without this node"

    offending = sorted({text for text in _strings() if text.strip() and text in authored})
    assert not offending, f"the caller repeats his authored words: {offending}"


def test_the_caller_formats_nothing_a_reader_will_see() -> None:
    """No number formatting, no markup, no separator: the line's shape is `008`'s."""
    offending = sorted({text for text in _strings() for token in FORMATTING if token in text})
    assert not offending, f"the caller formats message content: {offending}"

    #: And no unit, matched as a whole word so that ordinary prose does not trip it.
    wearing = sorted({text for text in _strings() if UNITS & set(text.split())})
    assert not wearing, f"the caller dresses a number in a unit: {wearing}"


def test_the_caller_never_imports_what_composes_the_message() -> None:
    """The strongest half, because it does not depend on guessing which strings matter.

    A caller that cannot reach the renderer cannot re-render, whatever it writes.
    """
    reached: list[str] = []
    for node in ast.walk(_tree()):
        if isinstance(node, ast.ImportFrom) and node.module:
            reached.append(node.module)
        elif isinstance(node, ast.Import):
            reached.extend(alias.name for alias in node.names)

    offending = sorted(
        {
            module
            for module in reached
            for forbidden in THE_MESSAGE
            if module == forbidden or module.startswith(f"{forbidden}.")
        }
    )
    assert not offending, f"the caller imports what composes the message: {offending}"

    called = {
        node.func.id
        for node in ast.walk(_tree())
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not called & {"render", "summarise", "active_kpis", "shape_rows"}, (
        f"the caller composes: {sorted(called & {'render', 'summarise', 'active_kpis'})}"
    )
