"""Ledger port, entry and in-process implementation — T039, T040, T045.

Covers FR-036, FR-065, FR-066, FR-078 and SC-012, SC-013, SC-036. Those three
tasks state their completion evidence here rather than leaving it a claim nobody
checks — Phase 4 gives them no dedicated test task.

The load-bearing assertion is the last group: **equal query identity plus a
differing authorization-context fingerprint must acquire, never attach.** That is
the defect the `ExecutionKey` split exists to close, and it is asserted against
the real in-process implementation rather than against the port's docstring.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

import pytest

from analytics_query.contracts._base import ContractViolation, build
from analytics_query.execution.ledger import (
    Acquired,
    Attached,
    AuthorizationContext,
    ExecutionKey,
    UnresolvedAuthorizationContext,
    derive_authorization_fingerprint,
)
from analytics_query.execution.ledger_entry import (
    ExecutionAttachment,
    ExecutionLedgerEntry,
    ExecutionStatus,
)
from analytics_query.execution.ledger_memory import InMemoryExecutionLedger

pytestmark = pytest.mark.contract

IDENTITY = "a" * 64
CTX_A = AuthorizationContext(
    authorization_scope="tenant-a",
    granted_access_tags=frozenset({"installs:read"}),
    principal_type="user",
    authorization_policy_pin="authpol-1",
)
CTX_B = AuthorizationContext(
    authorization_scope="tenant-b",
    granted_access_tags=frozenset({"installs:read"}),
    principal_type="user",
    authorization_policy_pin="authpol-1",
)


def _key(context: AuthorizationContext, identity: str = IDENTITY) -> ExecutionKey:
    return ExecutionKey(identity, derive_authorization_fingerprint(context))


# --- fingerprint (FR-078) ----------------------------------------------------


def test_the_fingerprint_is_deterministic_and_tag_order_independent() -> None:
    a = AuthorizationContext("t", frozenset({"x", "y"}), "user", "p")
    b = AuthorizationContext("t", frozenset({"y", "x"}), "user", "p")
    assert derive_authorization_fingerprint(a) == derive_authorization_fingerprint(b)


def test_the_fingerprint_separates_scopes_and_grants() -> None:
    base = derive_authorization_fingerprint(CTX_A)
    assert derive_authorization_fingerprint(CTX_B) != base
    wider = AuthorizationContext(
        "tenant-a", frozenset({"installs:read", "revenue:read"}), "user", "authpol-1"
    )
    assert derive_authorization_fingerprint(wider) != base
    repinned = AuthorizationContext("tenant-a", frozenset({"installs:read"}), "user", "authpol-2")
    assert derive_authorization_fingerprint(repinned) != base


def test_the_fingerprint_is_a_sha256_hex_digest_carrying_no_input_verbatim() -> None:
    """Non-reversible, so it is safe on a metadata-only ledger."""
    fingerprint = derive_authorization_fingerprint(CTX_A)
    assert len(fingerprint) == 64
    assert all(c in "0123456789abcdef" for c in fingerprint)
    for secret in ("tenant-a", "installs:read", "authpol-1", "user"):
        assert secret not in fingerprint


@pytest.mark.parametrize(
    "context",
    [
        AuthorizationContext("", frozenset({"x"}), "user", "p"),
        AuthorizationContext("t", frozenset({"x"}), "", "p"),
        AuthorizationContext("t", frozenset({"x"}), "user", ""),
        AuthorizationContext("t", frozenset({""}), "user", "p"),
    ],
)
def test_an_unresolved_context_yields_no_fingerprint(context: AuthorizationContext) -> None:
    """A partial fingerprint would misfile the request silently."""
    with pytest.raises(UnresolvedAuthorizationContext):
        derive_authorization_fingerprint(context)


def test_an_execution_key_cannot_be_built_from_identity_alone() -> None:
    with pytest.raises(UnresolvedAuthorizationContext):
        ExecutionKey(IDENTITY, "")


def test_no_ledger_method_accepts_a_bare_identity() -> None:
    """Identity-only keying is unrepresentable, not merely discouraged."""
    import inspect

    ledger = InMemoryExecutionLedger()
    for name in ("acquire", "attach", "complete", "get"):
        params = inspect.signature(getattr(ledger, name)).parameters
        assert "key" in params
        assert "identity" not in params and "query_identity" not in params


# --- single-flight within one key (FR-036, SC-012) ---------------------------


def test_a_second_caller_with_the_same_key_attaches() -> None:
    ledger = InMemoryExecutionLedger()
    key = _key(CTX_A)
    first = ledger.acquire(key, correlation_id="c1", principal_ref="p1")
    second = ledger.acquire(key, correlation_id="c2", principal_ref="p2")
    assert isinstance(first, Acquired)
    assert isinstance(second, Attached)


def test_concurrent_acquirers_of_one_key_yield_exactly_one_owner() -> None:
    ledger = InMemoryExecutionLedger()
    key = _key(CTX_A)
    results: list[object] = []
    barrier = threading.Barrier(8)

    def contend(i: int) -> None:
        barrier.wait()
        results.append(ledger.acquire(key, correlation_id=f"c{i}", principal_ref=f"p{i}"))

    threads = [threading.Thread(target=contend, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(isinstance(r, Acquired) for r in results) == 1
    assert sum(isinstance(r, Attached) for r in results) == 7


def test_a_terminal_entry_makes_the_next_request_a_fresh_execution() -> None:
    """A re-request is billed on its own; only RUNNING and UNKNOWN attach."""
    ledger = InMemoryExecutionLedger()
    key = _key(CTX_A)
    ledger.acquire(key, correlation_id="c1", principal_ref="p1")
    ledger.complete(key, ExecutionStatus.COMPLETED, actual_bytes=10, row_count=1)
    again = ledger.acquire(key, correlation_id="c2", principal_ref="p1")
    assert isinstance(again, Acquired)


def test_an_unknown_entry_attaches_because_it_may_already_have_billed() -> None:
    ledger = InMemoryExecutionLedger()
    key = _key(CTX_A)
    ledger.acquire(key, correlation_id="c1", principal_ref="p1")
    ledger.complete(key, ExecutionStatus.UNKNOWN)
    retry = ledger.acquire(key, correlation_id="c2", principal_ref="p1")
    assert isinstance(retry, Attached)


def test_completing_the_same_terminal_status_twice_is_a_no_op() -> None:
    ledger = InMemoryExecutionLedger()
    key = _key(CTX_A)
    ledger.acquire(key, correlation_id="c1", principal_ref="p1")
    first = ledger.complete(key, ExecutionStatus.COMPLETED, actual_bytes=10)
    second = ledger.complete(key, ExecutionStatus.COMPLETED, actual_bytes=10)
    assert first.ended_at == second.ended_at


# --- cross-authorization isolation (FR-078, SC-036) -------------------------


def test_equal_identity_with_a_different_fingerprint_acquires_rather_than_attaches() -> None:
    """The defect the ExecutionKey split closes, asserted end to end."""
    ledger = InMemoryExecutionLedger()
    key_a, key_b = _key(CTX_A), _key(CTX_B)
    assert key_a.query_identity == key_b.query_identity

    first = ledger.acquire(key_a, correlation_id="c1", principal_ref="p-a")
    second = ledger.acquire(key_b, correlation_id="c2", principal_ref="p-b")
    assert isinstance(first, Acquired)
    assert isinstance(second, Acquired), "a different authorization context must never attach"
    assert first.entry.correlation_id != second.entry.correlation_id


def test_a_different_context_cannot_observe_the_others_status_or_job() -> None:
    ledger = InMemoryExecutionLedger()
    key_a, key_b = _key(CTX_A), _key(CTX_B)
    ledger.acquire(key_a, correlation_id="c1", principal_ref="p-a")
    ledger.complete(key_a, ExecutionStatus.COMPLETED, actual_bytes=999, warehouse_job_ref="job-a")

    assert ledger.get(key_b) is None
    assert ledger.attach(key_b, correlation_id="c2", principal_ref="p-b") is None

    entry_a = ledger.get(key_a)
    assert entry_a is not None and entry_a.warehouse_job_ref == "job-a"


def test_the_same_context_still_retries_so_single_flight_survives() -> None:
    """The fingerprint hashes the context, not the principal."""
    ledger = InMemoryExecutionLedger()
    key = _key(CTX_A)
    ledger.acquire(key, correlation_id="c1", principal_ref="p-a")
    retry = ledger.attach(key, correlation_id="c1-retry", principal_ref="p-a")
    assert retry is not None


# --- attribution (FR-078) ----------------------------------------------------


def test_an_attachment_names_the_attaching_principal_without_rewriting_the_acquirer() -> None:
    ledger = InMemoryExecutionLedger()
    key = _key(CTX_A)
    ledger.acquire(key, correlation_id="c1", principal_ref="p-acquirer")
    attached = ledger.attach(key, correlation_id="c2", principal_ref="p-attacher")

    assert attached is not None
    assert attached.principal_ref == "p-acquirer"
    assert [a.principal_ref for a in attached.attachments] == ["p-attacher"]


def test_the_acquiring_request_is_not_recorded_as_an_attachment() -> None:
    """Otherwise "how many principals received this" would be wrong."""
    entry = build(
        ExecutionLedgerEntry,
        query_identity=IDENTITY,
        authorization_context_fingerprint="f" * 64,
        correlation_id="c1",
        principal_ref="p1",
        status=ExecutionStatus.RUNNING,
    )
    with pytest.raises(ContractViolation):
        entry.with_attachment(
            ExecutionAttachment(
                principal_ref="p1", correlation_id="c1", attached_at=datetime.now(UTC)
            )
        )


# --- metadata only (FR-065, FR-066, SC-013) ----------------------------------


def test_no_entry_or_attachment_field_can_carry_a_value() -> None:
    forbidden = (
        "value",
        "values",
        "rows",
        "result",
        "sql",
        "query_text",
        "filter_values",
        "payload",
        "cells",
        "aggregate",
        "credential",
        "token",
    )
    for model in (ExecutionLedgerEntry, ExecutionAttachment):
        declared = set(model.model_fields)
        for name in forbidden:
            assert name not in declared, f"{model.__name__} exposes {name}"


def test_the_entry_records_everything_fr_065_requires() -> None:
    declared = set(ExecutionLedgerEntry.model_fields)
    for required in (
        "query_identity",
        "principal_ref",
        "dry_run_bytes",
        "actual_bytes",
        "row_count",
        "started_at",
        "ended_at",
        "status",
        "data_revisions",
    ):
        assert required in declared


def test_a_terminal_entry_must_record_when_it_ended() -> None:
    with pytest.raises(ContractViolation):
        build(
            ExecutionLedgerEntry,
            query_identity=IDENTITY,
            authorization_context_fingerprint="f" * 64,
            correlation_id="c1",
            principal_ref="p1",
            status=ExecutionStatus.COMPLETED,
        )


def test_an_unknown_entry_has_no_end_instant() -> None:
    """The outcome is precisely what was lost; inventing one would be a lie."""
    with pytest.raises(ContractViolation):
        build(
            ExecutionLedgerEntry,
            query_identity=IDENTITY,
            authorization_context_fingerprint="f" * 64,
            correlation_id="c1",
            principal_ref="p1",
            status=ExecutionStatus.UNKNOWN,
            ended_at=datetime.now(UTC),
        )


def test_a_serialised_entry_contains_no_business_figure() -> None:
    ledger = InMemoryExecutionLedger()
    key = _key(CTX_A)
    ledger.acquire(key, correlation_id="c1", principal_ref="p1")
    ledger.attach(key, correlation_id="c2", principal_ref="p2")
    entry = ledger.complete(key, ExecutionStatus.COMPLETED, actual_bytes=10, row_count=3)

    dumped = entry.model_dump_json()
    for leak in ("installs", "12345.67", "row_values", "BR"):
        assert leak not in dumped
