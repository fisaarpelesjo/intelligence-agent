"""No gate duplication — T070 (FR-015, FR-016; SC-008).

`002` obtains its governance verdict from `001`'s pipeline and re-implements
none of the eleven gates. Asserted two ways, because either alone is weak.

**Statically**, over `src/`: no module may contain existence, lifecycle,
authorisation, combination, grain, comparability, coverage, freshness, period,
retention or as-of logic. A second implementation would be a second source of
truth for who may see what, and two sources of truth drift — usually in the
permissive direction, because that is the direction nobody files a bug about.

**Dynamically**: ``evaluate()`` is the only gate entry point, and the preflight
is exactly one call carrying no snapshot. Not two, and never zero.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import analytics_query

pytestmark = pytest.mark.contract

SRC = Path(analytics_query.__file__).parent
_MODULES = sorted(SRC.rglob("*.py"))

#: Function-name fragments that would mean a gate was reimplemented here.
_GATE_LOGIC = (
    "check_exists",
    "metric_exists",
    "is_governed",
    "check_lifecycle",
    "is_published",
    "authorize",
    "check_access",
    "has_access_tag",
    "check_combination",
    "is_allowed_dimension",
    "check_grain",
    "check_comparability",
    "are_comparable",
    "check_coverage",
    "check_freshness",
    "is_stale",
    "within_tolerance",
    "check_period",
    "is_partial_period",
    "check_retention",
    "resolve_as_of",
    "resolve_version",
)


def test_the_scan_sees_the_package() -> None:
    assert len(_MODULES) >= 20


@pytest.mark.parametrize("path", _MODULES, ids=lambda p: str(p.relative_to(SRC)))
def test_no_module_defines_gate_logic(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        for fragment in _GATE_LOGIC
        if fragment in node.name.lower()
    ]
    assert not offenders, f"{path.relative_to(SRC)} reimplements a gate: {offenders}"


@pytest.mark.parametrize("path", _MODULES, ids=lambda p: str(p.relative_to(SRC)))
def test_no_module_imports_a_gate_directly(path: Path) -> None:
    """Gates run in the catalog's order because the catalog runs them.

    Importing one would let this feature call a subset, or call them in an order
    the catalog never sanctioned.
    """
    text = path.read_text(encoding="utf-8")
    for marker in ("validation.gates", "GATES["):
        assert marker not in text, f"{path.relative_to(SRC)} reaches into the gates"


def test_evaluate_is_the_only_gate_entry_point() -> None:
    """Every real call site goes through the preflight or the bridge.

    Parses call expressions rather than grepping: several modules *discuss*
    ``evaluate()`` in prose, and a docstring is not a call site.
    """
    callers: set[str] = set()
    for path in _MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "evaluate"
            ):
                callers.add(path.relative_to(SRC).as_posix())
    assert callers <= {
        "authorization/preflight.py",
        "decision/bridge.py",
    }, callers
    assert callers, "no call site found; the scan would pass vacuously"


def test_the_preflight_is_exactly_one_snapshot_free_call() -> None:
    from datetime import date

    from semantic_catalog.contracts.audit_event import PrincipalType

    from analytics_query.contracts._base import build
    from analytics_query.contracts.request import AnalyticsQuery, DateRange
    from analytics_query.execution.ledger import AuthorizationContext
    from analytics_query.execution.ledger_memory import InMemoryExecutionLedger
    from analytics_query.pipeline import PipelineRefusal, run_until_evaluation

    from ..fixtures.catalog.decisions import ALLOWED
    from ..fixtures.observations.reader import FixtureObservationReader

    calls: list[object] = []

    def evaluate(_request: object, _bundle: object, **kwargs: object) -> object:
        calls.append(kwargs.get("snapshot"))
        return ALLOWED

    with pytest.raises(PipelineRefusal):
        run_until_evaluation(
            build(
                AnalyticsQuery,
                metrics=("installs",),
                date_range=DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31)),
            ),
            evaluate=evaluate,  # type: ignore[arg-type]
            catalog_bundle=object(),  # type: ignore[arg-type]
            ledger=InMemoryExecutionLedger(),
            observations=FixtureObservationReader(),
            context=AuthorizationContext(
                authorization_scope="tenant-a",
                granted_access_tags=frozenset({"installs:read"}),
                principal_type=PrincipalType.USER.value,
                authorization_policy_pin="authpol-1",
            ),
            correlation_id="c-1",
            principal_ref="p-1",
            on=date(2026, 8, 12),
            catalog_release_id="r-1",
            required_sources=frozenset({"google_play"}),
        )

    assert calls == [None], "the preflight must be exactly one snapshot-free call"


def test_the_bridge_reads_only_the_public_outcome() -> None:
    """Deciding from anything else would be forming an opinion on the verdict."""
    import inspect

    from analytics_query.decision import bridge

    source = inspect.getsource(bridge.is_permissive)
    assert "outcome" in source
    for internal in ("_gate", "gate_verdicts", "__dict__", "_state"):
        assert internal not in source
