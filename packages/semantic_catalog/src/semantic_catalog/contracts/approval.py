"""Pending visibility approvals — T019 (FR-058 - FR-060).

A pending metric may expose ``public_name`` or ``expected_available_from`` only
when *that specific field* carries a valid approval. A boolean flag inside the
metric file would be self-asserted by whoever edits the metric, which is the
review bypass the approval exists to prevent — so approvals live in a separate
governed file routed to a different CODEOWNERS group.

``source_commit`` binds an approval to the content it approved. If the field's
value changes in a later commit, the approval no longer covers it and the field
is omitted until re-approved. That is what stops an approval for a harmless
label from silently covering a later, different one.

**Every failure omits the field.** Missing, expired, rejected, commit-mismatched
or self-approved all resolve to omission — never a default, never a placeholder,
never an inferred value (FR-060). Omission is the safe failure: a reader learns
nothing rather than learning something unapproved.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import Field, StrictInt, model_validator

from ._base import CatalogModel, Identifier

__all__ = [
    "ApprovalStatus",
    "PendingVisibilityApproval",
    "PendingVisibilityApprovals",
    "VisibilityDenial",
]


class ApprovalStatus(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class VisibilityDenial(StrEnum):
    """Why a field is withheld. Every member results in omission."""

    NO_APPROVAL = "no_approval"
    REJECTED = "rejected"
    EXPIRED = "expired"
    COMMIT_MISMATCH = "commit_mismatch"
    FIELD_NOT_EXPOSABLE = "field_not_exposable"
    SELF_APPROVAL = "self_approval"
    ROLE_NOT_PERMITTED = "role_not_permitted"


class PendingVisibilityApproval(CatalogModel):
    """One approval, for one field of one metric."""

    metric_id: Identifier
    field_name: Identifier
    approval_status: ApprovalStatus
    approved_by_role: Identifier = Field(
        description="A role from the ownership registry. Never an individual.",
    )
    approved_at: date
    source_commit: str = Field(min_length=7, description="Binds the approval to approved content.")
    expires_at: date | None = None

    @model_validator(mode="after")
    def _expiry_after_approval(self) -> PendingVisibilityApproval:
        if self.expires_at is not None and self.expires_at < self.approved_at:
            raise ValueError(
                f"approval for {self.metric_id}.{self.field_name} expires {self.expires_at} "
                f"before it was granted {self.approved_at}"
            )
        return self


class PendingVisibilityApprovals(CatalogModel):
    """``semantic/governance/pending-visibility-approvals.yaml``."""

    catalog_schema_version: StrictInt
    kind: Literal["pending_visibility_approvals"]
    approvals: tuple[PendingVisibilityApproval, ...] = ()

    @model_validator(mode="after")
    def _one_approval_per_metric_field(self) -> PendingVisibilityApprovals:
        seen: set[tuple[str, str]] = set()
        for approval in self.approvals:
            key = (approval.metric_id, approval.field_name)
            if key in seen:
                raise ValueError(
                    f"two approvals for {approval.metric_id}.{approval.field_name}; "
                    "ambiguous approval is never resolved by preference"
                )
            seen.add(key)
        return self

    def evaluate(
        self,
        metric_id: str,
        field_name: str,
        *,
        current_commit: str,
        on: date,
        exposable_fields: tuple[str, ...],
        proposer_role: str | None = None,
        self_approval_allowed: bool = False,
        permitted_roles: frozenset[str] | None = None,
    ) -> VisibilityDenial | None:
        """``None`` exposes the field; a :class:`VisibilityDenial` omits it.

        Checked in order of decreasing bluntness so the reported reason is the
        most actionable one.
        """
        if field_name not in exposable_fields:
            return VisibilityDenial.FIELD_NOT_EXPOSABLE
        approval = next(
            (a for a in self.approvals if a.metric_id == metric_id and a.field_name == field_name),
            None,
        )
        if approval is None:
            return VisibilityDenial.NO_APPROVAL
        if approval.approval_status is ApprovalStatus.REJECTED:
            return VisibilityDenial.REJECTED
        if approval.expires_at is not None and on > approval.expires_at:
            return VisibilityDenial.EXPIRED
        if approval.source_commit != current_commit:
            return VisibilityDenial.COMMIT_MISMATCH
        if permitted_roles is not None and approval.approved_by_role not in permitted_roles:
            return VisibilityDenial.ROLE_NOT_PERMITTED
        if (
            proposer_role is not None
            and approval.approved_by_role == proposer_role
            and not self_approval_allowed
        ):
            return VisibilityDenial.SELF_APPROVAL
        return None
