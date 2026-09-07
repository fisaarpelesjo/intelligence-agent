"""Catalog policy — T016 (FR-059, FR-072; ADR 0003).

Governance behaviour lives in data, not code. Changing who approves a metric is
an edit to a reviewed YAML file, never a release. The semantics implemented here
come from ADR 0003 and must not be re-derived by a later consumer.

Three fail-closed properties, each defending against a different failure:

``resolve_effective``
    Zero effective policies, or more than one, raises
    :class:`PolicyUnresolvableError`. There is no assumed default, because a decision
    evaluated under a policy nobody approved is unauditable.

``resolve_approvers``
    An unrecognised change class or an unresolvable role raises. It never falls
    back to the single-metric rule, which would silently under-review the
    cross-cutting change that most needs review.

``self_approval_allowed``
    Defaults to refusing. A proposer cannot satisfy the approval requirement
    alone unless the policy grants it explicitly.

No language model participates in any of this: approval is resolved by lookup
against governed data, and a lookup that does not resolve is an error.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import Field, StrictBool, StrictInt, model_validator

from ._base import CatalogModel, Identifier

__all__ = [
    "ApprovalExpiryBehaviour",
    "ApprovalResolutionError",
    "AuthorizationRules",
    "CatalogPolicy",
    "ChangeClass",
    "PendingVisibilityRules",
    "PolicySet",
    "PolicyUnresolvableError",
    "PublicationRules",
    "RefusalRules",
    "UnknownTagBehaviour",
]


class PolicyUnresolvableError(Exception):
    """No effective policy, or more than one. Always fatal — never defaulted."""


class ApprovalResolutionError(Exception):
    """The approver set cannot be resolved. Fails closed rather than guessing."""


class ChangeClass(StrEnum):
    """ADR 0003. A change that cannot be classified is an error, not a default."""

    SINGLE_METRIC = "single_metric"
    CROSS_CUTTING = "cross_cutting"
    POLICY = "policy"


class UnknownTagBehaviour(StrEnum):
    FAIL_CLOSED = "fail_closed"


class ApprovalExpiryBehaviour(StrEnum):
    OMIT_FIELD = "omit_field"


class AuthorizationRules(CatalogModel):
    default: Literal["deny"] = Field(
        description="Deny-by-default is not configurable; only its scope is.",
    )
    require_access_tag: StrictBool
    unknown_tag_behaviour: UnknownTagBehaviour
    self_approval_allowed: StrictBool = Field(
        default=False,
        description="Refused unless a policy grants it explicitly (ADR 0003 §3).",
    )


class PublicationRules(CatalogModel):
    require_complete_contract: StrictBool
    require_owner: StrictBool
    require_pt_br_content: StrictBool
    require_reason_message_for_publishable_codes: StrictBool


class PendingVisibilityRules(CatalogModel):
    exposable_fields: tuple[Identifier, ...] = Field(
        description="The only fields a pending metric may ever expose (FR-058).",
    )
    require_visibility_approval: StrictBool
    approval_expiry_behaviour: ApprovalExpiryBehaviour


class RefusalRules(CatalogModel):
    disclose_answerable_subset: StrictBool = Field(
        description="Disclosure on a denial; never a substitute payload (FR-022).",
    )
    disclose_replacement_metric_id: StrictBool = Field(
        description="Guidance only; never automatically substituted (FR-064).",
    )


class CatalogPolicy(CatalogModel):
    """``semantic/policies/catalog-policy.yaml``."""

    catalog_schema_version: StrictInt
    kind: Literal["catalog_policy"]

    policy_id: Identifier
    policy_version: StrictInt = Field(ge=1)
    effective_from: date
    supersedes_version: StrictInt | None = None

    owner_role: Identifier
    approval_roles: tuple[Identifier, ...] = Field(min_length=1)

    authorization: AuthorizationRules
    publication: PublicationRules
    pending_visibility: PendingVisibilityRules
    refusal: RefusalRules

    @model_validator(mode="after")
    def _supersedes_is_older(self) -> CatalogPolicy:
        if self.supersedes_version is not None and self.supersedes_version >= self.policy_version:
            raise ValueError(
                f"policy {self.policy_id!r} v{self.policy_version} cannot supersede "
                f"v{self.supersedes_version}"
            )
        return self

    def resolve_approvers(
        self,
        change_class: ChangeClass,
        *,
        affected_owner_roles: tuple[Identifier, ...] = (),
        governance_role: Identifier = "data_governance",
    ) -> frozenset[str]:
        """Roles that must approve a change of ``change_class`` (ADR 0003 §1).

        Raises :class:`ApprovalResolutionError` rather than falling back, because
        under-reviewing a cross-cutting change is exactly the failure the class
        distinction exists to prevent.
        """
        match change_class:
            case ChangeClass.SINGLE_METRIC:
                if not affected_owner_roles:
                    raise ApprovalResolutionError(
                        "single-metric change names no affected owner role; "
                        "cannot resolve approvers"
                    )
                return frozenset(affected_owner_roles)
            case ChangeClass.CROSS_CUTTING:
                if not affected_owner_roles:
                    raise ApprovalResolutionError(
                        "cross-cutting change names no affected owner roles; every affected "
                        "metric's owner must approve (ADR 0003)"
                    )
                return frozenset(affected_owner_roles) | {governance_role}
            case ChangeClass.POLICY:
                return frozenset(self.approval_roles) | {self.owner_role}

    def permits_self_approval(self, proposer_role: str, approvers: frozenset[str]) -> bool:
        """Whether ``proposer_role`` may count towards its own approval.

        False unless the policy grants it. A proposer who is the only approver is
        an approval bypass with extra steps.
        """
        if self.authorization.self_approval_allowed:
            return True
        return bool(approvers - {proposer_role})


class PolicySet(CatalogModel):
    """All authored policies. Exactly one must be effective at any instant."""

    policies: tuple[CatalogPolicy, ...] = Field(min_length=1)

    def resolve_effective(self, on: date) -> CatalogPolicy:
        """The policy effective on ``on``.

        Raises :class:`PolicyUnresolvableError` when none or several apply. Callers
        surface this as ``POLICY_UNRESOLVABLE`` / DENY (FR-072).
        """
        candidates = [p for p in self.policies if p.effective_from <= on]
        if not candidates:
            raise PolicyUnresolvableError(f"no catalog policy is effective on {on.isoformat()}")
        newest = max(p.effective_from for p in candidates)
        effective = [p for p in candidates if p.effective_from == newest]
        if len(effective) > 1:
            ids = sorted(f"{p.policy_id}@{p.policy_version}" for p in effective)
            raise PolicyUnresolvableError(
                f"{len(effective)} catalog policies are effective on {on.isoformat()}: {ids}; "
                "an ambiguous policy is never resolved by preference"
            )
        return effective[0]
