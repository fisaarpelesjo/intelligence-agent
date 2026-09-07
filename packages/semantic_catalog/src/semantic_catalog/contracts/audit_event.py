"""Runtime audit event contract — T020 (FR-041, FR-043).

**Contract only. Nothing here emits.** The emitter integration is T075; it wraps
the decision pipeline and produces one event per ALLOW and per DENY. Splitting
them means the contract can be defined, validated and tested before any pipeline
exists to feed it.

The actor field is **required**, and that is a deliberate reversal of an earlier
draft. An audit trail with no actor cannot answer "which principal was refused
access", which makes FR-042 unverifiable in practice. An actorless audit log is
not a privacy feature; it is a broken audit log.

Privacy comes from **pseudonymity and minimisation**, not from deleting
traceability:

* ``principal_id`` is opaque and **stable per subject** — stable so repeated
  refusals are observable, opaque so the event carries no direct PII;
* the denylist below is enforced by the model, so a caller cannot pass an email
  address as a principal id and quietly produce a compliant-looking event;
* ``metric_ids`` and friends record *what was asked for* using governed
  identifiers, so the event never reproduces *what was typed*.

``policy_version`` sits beside ``catalog_release_id`` on purpose: a decision can
change because the catalog changed or because the policy did, and an audit that
conflates the two cannot explain a behaviour change.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field, StringConstraints, field_validator, model_validator

from ._base import CatalogModel, Identifier
from .access_tag import PrincipalType
from .reason_codes import Outcome, ReasonCode, outcome_for

__all__ = [
    "AuditDateRange",
    "CatalogDecisionAuditEvent",
    "EvidenceKind",
    "EvidenceRef",
    "ForbiddenAuditContentError",
    "RequestedOperation",
]


class ForbiddenAuditContentError(ValueError):
    """A value matched the forbidden-content denylist."""


class RequestedOperation(StrEnum):
    VALIDATE = "validate"
    RESOLVE = "resolve"
    SEARCH = "search"
    MATRIX = "matrix"
    COMPLIANCE = "compliance"


class EvidenceKind(StrEnum):
    METRIC_VERSION = "metric_version"
    FRESHNESS_SNAPSHOT = "freshness_snapshot"
    COVERAGE_WINDOW = "coverage_window"
    COMPARABILITY_RULE = "comparability_rule"
    CATALOG_RELEASE = "catalog_release"
    DATA_REVISION = "data_revision"


# Shapes that must never appear in an audit event. Each is a category the
# specification names explicitly (FR-041, decision-contract §5).
_FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email address", re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")),
    ("bearer or access token", re.compile(r"\b(bearer|token)\s*[:=]\s*\S+", re.IGNORECASE)),
    ("private key block", re.compile(r"BEGIN [A-Z ]*PRIVATE KEY")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("IPv4 address", re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")),
    ("password assignment", re.compile(r"\bpassword\s*[:=]", re.IGNORECASE)),
)

_OPAQUE_PRINCIPAL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$")

#: Opaque, stable subject identifier. Stability is as load-bearing as opacity: a
#: per-request rotating id would satisfy privacy and destroy the audit.
OpaquePrincipalId = Annotated[str, StringConstraints(min_length=8, max_length=128)]


def _reject_forbidden(value: str, *, field: str) -> str:
    for label, pattern in _FORBIDDEN_PATTERNS:
        if pattern.search(value):
            raise ForbiddenAuditContentError(
                f"{field} contains a {label}; audit events carry a pseudonymous actor "
                "reference and governed identifiers only - never direct PII, credentials "
                "or prompt text (FR-041)"
            )
    return value


class EvidenceRef(CatalogModel):
    """What a decision stood on."""

    kind: EvidenceKind
    id: str = Field(min_length=1)


class AuditDateRange(CatalogModel):
    """Canonical-zone dates. The request's period, not a timestamp range."""

    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> AuditDateRange:
        if self.end < self.start:
            raise ValueError(f"date range ends {self.end} before it starts {self.start}")
        return self


class CatalogDecisionAuditEvent(CatalogModel):
    """One event per decision. Emitted by T075; defined and validated here."""

    # correlation
    correlation_id: str = Field(min_length=1)
    occurred_at: datetime
    decision_id: str = Field(min_length=1)

    # actor — REQUIRED (see module docstring)
    principal_id: OpaquePrincipalId
    principal_type: PrincipalType
    authorization_scope: Identifier | None = None

    # request
    requested_operation: RequestedOperation
    metric_ids: tuple[Identifier, ...] = ()
    dimension_ids: tuple[Identifier, ...] = ()
    source_ids: tuple[Identifier, ...] = ()
    date_range: AuditDateRange | None = None
    granted_access_tags: tuple[Identifier, ...] = ()

    # outcome
    outcome: Outcome
    reason_code: ReasonCode
    resolved_versions: tuple[str, ...] = ()
    policy_version: str = Field(min_length=1)
    catalog_release_id: str = Field(min_length=1)
    evidence_refs: tuple[EvidenceRef, ...] = ()

    @field_validator("principal_id")
    @classmethod
    def _principal_is_opaque(cls, value: str) -> str:
        _reject_forbidden(value, field="principal_id")
        if not _OPAQUE_PRINCIPAL.match(value):
            raise ForbiddenAuditContentError(
                f"principal_id {value!r} is not an opaque internal subject identifier; "
                "names, emails and raw external account identifiers are forbidden"
            )
        return value

    @field_validator("correlation_id", "decision_id", "policy_version", "catalog_release_id")
    @classmethod
    def _free_of_forbidden_content(cls, value: str) -> str:
        return _reject_forbidden(value, field="value")

    @model_validator(mode="after")
    def _outcome_matches_reason_code(self) -> CatalogDecisionAuditEvent:
        expected = outcome_for(self.reason_code)
        if self.outcome is not expected:
            raise ValueError(
                f"reason code {self.reason_code.value} is classified {expected.value}, but the "
                f"event records {self.outcome.value}; a denial recorded as an allow is unauditable"
            )
        return self
