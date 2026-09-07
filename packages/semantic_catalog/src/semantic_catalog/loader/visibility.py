"""Pending-visibility approval resolution — T042 (FR-058, FR-059, FR-060).

The T019 contract already knows how to evaluate one approval. This module is
what wires it to the **governed policy** (T016) so no semantics are invented
here: the exposable-field allowlist, the permitted approver roles and the
self-approval rule are all read from ``catalog-policy.yaml``, never hard-coded.

That matters for one reason in particular. Whether a proposer may count towards
their own approval is a governance decision recorded in
``authorization.self_approval_allowed``; deciding it in code would make changing
it a release instead of a reviewed YAML edit (ADR 0003 §3).

**Every failure omits the field.** Missing, rejected, expired, commit-mismatched,
role-not-permitted and self-approved all resolve to omission — never a default,
never a placeholder, never an inferred value (FR-060). Omission is the safe
failure: a reader learns nothing rather than learning something unapproved.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from ..contracts.approval import PendingVisibilityApprovals, VisibilityDenial
from ..contracts.policy import CatalogPolicy

__all__ = [
    "FieldVisibility",
    "VisibilityResolution",
    "resolve_visibility",
]


@dataclass(frozen=True, slots=True)
class FieldVisibility:
    """Whether one field of one pending metric may be exposed."""

    field_name: str
    exposed: bool
    denial: VisibilityDenial | None


@dataclass(frozen=True, slots=True)
class VisibilityResolution:
    """Resolution for every exposable field the policy declares."""

    metric_id: str
    fields: Mapping[str, FieldVisibility]

    def exposes(self, field_name: str) -> bool:
        """False for any field the policy does not declare exposable at all."""
        decision = self.fields.get(field_name)
        return decision is not None and decision.exposed

    def denial_for(self, field_name: str) -> VisibilityDenial | None:
        decision = self.fields.get(field_name)
        if decision is None:
            return VisibilityDenial.FIELD_NOT_EXPOSABLE
        return decision.denial


def resolve_visibility(
    metric_id: str,
    *,
    policy: CatalogPolicy,
    approvals: PendingVisibilityApprovals | None,
    current_commit: str,
    on: date,
    proposer_role: str | None = None,
) -> VisibilityResolution:
    """Resolve every policy-declared exposable field for ``metric_id``.

    An absent approvals file denies everything rather than exposing everything:
    "no approval file" reads as "nothing is approved", which is the only safe
    reading of a missing control.

    ``permitted_roles`` comes from the policy's ``approval_roles`` plus its
    ``owner_role`` — the same set the policy uses to resolve a policy-class
    change — so an approval granted by a role outside the governance registry
    does not silently count.
    """
    exposable = policy.pending_visibility.exposable_fields
    permitted = frozenset(policy.approval_roles) | {policy.owner_role}

    if approvals is None:
        return VisibilityResolution(
            metric_id=metric_id,
            fields={
                name: FieldVisibility(name, False, VisibilityDenial.NO_APPROVAL)
                for name in exposable
            },
        )

    resolved: dict[str, FieldVisibility] = {}
    for field_name in exposable:
        denial = approvals.evaluate(
            metric_id,
            field_name,
            current_commit=current_commit,
            on=on,
            exposable_fields=exposable,
            proposer_role=proposer_role,
            self_approval_allowed=policy.authorization.self_approval_allowed,
            permitted_roles=permitted,
        )
        resolved[field_name] = FieldVisibility(field_name, denial is None, denial)

    return VisibilityResolution(metric_id=metric_id, fields=resolved)
