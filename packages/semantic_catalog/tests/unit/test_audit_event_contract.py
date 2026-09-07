"""Audit-event **contract** test — T080 (FR-041; decision-contract §5).

Tests the contract (T020), not the emitter. Three properties:

**The actor is required.** An earlier draft said the record carries "never the
requester's identity". That was wrong and is corrected in the contract: an audit
trail with no actor cannot answer "who was refused access", which is the central
question of authorisation auditing. Privacy comes from a pseudonymous identifier
and data minimisation, not from deleting traceability.

**The denylist is clean.** Names, emails, tokens, keys, IP addresses and password
assignments are refused wherever they appear — not filtered, refused.

**The principal is stable.** Stability is as load-bearing as opacity: an
identifier that rotated per request would satisfy privacy and destroy the audit,
because "this principal was refused eleven times" would be unobservable.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.contracts.audit_event import (
    AuditDateRange,
    CatalogDecisionAuditEvent,
    EvidenceKind,
    EvidenceRef,
    ForbiddenAuditContentError,
    RequestedOperation,
)
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode, outcome_for

pytestmark = pytest.mark.unit

PRINCIPAL = "prn_" + "a" * 24
STAMP = datetime(2026, 8, 11, 12, tzinfo=UTC)


def _event(**overrides: object) -> CatalogDecisionAuditEvent:
    payload: dict[str, object] = {
        "correlation_id": "corr-1",
        "occurred_at": STAMP,
        "decision_id": "sha256:abc",
        "principal_id": PRINCIPAL,
        "principal_type": PrincipalType.USER,
        "requested_operation": RequestedOperation.VALIDATE,
        "metric_ids": ("app_sessions",),
        "source_ids": ("app_a",),
        "date_range": AuditDateRange(start=date(2026, 7, 1), end=date(2026, 7, 31)),
        "granted_access_tags": ("standard",),
        "outcome": Outcome.DENY,
        "reason_code": ReasonCode.METRIC_PENDING,
        "policy_version": "catalog_core@1",
        "catalog_release_id": "sha256:rel",
        "evidence_refs": (EvidenceRef(kind=EvidenceKind.CATALOG_RELEASE, id="sha256:rel"),),
    }
    payload.update(overrides)
    return CatalogDecisionAuditEvent.model_validate(payload)


# --- the actor is required --------------------------------------------------


@pytest.mark.parametrize("field", ["principal_id", "principal_type"])
def test_the_actor_is_required(field: str) -> None:
    payload = {
        "correlation_id": "c",
        "occurred_at": STAMP,
        "decision_id": "d",
        "principal_id": PRINCIPAL,
        "principal_type": PrincipalType.USER,
        "requested_operation": RequestedOperation.VALIDATE,
        "outcome": Outcome.DENY,
        "reason_code": ReasonCode.METRIC_PENDING,
        "policy_version": "p@1",
        "catalog_release_id": "r",
    }
    del payload[field]
    with pytest.raises(ValidationError):
        CatalogDecisionAuditEvent.model_validate(payload)


def test_the_principal_must_be_opaque() -> None:
    """A raw account identifier is refused even though it is 'just an id'."""
    with pytest.raises((ValidationError, ForbiddenAuditContentError)):
        _event(principal_id="maria.silva@example.com")


@pytest.mark.parametrize(
    "value",
    [
        "maria.silva@example.com",
        "Bearer: abc123def456",
        "-----BEGIN RSA PRIVATE KEY-----",
        "AKIA" + "B" * 16,
        "gh" + "p_" + "z" * 30,
        "192.168.1.10",
        "password=hunter2",
    ],
)
def test_the_denylist_refuses_direct_pii_and_credentials(value: str) -> None:
    with pytest.raises((ValidationError, ForbiddenAuditContentError)):
        _event(correlation_id=value)


def test_the_denylist_covers_every_free_text_field() -> None:
    for field in ("correlation_id", "decision_id", "policy_version", "catalog_release_id"):
        with pytest.raises((ValidationError, ForbiddenAuditContentError)):
            _event(**{field: "leak@example.com"})


def test_a_service_principal_is_distinguishable_from_a_person() -> None:
    """The two need different retention and review treatment."""
    event = _event(principal_type=PrincipalType.SERVICE_PRINCIPAL)
    assert event.principal_type is PrincipalType.SERVICE_PRINCIPAL


# --- the principal is stable ------------------------------------------------


def test_the_principal_is_stable_across_evaluations() -> None:
    """Same subject, two decisions, one identifier — or the audit is unusable."""
    first = _event(decision_id="sha256:one")
    second = _event(decision_id="sha256:two", outcome=Outcome.DENY)
    assert first.principal_id == second.principal_id == PRINCIPAL
    assert first.decision_id != second.decision_id


def test_repeated_refusals_for_one_principal_are_observable() -> None:
    events = [_event(decision_id=f"sha256:{n}") for n in range(11)]
    refused = [e for e in events if e.outcome is Outcome.DENY]
    assert len({e.principal_id for e in refused}) == 1
    assert len(refused) == 11


# --- outcome integrity ------------------------------------------------------


def test_the_outcome_must_match_the_reason_code() -> None:
    with pytest.raises(ValidationError, match="unauditable"):
        _event(outcome=Outcome.ALLOW, reason_code=ReasonCode.METRIC_PENDING)


@pytest.mark.parametrize(
    "outcome, code",
    [
        (Outcome.ALLOW, ReasonCode.REQUEST_ALLOWED),
        (Outcome.DENY, ReasonCode.ACCESS_DENIED),
        (Outcome.ALLOW_WITH_CAVEAT, ReasonCode.DEPRECATED_METRIC),
    ],
)
def test_every_outcome_class_is_recordable(outcome: Outcome, code: ReasonCode) -> None:
    """An outcome that cannot be recorded is an outcome that cannot be audited."""
    event = _event(outcome=outcome, reason_code=code)
    assert event.outcome is outcome
    assert outcome_for(event.reason_code) is outcome


# --- what the event never carries -------------------------------------------


def test_the_event_has_no_field_for_a_metric_value_or_prompt_text() -> None:
    """Absent by construction, not stripped by a filter."""
    fields = set(CatalogDecisionAuditEvent.model_fields)
    for forbidden in ("value", "values", "rows", "prompt", "question", "text", "payload"):
        assert forbidden not in fields, forbidden


def test_unknown_fields_are_refused() -> None:
    with pytest.raises(ValidationError):
        _event(prompt_text="quantos usuários ativos ontem?")


def test_the_event_carries_governed_identifiers_only() -> None:
    event = _event(
        evidence_refs=(
            EvidenceRef(kind=EvidenceKind.CATALOG_RELEASE, id="sha256:rel"),
            EvidenceRef(kind=EvidenceKind.DATA_REVISION, id="app_a@rev3"),
            EvidenceRef(kind=EvidenceKind.METRIC_VERSION, id="app_sessions@1"),
        )
    )
    serialised = str(event.model_dump(mode="json"))
    assert "@" in serialised  # revision ids legitimately contain one
    assert "example.com" not in serialised
    assert all(ref.id for ref in event.evidence_refs)


def test_provenance_fields_are_all_present() -> None:
    """Policy, release and revision provenance travel on every event."""
    event = _event(evidence_refs=(EvidenceRef(kind=EvidenceKind.DATA_REVISION, id="app_a@rev3"),))
    assert event.policy_version
    assert event.catalog_release_id
    assert any(ref.kind is EvidenceKind.DATA_REVISION for ref in event.evidence_refs)
