"""Schema drift — T112.

`schema export --check` compares the generated governed-content schema against
what the contracts actually declare. Hand-editing a generated schema fails CI.

The point is direction of authority. Governed content and the code that reads it
must agree, and when they disagree the answer is never "regenerate quietly" --
someone changed one of them on purpose and the other needs to catch up. A gate
that auto-fixed the drift would erase the evidence that they had diverged.
"""

from __future__ import annotations

import json

import pytest

from analytics_query.cli.main import EXIT_OK, EXIT_VIOLATION, main
from analytics_query.contracts.matrix import OPERATOR_MATRIX
from analytics_query.contracts.operators import (
    DimensionType,
    GovernedOperator,
    load_dimension_types,
    load_operators,
)
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.messages.registry import load_registry

pytestmark = pytest.mark.contract


def test_the_check_passes_today() -> None:
    """Otherwise every drift assertion below would pass vacuously."""
    assert main(["schema", "export", "--check"]) == EXIT_OK


def test_the_export_emits_the_generated_schema(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["schema", "export"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {
        "operators",
        "dimension_types",
        "dimension_assignments",
        "reason_codes",
    }


def test_the_exported_operators_match_the_enum() -> None:
    assert sorted(load_operators()) == sorted(o.value for o in GovernedOperator)


def test_the_exported_dimension_types_match_the_enum() -> None:
    types, _ = load_dimension_types()
    assert sorted(types) == sorted(t.value for t in DimensionType)


def test_every_governed_dimension_has_a_declared_type() -> None:
    _, assignments = load_dimension_types()
    types, _ = load_dimension_types()
    assert assignments, "the vocabulary must actually assign something"
    for dimension, type_id in assignments.items():
        assert type_id in types, f"{dimension} claims an undeclared type"


def test_the_matrix_stays_exhaustive() -> None:
    """Five operators times three types. A new member without an entry drifts."""
    assert len(OPERATOR_MATRIX) == len(GovernedOperator) * len(DimensionType)


def test_the_message_registry_covers_the_enum_exactly() -> None:
    assert load_registry().codes == frozenset(AnalyticsReasonCode)


def test_a_drifted_registry_is_reported_as_a_violation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulated drift must fail the gate, not be regenerated away."""
    from analytics_query.messages import registry as registry_module

    class _Short:
        codes: frozenset[AnalyticsReasonCode] = frozenset({next(iter(AnalyticsReasonCode))})

    monkeypatch.setattr(registry_module, "load_registry", lambda: _Short())
    monkeypatch.setattr("analytics_query.cli.main.load_registry", lambda: _Short())
    assert main(["schema", "export", "--check"]) == EXIT_VIOLATION


def test_the_check_reports_what_drifted(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Short:
        codes: frozenset[AnalyticsReasonCode] = frozenset()

    monkeypatch.setattr("analytics_query.cli.main.load_registry", lambda: _Short())
    main(["schema", "export", "--check"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["drifted"] == ["messages"]


def test_the_gate_never_rewrites_governed_content() -> None:
    """`--check` reports; it does not fix."""
    import ast
    import inspect

    from analytics_query.cli import main as cli

    # The whole module, not one handler: a rewrite added to a helper the gate
    # calls would be just as damaging and harder to notice.
    tree = ast.parse(inspect.getsource(cli))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "attr", "") or getattr(node.func, "id", "")
            assert name not in {"write_text", "write_bytes", "mkdir", "unlink"}, name
