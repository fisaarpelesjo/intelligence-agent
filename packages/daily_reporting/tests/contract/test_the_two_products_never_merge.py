"""The report and the alert are two things — `T801`, `T803`.

**The owner separated them himself after the first question mixed them**, and the
separation is asserted here rather than remembered. His words, recorded as `OD-14-A`:
*"o relatorio diarios tem que ter todos os kpis"*.

## The failure this guards is a keyword argument

Merged now and split later never happens. What happens is one function growing a flag,
and a flag is how a summary silently becomes an alarm — after which a reader who
receives silence cannot tell *nothing moved* from *nothing was measured*.

So the check is over the **syntax tree**, not over behaviour: behaviour with the flag
unset looks exactly like behaviour with no flag.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from daily_reporting.alert import rule
from daily_reporting.report import summary

pytestmark = pytest.mark.contract

REPORT_MODULE = Path(summary.__file__)
ALERT_MODULE = Path(rule.__file__)


def _tree(module: Path) -> ast.Module:
    return ast.parse(module.read_text(encoding="utf-8"))


def _imported_roots(tree: ast.Module) -> set[str]:
    """Every module this file reaches for, however it spells the reach."""
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module)
        elif isinstance(node, ast.ImportFrom):  # a bare relative import
            roots.add("." * node.level)
    return roots


def test_the_report_does_not_reach_for_the_alert() -> None:
    """`FR-801`. A summary that can consult a threshold is one edit from using it."""
    reached = _imported_roots(_tree(REPORT_MODULE))
    offending = sorted(name for name in reached if "alert" in name or "threshold" in name)
    assert not offending, f"the report reaches for {offending}"


def test_the_alert_does_not_reach_for_the_report() -> None:
    """The reverse direction, because a cycle in either direction merges them."""
    reached = _imported_roots(_tree(ALERT_MODULE))
    offending = sorted(name for name in reached if "report" in name or "summary" in name)
    assert not offending, f"the alert reaches for {offending}"


def test_the_import_scan_would_catch_a_reach() -> None:
    """**Proof the scan bites**, over source this file parses rather than the modules.

    A node asserting *no reach* while there is no reach is green for two reasons and
    cannot tell them apart. This is the second reason, measured, in the three spellings
    a reach actually takes.
    """
    for source in (
        "from ..alert.threshold import threshold_from\n",
        "import daily_reporting.alert.rule\n",
        "from daily_reporting.alert import rule\n",
    ):
        reached = _imported_roots(ast.parse(source))
        assert any("alert" in name for name in reached), (
            f"the scan misses a reach spelled {source.strip()!r}"
        )


def test_the_report_takes_no_threshold_parameter_of_any_kind() -> None:
    """`FR-801`, `T803`. Read off the signature, so a default cannot hide it."""
    tree = _tree(REPORT_MODULE)
    entry = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "summarise"
    )
    arguments = entry.args
    named = [
        argument.arg
        for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)
    ]
    offending = sorted(
        name for name in named if "threshold" in name or "p90" in name or "percentile" in name
    )
    assert not offending, f"the report's entry point accepts {offending}"


def test_the_signature_scan_would_catch_a_flag() -> None:
    """The same predicate, fed the flag this file exists to prevent."""
    entry = next(
        node
        for node in ast.walk(ast.parse("def summarise(rows, *, threshold=None): ...\n"))
        if isinstance(node, ast.FunctionDef)
    )
    named = [argument.arg for argument in (*entry.args.args, *entry.args.kwonlyargs)]
    assert any("threshold" in name for name in named), "the signature scan misses a flag"
