"""There is exactly one way to execute — 003:T007.

ADR 0010 authorizes a composition, not an alternative. If the entry point
re-implemented steps 1-7 instead of delegating them, or if a second callable
appeared that reached the adapter by another route, the ordering guarantees
`002` proves would hold on one path and be unproven on the other — and the one
that skipped a gate would be the one nobody tested.

So this is asserted structurally: the entry point *calls* the pipeline, the
public surface is exactly what ADR 0010 declared, and nothing else in `002`
composes execution.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from analytics_query import execute as entry_point

pytestmark = pytest.mark.contract

SRC = Path(entry_point.__file__).resolve().parent
MODULE = Path(entry_point.__file__).resolve()

#: ADR 0010 §"What `003` may depend on". Widening this is a governed change.
DECLARED_SURFACE = {"ExecutedAnswer", "ExecutionRefused", "execute_analytics_query"}


def _calls(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def test_the_public_surface_is_exactly_what_the_adr_declared() -> None:
    assert set(entry_point.__all__) == DECLARED_SURFACE


def test_the_entry_point_delegates_to_the_pipeline_rather_than_reimplementing_it() -> None:
    """The composition must *call* `run_until_evaluation`, not inline it."""
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    assert "run_until_evaluation" in _calls(tree)


def test_the_entry_point_reimplements_no_step_the_pipeline_owns() -> None:
    """Steps 2-7 belong to the pipeline. Calling their internals here would be a
    second ordering wearing the first one's name."""
    source = MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    called = _calls(tree)
    for owned in (
        "run_preflight",
        "resolve_policy",
        "assert_range_within_limit",
        "derive_identity",
        "execution_key_for",
        "read_bundle_or_refuse",
    ):
        assert owned not in called, (
            f"{owned} belongs to steps 2-7 and must be reached through the pipeline"
        )
    assert "acquire" not in called, "the ledger is acquired by the pipeline, not the composition"


def test_no_other_module_composes_execution() -> None:
    """Only one module may reach both the adapter and result assembly.

    That pairing is what makes a module an execution path. `explain-plan`
    deliberately stops before it, and no other module may pick it up.
    """
    composers: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        reaches_adapter = "execute_bounded(" in text or "perform_dry_run(" in text
        reaches_results = "assemble_result(" in text
        if reaches_adapter and reaches_results:
            composers.append(path.name)
    assert composers == ["execute.py"], f"more than one execution path exists: {composers}"


def test_the_ordering_is_fixed_in_source_order() -> None:
    """Compile, dry run, execute, shape, mid-flight, assemble — in that order.

    Read positionally from the module rather than asserted by comment: a
    reordered composition moves these markers and fails here.
    """
    source = MODULE.read_text(encoding="utf-8")
    sequence = [
        "resolve_structure(",
        "assert_emitted_text_is_safe(",
        "perform_dry_run(",
        "assert_within_byte_ceiling(",
        "execute_bounded(",
        "assert_shapes_agree(",
        "assert_catalog_unchanged(",
        "assemble_result(",
        "finalise_decision(",
    ]
    positions = [source.index(marker) for marker in sequence]
    assert positions == sorted(positions), (
        "the composed order diverges from the approved sequence: "
        f"{[m for _, m in sorted(zip(positions, sequence, strict=True))]}"
    )


def test_the_entry_point_signature_takes_every_collaborator_by_injection() -> None:
    """Nothing is constructed internally, so nothing can be swapped at runtime."""
    signature = inspect.signature(entry_point.execute_analytics_query)
    for injected in ("evaluate", "ledger", "observations", "adapter", "sink"):
        assert injected in signature.parameters
        assert signature.parameters[injected].default is inspect.Parameter.empty, (
            f"{injected} must be supplied by the caller, never defaulted"
        )
