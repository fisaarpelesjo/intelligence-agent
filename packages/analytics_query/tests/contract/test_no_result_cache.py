"""No result cache — T086 (FR-068; SC-013).

A cache hit is not a reachable state, and this is asserted **structurally**
rather than behaviourally. A test that merely observed "the second request
executed again" would still pass if someone later added a cache that happened to
miss under test conditions.

The property matters more than it sounds. A result cache would be a durable
store of metric values, which needs its own access control, retention policy and
audit trail — precisely the machinery `FR-066` exists to avoid needing. It would
also make `FR-067`'s stability guarantee unverifiable: identical values would no
longer prove the revisions were unchanged, only that something was remembered.

Repeat cost is the accepted trade (`A-13`). A re-request pays for a fresh
execution, and identical values come from the as-of pin and unchanged revisions
rather than from stored output.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import analytics_query

pytestmark = pytest.mark.contract

SRC = Path(analytics_query.__file__).parent
_MODULES = sorted(SRC.rglob("*.py"))

#: Names that would betray a store of computed **results**.
#:
#: Deliberately not the bare word "cache". Two legitimate uses would trip that:
#: `use_query_cache=False` *disables* the warehouse cache, which is the opposite
#: of the defect; and the pt-BR message registry caches governed content, which
#: is not a result and whose stability `FR-058` actively wants.
_RESULT_CACHE_SHAPED = (
    "stored_result",
    "previous_result",
    "last_result",
    "result_store",
    "result_cache",
    "cached_result",
    "row_cache",
    "value_cache",
    "answer_cache",
)

#: Packages where no caching decorator may appear at all — these compute, bind
#: and return figures, so anything remembered here is a remembered result.
_RESULT_BEARING = ("results", "execution", "decision", "compile")


def test_the_scan_sees_the_package() -> None:
    assert len(_MODULES) >= 25


@pytest.mark.parametrize("path", _MODULES, ids=lambda p: str(p.relative_to(SRC)))
def test_no_module_declares_a_cache(path: Path) -> None:
    """Scans executable code, not prose — several modules explain the absence."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            node.value = ast.Constant("")
    code = ast.unparse(tree).lower()
    for marker in _RESULT_CACHE_SHAPED:
        assert marker not in code, f"{path.relative_to(SRC)} declares {marker!r}"


def test_no_result_bearing_module_uses_a_caching_decorator() -> None:
    """Governed content may be cached; figures may not.

    The message registry caches its parsed YAML, and that is fine — it is
    governed content, not an answer. Anything under `results/`, `execution/`,
    `decision/` or `compile/` computes or carries figures, so a cache there
    would be a remembered result.
    """
    offenders: list[str] = []
    for path in _MODULES:
        if path.relative_to(SRC).parts[0] not in _RESULT_BEARING:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "functools":
                names = {alias.name for alias in node.names}
                if names & {"lru_cache", "cache", "cached_property"}:
                    offenders.append(f"{path.relative_to(SRC)}: {sorted(names)}")
    assert not offenders, offenders


def test_the_warehouse_cache_is_explicitly_disabled() -> None:
    """The adapter must not be served a remembered answer either.

    BigQuery caches query results by default. Leaving that on would reintroduce
    exactly the state `FR-068` forbids, one layer below this feature.
    """
    client = (SRC / "adapters" / "bigquery" / "client.py").read_text(encoding="utf-8")
    assert client.count("use_query_cache=False") == 2, "both dry run and execute must disable it"
    assert "use_query_cache=True" not in client


def test_the_ledger_declares_no_field_that_could_hold_a_result() -> None:
    """The one durable store this feature owns holds metadata only."""
    from analytics_query.execution.ledger_entry import ExecutionAttachment, ExecutionLedgerEntry

    for model in (ExecutionLedgerEntry, ExecutionAttachment):
        declared = {name.lower() for name in model.model_fields}
        for forbidden in ("result", "rows", "values", "payload", "cells", "cached"):
            assert forbidden not in declared, f"{model.__name__} could store a result"


def test_a_terminal_entry_yields_a_fresh_execution_rather_than_a_replay() -> None:
    """The behavioural half: a re-request acquires, it does not read back."""
    from analytics_query.execution.ledger import (
        AuthorizationContext,
        ExecutionKey,
        derive_authorization_fingerprint,
    )
    from analytics_query.execution.ledger_entry import ExecutionStatus
    from analytics_query.execution.ledger_memory import InMemoryExecutionLedger
    from analytics_query.execution.singleflight import Disposition, drive_single_flight

    context = AuthorizationContext(
        authorization_scope="tenant-a",
        granted_access_tags=frozenset({"installs:read"}),
        principal_type="user",
        authorization_policy_pin="authpol-1",
    )
    key = ExecutionKey("a" * 64, derive_authorization_fingerprint(context))
    ledger = InMemoryExecutionLedger()

    first = drive_single_flight(ledger, key, correlation_id="c1", principal_ref="p1")
    assert first.disposition is Disposition.NEW
    ledger.complete(key, ExecutionStatus.COMPLETED, actual_bytes=10, row_count=3)

    again = drive_single_flight(ledger, key, correlation_id="c2", principal_ref="p1")
    assert again.disposition is Disposition.RE_REQUEST
    assert again.owns_execution, "a re-request drives its own execution, it does not replay"
    # The fresh entry carries no figures from the completed one.
    assert again.entry.actual_bytes is None
    assert again.entry.row_count is None


def test_no_module_returns_a_stored_payload_in_place_of_executing() -> None:
    """No function name promises a remembered answer."""
    offenders: list[str] = []
    for path in _MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                name = node.name.lower()
                if any(m in name for m in ("get_cached", "load_result", "fetch_stored", "replay")):
                    offenders.append(f"{path.relative_to(SRC)}: {node.name}")
    assert not offenders, offenders
