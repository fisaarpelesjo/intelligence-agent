"""Value-free ledger — T087 (FR-066, FR-078; SC-013, SC-036).

Two independent assertions, because either alone would miss the other's failure.

**The declared field set**: no field on the entry *or* on an attachment record
can hold a metric value, a result row, an aggregate, a filter value or query
text. This catches the defect at the type, before anything is written.

**A serialised-content scan**: an entry populated with realistic metadata is
dumped and searched for business figures. This catches the defect that the field
set cannot — a value smuggled into a field whose name sounds innocent, or
appended to an opaque handle.

Attachment records are included deliberately. They are the newest surface
(`FR-078`), they are written on the attach path rather than the acquire path,
and a scan that only covered the entry would have been silently incomplete from
the day they were added.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from analytics_query.contracts.audit import AuditStage
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.execution.ledger import (
    AuthorizationContext,
    ExecutionKey,
    derive_authorization_fingerprint,
)
from analytics_query.execution.ledger_entry import (
    ExecutionAttachment,
    ExecutionLedgerEntry,
    ExecutionStatus,
)
from analytics_query.execution.ledger_memory import InMemoryExecutionLedger

pytestmark = pytest.mark.contract

#: Field names that would mean a business figure could be stored.
FORBIDDEN_FIELDS = (
    "value",
    "values",
    "row",
    "rows",
    "result",
    "results",
    "payload",
    "cell",
    "cells",
    "aggregate",
    "total",
    "figure",
    "measure",
    "sql",
    "query_text",
    "statement",
    "filter_value",
    "filter_values",
    "credential",
    "token",
    "secret",
    "email",
    "name",
)

#: Figures a realistic execution would have touched. None may survive into the
#: serialised entry, which records that an execution happened and what it cost —
#: never what it returned.
BUSINESS_FIGURES = ("123456", "98765.43", "installs_total", "BR", "android", "revenue")


# --- the declared field set --------------------------------------------------


@pytest.mark.parametrize(
    "model", [ExecutionLedgerEntry, ExecutionAttachment], ids=lambda m: m.__name__
)
@pytest.mark.parametrize("forbidden", FORBIDDEN_FIELDS)
def test_no_field_could_hold_a_business_figure(model: type[BaseModel], forbidden: str) -> None:
    declared = {name.lower() for name in model.model_fields}
    assert forbidden not in declared, f"{model.__name__} declares {forbidden!r}"


def test_the_entry_records_only_counts_and_handles() -> None:
    """Counts, timings, status, revision ids and an opaque job ref. Nothing else."""
    declared = set(ExecutionLedgerEntry.model_fields)
    assert declared == {
        "query_identity",
        "authorization_context_fingerprint",
        "correlation_id",
        "principal_ref",
        "attachments",
        "status",
        "dry_run_bytes",
        "actual_bytes",
        "row_count",
        "started_at",
        "ended_at",
        "data_revisions",
        "catalog_release_id",
        "policy_version",
        "warehouse_job_ref",
        "terminal_reason_code",
        "audit_stages_accepted",
    }


def test_an_attachment_records_only_who_attached_and_when() -> None:
    assert set(ExecutionAttachment.model_fields) == {
        "principal_ref",
        "correlation_id",
        "attached_at",
    }


# --- the serialised-content scan ---------------------------------------------


def _populated_entry() -> ExecutionLedgerEntry:
    """An entry carrying everything a real execution would have set."""
    context = AuthorizationContext(
        authorization_scope="tenant-a",
        granted_access_tags=frozenset({"installs:read"}),
        principal_type="user",
        authorization_policy_pin="authpol-1",
    )
    key = ExecutionKey("a" * 64, derive_authorization_fingerprint(context))
    ledger = InMemoryExecutionLedger()
    ledger.acquire(key, correlation_id="c-1", principal_ref="opaque-acquirer")
    ledger.attach(key, correlation_id="c-2", principal_ref="opaque-attacher")
    return ledger.complete(
        key,
        ExecutionStatus.COMPLETED,
        dry_run_bytes=1_000_000,
        actual_bytes=999_999,
        row_count=42,
        data_revisions=("rev-1", "rev-2"),
        catalog_release_id="r-1",
        policy_version="p-1",
        warehouse_job_ref="job-abc",
        terminal_reason_code=AnalyticsReasonCode.QUERY_EXECUTED,
        audit_stages_accepted=(AuditStage.VALIDATION, AuditStage.EXECUTION_COMPLETE),
    )


@pytest.mark.parametrize("figure", BUSINESS_FIGURES)
def test_no_business_figure_appears_in_a_serialised_entry(figure: str) -> None:
    assert figure not in _populated_entry().model_dump_json()


def test_the_scan_is_not_vacuous() -> None:
    """The entry really is populated, so absence means something."""
    dumped = _populated_entry().model_dump_json()
    assert "999999" in dumped, "the scan must run against a populated entry"
    assert "job-abc" in dumped
    assert len(dumped) > 300


def test_attachment_records_are_covered_by_the_same_scan() -> None:
    """The newest surface, written on a different path from acquisition."""
    entry = _populated_entry()
    assert len(entry.attachments) == 1
    dumped = entry.model_dump_json()
    assert "opaque-attacher" in dumped, "attachments must be serialised at all"
    for figure in BUSINESS_FIGURES:
        assert figure not in dumped


def test_an_attachment_alone_carries_no_figure() -> None:
    attachment = ExecutionAttachment(
        principal_ref="opaque-1", correlation_id="c-9", attached_at=datetime.now(UTC)
    )
    dumped = attachment.model_dump_json()
    for figure in BUSINESS_FIGURES:
        assert figure not in dumped


def test_the_row_count_is_a_count_not_the_rows() -> None:
    """42 rows, and none of them present."""
    entry = _populated_entry()
    assert entry.row_count == 42
    assert "installs" not in entry.model_dump_json()


def test_the_job_reference_is_opaque() -> None:
    """A handle, never the query text it identifies."""
    entry = _populated_entry()
    assert entry.warehouse_job_ref == "job-abc"
    for fragment in ("SELECT", "FROM", "WHERE", "semantic."):
        assert fragment not in entry.model_dump_json()
