"""The exported port boundary — T097 reconciliation (FR-028; SC-003, SC-004).

An earlier draft of `execution/port.py` held `002`'s fifteen collaborators as
**public** dataclass fields, seven of them annotated ``Any``. Both halves of that
were defects, and this file is the guard against either returning.

**A public ``Any`` is a hole, not a description of one.** It accepts a result
set, a warehouse response, rendered SQL, a query plan, a credential or an audit
payload, and lets each be passed onward as though the type system had approved
it. The static claim asserted here is exact: **no ``Any`` appears anywhere on the
exported surface** — not on the Protocol, not on ``submit``, not on the
environment's constructor, not on any exported class's annotations. The one
``Any`` this module needs is private, is applied at the single call site, and is
asserted to stay there.

**Republishing `002`'s collaborator list is the second defect.** A consumer
coding against fifteen public fields would be coupled to `002`'s composition —
precisely the coupling ADR 0010's single entry point exists to prevent — and a
collaborator added upstream would become a breaking change in `003`. So the
binding is opaque: constructed once, readable never, and asserted here to expose
no public attribute at all.

**Type reachability.** ``ExecutedAnswer`` is the approved return contract and it
does reach analytical values — that is what it is for. What must hold is that it
is the *only* such path: every other annotation on the exported boundary has a
type closure containing no result, no row, no cell and no provenance. So the
reachability test walks the closure of each annotation and asserts the result
types appear under ``ExecutedAnswer`` and nowhere else.
"""

from __future__ import annotations

import ast
import inspect
import typing
from pathlib import Path
from typing import Any, cast, get_type_hints

import pytest
from analytics_query.contracts.request import AnalyticsQuery
from analytics_query.contracts.result import AnalyticsResult, ResultCell, ResultRow
from analytics_query.contracts.result_provenance import ResultProvenance
from analytics_query.execute import ExecutedAnswer
from analytics_query.results.completeness import ResultDisposition
from semantic_catalog.validation.decision import CatalogDecision

from analytics_interaction.authorization.context_preflight import AuthorizedContext
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.execution import port as port_module
from analytics_interaction.execution.port import (
    ExecutionEnvironment,
    ExecutionPort,
    GovernedExecutionPort,
)

from ..conftest import ON
from ..fixtures.submissions import bound_environment

pytestmark = pytest.mark.contract

PORT_SOURCE = Path(inspect.getfile(port_module))

#: What `003` publishes from this module. Read from ``__all__`` rather than
#: listed here, so a value exported later is covered without an edit.
EXPORTED = tuple(port_module.__all__)

#: Everything a submission may carry. Four values: the question, who is asking,
#: the binding that proves they asked, and what to correlate the execution with.
SUBMIT_PARAMETERS = ("request", "authorized", "auth_fingerprint", "correlation_id")

#: Analytical payload. None of it may be reachable from the boundary except
#: through the approved return contract.
RESULT_TYPES = (AnalyticsResult, ResultRow, ResultCell, ResultProvenance)


#: Names `002` defers behind ``TYPE_CHECKING`` in ``execute.py``. Its annotations
#: are strings that do not resolve at runtime without them, and this feature may
#: not ask `002` to change that. Supplied here so the closure walker can follow
#: ``ExecutedAnswer`` into the result types — which is the positive half of the
#: reachability claim and would silently pass if resolution failed instead.
_DEFERRED: dict[str, object] = {
    "AnalyticsResult": AnalyticsResult,
    "ResultProvenance": ResultProvenance,
    "CatalogDecision": CatalogDecision,
    "ResultDisposition": ResultDisposition,
    "AnalyticsQuery": AnalyticsQuery,
}


def _annotations(target: object) -> dict[str, object]:
    """Resolved annotations, with string forms evaluated.

    ``from __future__ import annotations`` makes every annotation a string, so a
    check that read ``__annotations__`` directly would be comparing source text
    and would miss an alias resolving to ``Any``.
    """
    return dict(get_type_hints(target, localns=_DEFERRED, include_extras=True))  # type: ignore[arg-type]


def _closure(annotation: object, seen: set[object] | None = None) -> set[object]:
    """Every type reachable from ``annotation``, transitively.

    Walks type arguments and, for pydantic models and dataclasses, their field
    annotations. Depth matters: ``AnalyticsResult`` is two hops from
    ``ExecutedAnswer`` and zero hops from nothing else on this boundary, and a
    one-level check would call both of those clean.
    """
    seen = seen if seen is not None else set()
    if annotation is None:
        return seen
    try:
        if annotation in seen:
            return seen
        seen.add(annotation)
    except TypeError:
        # ``Callable[[], object]`` carries its parameter list as a bare list,
        # which is unhashable. Descend into it rather than skipping: a result
        # type could sit inside a callable's arguments.
        parameters = cast("list[object]", annotation) if isinstance(annotation, list) else []
        for argument in parameters:
            _closure(argument, seen)
        return seen

    for argument in typing.get_args(annotation):
        _closure(argument, seen)

    fields = getattr(annotation, "model_fields", None)
    if fields is not None:
        for info in fields.values():  # pyright: ignore[reportUnknownVariableType]
            _closure(getattr(info, "annotation", None), seen)
        return seen

    if inspect.isclass(annotation) and hasattr(annotation, "__dataclass_fields__"):
        for declared in _annotations(annotation).values():
            _closure(declared, seen)
    return seen


# --- the exported surface carries no Any ----------------------------------------


def test_the_port_protocol_method_has_no_any() -> None:
    """The one method that reaches the warehouse names everything that crosses it."""
    hints = _annotations(ExecutionPort.submit)
    assert hints, "the protocol method carries no annotations at all"
    assert Any not in hints.values()
    assert object not in hints.values()


def test_the_concrete_submit_matches_the_protocol_exactly() -> None:
    """A widened implementation would satisfy the Protocol and defeat it.

    ``Any`` on the concrete method would still typecheck against a precise
    Protocol, and every caller holding the concrete type would get the hole.
    """
    assert _annotations(GovernedExecutionPort.submit) == _annotations(ExecutionPort.submit)


def test_submit_exposes_only_the_minimum_governed_submission_information() -> None:
    """Four values. Not a collaborator, a limit, a policy or a stage selector."""
    parameters = inspect.signature(GovernedExecutionPort.submit).parameters
    assert tuple(name for name in parameters if name != "self") == SUBMIT_PARAMETERS
    for name in SUBMIT_PARAMETERS[1:]:
        assert parameters[name].kind is inspect.Parameter.KEYWORD_ONLY


def test_submit_names_concrete_public_types() -> None:
    hints = _annotations(GovernedExecutionPort.submit)
    assert hints["request"] is AnalyticsQuery
    assert hints["authorized"] is AuthorizedContext
    assert hints["auth_fingerprint"] is str
    assert hints["correlation_id"] is str
    assert hints["return"] is ExecutedAnswer


@pytest.mark.parametrize("name", EXPORTED)
def test_no_exported_value_annotates_anything_as_any(name: str) -> None:
    """Every exported class, its methods and its constructor."""
    exported = getattr(port_module, name)
    targets: list[object] = [exported]
    targets += [
        member
        for member_name, member in inspect.getmembers(exported, inspect.isfunction)
        if not member_name.startswith("__") or member_name == "__init__"
    ]
    for target in targets:
        try:
            hints = _annotations(target)
        except (TypeError, NameError):  # pragma: no cover - non-annotatable member
            continue
        offenders = [key for key, value in hints.items() if value is Any]
        assert not offenders, f"{name}.{getattr(target, '__name__', '')} annotates {offenders} Any"


def test_the_environment_constructor_uses_object_not_any_for_hidden_collaborators() -> None:
    """``object`` accepts a value and permits nothing to be done with it.

    That is the whole difference. ``Any`` would let a result set be passed in and
    then called, indexed or attribute-accessed downstream as though checked;
    ``object`` cannot become a path to anything.
    """
    hints = _annotations(ExecutionEnvironment.__init__)
    hidden = ("evaluate", "ledger", "observations", "adapter", "sink", "context")
    for name in hidden:
        assert hints[name] is object, f"{name} is {hints[name]}, not object"
    assert Any not in hints.values()


# --- the one private Any ---------------------------------------------------------


def test_any_appears_exactly_once_in_the_module_and_inside_a_private_helper() -> None:
    """Contained, and asserted to stay contained.

    A second ``Any`` — even a well-intentioned one — is how the hole comes back,
    so the count is asserted rather than the placement alone.
    """
    tree = ast.parse(PORT_SOURCE.read_text(encoding="utf-8"), filename=str(PORT_SOURCE))
    holders = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and any(inner.id == "Any" for inner in ast.walk(node) if isinstance(inner, ast.Name))
    ]
    assert [node.name for node in holders] == ["_opaque"]
    assert holders[0].name.startswith("_"), "the widening helper is not private"


def test_the_private_helper_is_not_exported() -> None:
    assert "_opaque" not in EXPORTED
    assert not any(name.startswith("_") for name in EXPORTED)


# --- the environment is opaque ---------------------------------------------------


def test_a_bound_environment_exposes_no_public_attribute() -> None:
    """No accessor, no ``asdict``, no iteration. It is a token, not a record."""
    environment = bound_environment(on=ON)
    public = [name for name in dir(environment) if not name.startswith("_")]
    assert public == []


def test_a_bound_environment_cannot_be_extended_after_validation() -> None:
    """``__slots__``: bound and validated are the same moment."""
    environment = bound_environment(on=ON)
    with pytest.raises(AttributeError):
        environment.adapter = object()  # type: ignore[attr-defined]


def test_the_environment_repr_discloses_nothing() -> None:
    """The default would print the ledger and the adapter into every traceback."""
    environment = bound_environment(on=ON)
    assert repr(environment) == "ExecutionEnvironment(<bound>)"


def test_the_exported_surface_is_three_names() -> None:
    """`002`'s fifteen collaborators are not `003`'s API."""
    assert set(EXPORTED) == {"ExecutionEnvironment", "ExecutionPort", "GovernedExecutionPort"}


# --- type reachability ------------------------------------------------------------


def test_only_the_approved_return_contract_reaches_analytical_values() -> None:
    """`SC-004`: the boundary has one path to a result, and it is the answer."""
    hints = _annotations(GovernedExecutionPort.submit)
    for name, annotation in hints.items():
        if name == "return":
            continue
        reachable = _closure(annotation)
        offenders = [t for t in RESULT_TYPES if t in reachable]
        assert not offenders, f"submit parameter {name} reaches {offenders}"


def test_the_approved_return_contract_does_reach_them() -> None:
    """Otherwise the test above passes because the closure walker sees nothing.

    A reachability assertion whose walker is broken is indistinguishable from a
    clean boundary, so the positive case is asserted alongside the negative one.
    """
    reachable = _closure(ExecutedAnswer)
    assert AnalyticsResult in reachable
    assert ResultProvenance in reachable


def test_the_environment_constructor_reaches_no_analytical_value() -> None:
    """Wiring cannot smuggle a result in disguised as a collaborator."""
    hints = _annotations(ExecutionEnvironment.__init__)
    for name, annotation in hints.items():
        reachable = _closure(annotation)
        offenders = [t for t in RESULT_TYPES if t in reachable]
        assert not offenders, f"environment parameter {name} reaches {offenders}"


# --- the single call site ---------------------------------------------------------


def test_the_entry_point_is_called_exactly_once_in_the_module() -> None:
    """One call site. `T093`'s ownership guard proves it is the only module."""
    tree = ast.parse(PORT_SOURCE.read_text(encoding="utf-8"), filename=str(PORT_SOURCE))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "execute_analytics_query"
    ]
    assert len(calls) == 1


def test_no_collaborator_is_constructed_inside_the_port() -> None:
    """A hidden collaborator built here would be an environment `003` chose.

    The port composes nothing and defaults nothing: every collaborator arrives
    through the binding or the submission refuses at wiring time.
    """
    tree = ast.parse(PORT_SOURCE.read_text(encoding="utf-8"), filename=str(PORT_SOURCE))
    constructed = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    forbidden = {"BigQueryAdapter", "ExecutionLedger", "AuditSink", "ObservationReader", "open"}
    assert not constructed & forbidden


def test_an_incompletely_bound_environment_refuses_at_wiring_time() -> None:
    """Not at the warehouse, where it would read as a governance failure."""
    with pytest.raises(ContractViolation) as refusal:
        ExecutionEnvironment(
            evaluate=None,
            ledger=None,
            observations=None,
            adapter=None,
            sink=None,
            context=None,
            sample_catalog=lambda: None,
            catalog_bundle=None,  # type: ignore[arg-type]
            on=ON,
            catalog_release_id="r-1",
            required_sources=frozenset({"appstore"}),
            columns=(),
            metric_version_ids=("mv-1",),
            freshness_snapshot=None,  # type: ignore[arg-type]
            metric_version=None,  # type: ignore[arg-type]
        )
    assert "incompletely bound" in refusal.value.detail
