"""Static reachability from the model surface — T084 (FR-092, FR-093; SC-054).

    **Reachability, not redaction** — a value is never present rather than
    removed. — `tasks.md` T084

The distinction is the whole design. Redaction is a correctness obligation on
every future change: somebody must remember to strip the value, and the day they
forget the payload leaves. Type-level impossibility plus this gate is an
obligation on nobody — there is no value in the process to strip.

Three closures are walked, and each answers a different question:

* **module closure** — what can `model_port.py` import, transitively? Nothing
  under `execution/`, `comparison/`, `answer/`, `audit/`, or `002`'s result,
  execution and adapter modules.
* **type closure** — what types can the port's parameters and return reach, by
  following every field annotation to its leaves? No `002` result type, no `003`
  answer or comparison value type, no execution type.
* **call closure** — what does anything in the module closure invoke? Nothing
  that produces or reads a result.

`FR-093` is checked as sequence position: the port sits at step 8, before any
execution, so no result exists in the process while it is reachable. Asserted by
the module closure containing no execution path at all — if it did, "before
execution" would be a convention rather than a fact.
"""

from __future__ import annotations

import ast
import inspect
import typing
from pathlib import Path

import pytest

import analytics_interaction
from analytics_interaction.interpretation.model_port import (
    CandidateSelection,
    CandidateSet,
    DelimitedQuestionData,
    InterpretationModelPort,
)

pytestmark = pytest.mark.contract

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent
PACKAGE = "analytics_interaction"
PORT = SRC / "interpretation" / "model_port.py"

#: `003` subpackages that hold or produce values. None may be reachable.
FORBIDDEN_LOCAL = ("execution", "comparison", "answer", "audit")

#: Upstream modules that **execute, read or produce** — not modules that merely
#: declare a type. None may be reachable from the port's module closure.
#:
#: `analytics_query.contracts.result` and `result_provenance` are deliberately
#: **not** here, and the distinction is worth stating rather than assuming.
#: `contracts/__init__.py` is this package's single export surface, so importing
#: any contract executes it and therefore executes `contracts/answer.py`, which
#: declares `AnalyticsAnswer` and names `ResultProvenance` as a type. Banning
#: that transitively would ban the export surface itself.
#:
#: What actually matters is whether a value can *reach* the port, and that is the
#: **type closure** below — a strictly stronger claim, and it is clean. Importing
#: a frozen record definition holds no result, exactly as `contracts/comparison.py`
#: importing `CatalogDecision` holds no decision. The port's own direct imports
#: are checked separately and name none of them.
FORBIDDEN_UPSTREAM = (
    "analytics_query.execute",
    "analytics_query.execution",
    "analytics_query.results",
    "analytics_query.adapters",
    "analytics_query.observations",
    "analytics_query.pipeline",
    "semantic_catalog.provenance",
    "semantic_catalog.freshness",
)

#: Type-declaring modules the **port itself** must not import directly. Reaching
#: them through the package export surface is unavoidable; naming one in
#: `model_port.py` would be a deliberate act.
FORBIDDEN_DIRECT_IMPORTS = (
    "analytics_query.contracts.result",
    "analytics_query.contracts.result_provenance",
    "analytics_query.contracts.provenance",
    "analytics_query.contracts.policy",
    "analytics_query.contracts.request",
    "analytics_query.contracts.comparable_window",
    "semantic_catalog.validation.decision",
)

#: Calls that produce or read a result.
FORBIDDEN_CALLS = (
    "execute_analytics_query",
    "execute_bounded",
    "run_until_evaluation",
    "assemble_result",
    "perform_dry_run",
    "finalise_decision",
    "submit",
)

#: Type names that carry a value. Leaves of the type closure are checked
#: against these by name, so an alias or a re-export cannot slip past.
FORBIDDEN_TYPES = (
    "AnalyticsResult",
    "ResultColumn",
    "ResultProvenance",
    "CostProvenance",
    "SourceUpdate",
    "ExecutedAnswer",
    "AnalyticsQuery",
    "GovernedFilter",
    "QueryPolicy",
    "ComparableWindow",
    "CatalogDecision",
    "DerivedFigure",
    "SideResult",
    "GovernedComparison",
    "AnalyticsAnswer",
    "AnswerClaim",
    "CaveatSet",
    "AttributedCaveat",
    "InsufficiencyNotice",
    "InterpretationPolicy",
    "Decimal",
)


def _imports(path: Path) -> set[str]:
    """Absolute module names, relatives resolved against the package."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = path.parent.relative_to(SRC).as_posix().replace("/", ".")
    base = f"{PACKAGE}.{package}" if package != "." else PACKAGE

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                found.add(node.module or "")
            else:
                parts = base.split(".")
                anchor = ".".join(parts[: len(parts) - node.level + 1])
                found.add(f"{anchor}.{node.module}" if node.module else anchor)
    return {module for module in found if module}


def _module_path(module: str) -> Path | None:
    relative = module.removeprefix(PACKAGE + ".").replace(".", "/")
    for candidate in (SRC / f"{relative}.py", SRC / relative / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _module_closure() -> dict[str, Path]:
    """Every module transitively reachable from the port."""
    pending = [PORT]
    seen: dict[str, Path] = {}
    while pending:
        path = pending.pop()
        key = path.relative_to(SRC).as_posix()
        if key in seen:
            continue
        seen[key] = path
        for module in _imports(path):
            if module.split(".")[0] != PACKAGE:
                continue
            local = _module_path(module)
            if local is not None:
                pending.append(local)
    return seen


CLOSURE = _module_closure()


def _type_closure() -> set[str]:
    """Every type name reachable by following field annotations to their leaves."""
    seen: set[str] = set()
    pending: list[object] = [DelimitedQuestionData, CandidateSet, CandidateSelection]

    while pending:
        current = pending.pop()
        name = getattr(current, "__name__", str(current))
        if name in seen:
            continue
        seen.add(name)

        fields = getattr(current, "model_fields", None)
        if fields is None:
            continue
        for field in fields.values():
            pending.extend(_leaves(field.annotation))
    return seen


def _leaves(annotation: object) -> list[object]:
    """Unwrap containers and unions down to the types they contain."""
    args = typing.get_args(annotation)
    if not args:
        return [annotation]
    leaves: list[object] = []
    for arg in args:
        if arg is type(None) or arg is Ellipsis:
            continue
        leaves.extend(_leaves(arg))
    return leaves


TYPES = _type_closure()


# --- the closures are real -----------------------------------------------------


def test_the_module_closure_is_non_empty_and_contains_the_port() -> None:
    """A reachability guard over nothing passes for the wrong reason."""
    assert "interpretation/model_port.py" in CLOSURE
    assert len(CLOSURE) > 3, f"the closure is suspiciously small: {sorted(CLOSURE)}"


def test_the_type_closure_reaches_the_nested_governed_types() -> None:
    """The walk must be transitive, or the leaf checks prove nothing."""
    assert {"CandidateSet", "CandidateOption", "LocalizedRef", "SlotKind"} <= TYPES


# --- module reachability -------------------------------------------------------


@pytest.mark.parametrize("subpackage", FORBIDDEN_LOCAL)
def test_the_port_reaches_no_value_bearing_subpackage(subpackage: str) -> None:
    offenders = sorted(name for name in CLOSURE if name.startswith(f"{subpackage}/"))
    assert not offenders, f"{subpackage}/ is reachable from the model port: {offenders}"


@pytest.mark.parametrize("module", FORBIDDEN_UPSTREAM)
def test_the_port_reaches_no_upstream_result_or_execution_module(module: str) -> None:
    offenders = [
        f"{name} imports {imported}"
        for name, path in sorted(CLOSURE.items())
        for imported in _imports(path)
        if imported == module or imported.startswith(module + ".")
    ]
    assert not offenders, f"an execution or result module is reachable: {offenders}"


@pytest.mark.parametrize("module", FORBIDDEN_DIRECT_IMPORTS)
def test_the_port_module_itself_imports_no_value_declaring_module(module: str) -> None:
    """Transitive reach through the export surface is unavoidable; naming one here is not.

    `model_port.py` imports the gate, the readiness types, the shared base, the
    slot enum and the reason codes. Nothing that declares a result, a request, a
    policy or a decision.
    """
    direct = _imports(PORT)
    offenders = [
        imported for imported in direct if imported == module or imported.startswith(module + ".")
    ]
    assert not offenders, f"the port imports {module} directly: {offenders}"


def test_the_ports_direct_imports_are_exactly_what_it_needs() -> None:
    """Enumerated, so a new dependency has to be argued for rather than added."""
    assert _imports(PORT) == {
        "__future__",
        "typing",
        "pydantic",
        "analytics_interaction.compliance.gates",
        "analytics_interaction.compliance.readiness",
        "analytics_interaction.contracts._base",
        "analytics_interaction.contracts.intent",
        "analytics_interaction.contracts.reason_codes",
    }


@pytest.mark.parametrize("function", FORBIDDEN_CALLS)
def test_nothing_reachable_from_the_port_invokes_execution(function: str) -> None:
    """`FR-093`: the surface sits entirely before execution in the sequence."""
    offenders: list[str] = []
    for name, path in sorted(CLOSURE.items()):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else node.func.id
                if isinstance(node.func, ast.Name)
                else ""
            )
            if called == function:
                offenders.append(f"{name}:{node.lineno} calls {function}()")
    assert not offenders, f"execution is reachable from the model port: {offenders}"


# --- type reachability ---------------------------------------------------------


@pytest.mark.parametrize("forbidden", FORBIDDEN_TYPES)
def test_no_model_facing_type_reaches_a_value_type(forbidden: str) -> None:
    """Followed to the leaves, so a value nested three levels down is caught."""
    assert forbidden not in TYPES, f"{forbidden} is reachable from the model surface"


def test_the_reachable_types_are_the_ones_the_contract_names() -> None:
    """Enumerated exactly.

    A pattern check would pass for a type named innocuously; this fails the
    moment anything new becomes reachable, whatever it is called.
    """
    assert {
        "DelimitedQuestionData",
        "CandidateSet",
        "CandidateSelection",
        "CandidateOption",
        "LocalizedRef",
        "SlotKind",
        "str",
        "int",
    } == TYPES


def test_the_guard_would_catch_an_added_result_field() -> None:
    """The mutation test. A closure that never fails proves nothing.

    A model built like the real ones, with a result type on a field, must be
    visible to the same walk.
    """
    from analytics_query.contracts.result_provenance import ResultProvenance
    from pydantic import BaseModel

    class Planted(BaseModel):
        identifier: str
        provenance: ResultProvenance

    leaves = {
        getattr(leaf, "__name__", str(leaf))
        for field in Planted.model_fields.values()
        for leaf in _leaves(field.annotation)
    }
    assert "ResultProvenance" in leaves
    assert leaves & set(FORBIDDEN_TYPES)


def test_the_guard_would_catch_a_planted_execution_import() -> None:
    planted = ast.parse("from analytics_query.execute import execute_analytics_query\n")
    modules = {
        node.module
        for node in ast.walk(planted)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert any(
        module == banned or module.startswith(banned + ".")
        for module in modules
        for banned in FORBIDDEN_UPSTREAM
    )


# --- the return type cannot name an unknown identifier -------------------------


def test_the_return_type_carries_an_identifier_and_no_provenance_for_it() -> None:
    """`FR-041` enforced by the signature.

    A selection is an identifier and nothing else; validation confirms it came
    from the request. There is no field through which a model could attach a
    justification that later code might trust.
    """
    hints = typing.get_type_hints(InterpretationModelPort.narrow)
    assert CandidateSelection in typing.get_args(hints["return"])
    assert tuple(CandidateSelection.model_fields) == ("identifier",)
    assert CandidateSelection.model_fields["identifier"].annotation is str
