"""Audit denylist — T098 (FR-051, FR-052, FR-053; SC-010).

No audit event, log or trace may contain metric values, fact rows, personal
data, credentials, channel tokens, free-text question input or replayable query
text.

**All three surfaces**, deliberately. An audit trail scrubbed of values while a
debug log carries them is not scrubbed — and logs are the surface most likely to
be shipped somewhere with weaker access control than the audit store.

The scan works two ways: the declared field set (the defect caught at the type)
and a serialised-content sweep of a fully populated event (the defect caught in
a field whose name sounds innocent).
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest
from semantic_catalog.contracts.reason_codes import Outcome

import analytics_query
from analytics_query.contracts._base import build
from analytics_query.contracts.audit import AnalyticsAuditEvent, AuditStage, PrincipalType
from analytics_query.contracts.reason_codes import AnalyticsReasonCode

pytestmark = pytest.mark.contract

SRC = Path(analytics_query.__file__).parent
_MODULES = sorted(SRC.rglob("*.py"))

#: Field names that would let forbidden content into an event.
FORBIDDEN_FIELDS = (
    "value",
    "values",
    "row",
    "rows",
    "result",
    "payload",
    "cell",
    "cells",
    "sql",
    "query_text",
    "statement",
    "question",
    "prompt",
    "free_text",
    "credential",
    "token",
    "secret",
    "api_key",
    "password",
    "email",
    "full_name",
    "display_name",
    "phone",
    "user_name",
    "filter_value",
    "filter_values",
)

#: Content a populated event must never carry.
FORBIDDEN_CONTENT = (
    "SELECT",
    "FROM `semantic.",
    "WHERE",
    "123456",
    "98765.43",
    "user@example.com",
    "Maria Silva",
    "ya29.",
    "AIza",
    "-----BEGIN",
    "quantos installs tivemos",
)


def _populated_event(**overrides: object) -> AnalyticsAuditEvent:
    payload: dict[str, object] = {
        "stage": AuditStage.EXECUTION_COMPLETE,
        "correlation_id": "c-1",
        "query_identity": "a" * 64,
        "emitted_at": datetime(2026, 8, 12, tzinfo=UTC),
        "principal_ref": "opaque-1",
        "principal_type": PrincipalType.USER,
        "authorization_scope": "tenant-a",
        "granted_access_tags": ("installs:read",),
        "metric_ids": ("installs",),
        "dimension_ids": ("country",),
        "source_ids": ("google_play",),
        "date_range_start": "2026-07-01",
        "date_range_end": "2026-07-31",
        "outcome": Outcome.ALLOW,
        "reason_code": AnalyticsReasonCode.QUERY_EXECUTED,
        "resolved_versions": ("installs@3",),
        "policy_version": "p-1",
        "catalog_release_id": "r-1",
        "dry_run_bytes": 1000,
        "actual_bytes": 999,
        "row_count": 42,
    }
    payload.update(overrides)
    return build(AnalyticsAuditEvent, **payload)


# --- the declared field set --------------------------------------------------


@pytest.mark.parametrize("forbidden", FORBIDDEN_FIELDS)
def test_no_event_field_could_hold_forbidden_content(forbidden: str) -> None:
    declared = {name.lower() for name in AnalyticsAuditEvent.model_fields}
    assert forbidden not in declared, f"AnalyticsAuditEvent declares {forbidden!r}"


def test_the_event_records_identifiers_and_counts_only() -> None:
    """Governed ids, an outcome, a code, versions and counts. No contents."""
    declared = set(AnalyticsAuditEvent.model_fields)
    assert "metric_ids" in declared and "row_count" in declared
    assert "rows" not in declared and "values" not in declared


# --- the serialised-content sweep --------------------------------------------


@pytest.mark.parametrize("forbidden", FORBIDDEN_CONTENT)
def test_no_forbidden_content_survives_serialisation(forbidden: str) -> None:
    assert forbidden not in _populated_event().model_dump_json()


def test_the_sweep_is_not_vacuous() -> None:
    """The event really is populated, so absence means something."""
    dumped = _populated_event().model_dump_json()
    assert "installs" in dumped, "the sweep must run against a populated event"
    assert "999" in dumped
    assert len(dumped) > 300


def test_the_row_count_is_a_count_not_the_rows() -> None:
    event = _populated_event()
    assert event.row_count == 42
    assert '"rows"' not in event.model_dump_json()


def test_a_pre_authorization_refusal_carries_no_identity() -> None:
    """Nothing was evaluated, so there is nothing to identify."""
    event = _populated_event(
        stage=AuditStage.REFUSAL,
        query_identity=None,
        outcome=Outcome.DENY,
        reason_code=AnalyticsReasonCode.REQUEST_MALFORMED,
        dry_run_bytes=None,
        actual_bytes=None,
        row_count=None,
    )
    assert event.query_identity is None
    assert event.actual_bytes is None


# --- logs and traces ---------------------------------------------------------


@pytest.mark.parametrize("path", _MODULES, ids=lambda p: str(p.relative_to(SRC)))
def test_no_module_logs_a_value_row_or_query_text(path: Path) -> None:
    """Logs are the surface most likely to be shipped somewhere less protected."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        name = getattr(target, "attr", None) or getattr(target, "id", None)
        if name not in {"debug", "info", "warning", "error", "exception", "print", "log"}:
            continue
        rendered = ast.unparse(node).lower()
        for leak in ("row", "value", "text", "parameters", "credential", "principal"):
            assert leak not in rendered, f"{path.relative_to(SRC)} logs {leak!r}: {rendered[:80]}"


def test_no_module_emits_to_an_unstructured_sink() -> None:
    """A print or a bare logger bypasses the denylist entirely."""
    offenders: list[str] = []
    for path in _MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "print":
                offenders.append(str(path.relative_to(SRC)))
    assert not offenders, offenders
