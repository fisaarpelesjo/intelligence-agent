"""Approval fail-closed tests — T048 (FR-058, FR-059, FR-060).

Every path through :func:`resolve_visibility` that is not a resolving approval
must **omit the field**, and omission must be literal: no key, no ``null``, no
placeholder, no inferred value. A ``null`` still tells a reader the field exists
and is empty, which is a claim nobody approved.

Fixtures are isolated and deterministic, and they are **not production
approvals**. The governed seed in ``semantic/governance/`` is validated by
``tests/integration/test_authored_catalog_is_fail_closed.py``; nothing here
grants anything in the real catalog.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from semantic_catalog.contracts.approval import PendingVisibilityApprovals, VisibilityDenial
from semantic_catalog.contracts.policy import CatalogPolicy
from semantic_catalog.loader.visibility import VisibilityResolution, resolve_visibility

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "approvals"

METRIC = "fixture_metric"
COMMIT = "fixture0"
ON = date(2026, 8, 11)

POLICY = """\
catalog_schema_version: 1
kind: catalog_policy
policy_id: fixture_policy
policy_version: 1
effective_from: 2026-08-11
owner_role: data_governance
approval_roles: [data_governance, product_analytics]
authorization:
  default: deny
  require_access_tag: true
  unknown_tag_behaviour: fail_closed
  self_approval_allowed: {self_approval}
publication:
  require_complete_contract: true
  require_owner: true
  require_pt_br_content: true
  require_reason_message_for_publishable_codes: true
pending_visibility:
  exposable_fields: [public_name, expected_available_from]
  require_visibility_approval: true
  approval_expiry_behaviour: omit_field
refusal:
  disclose_answerable_subset: true
  disclose_replacement_metric_id: true
"""


def _policy(*, self_approval: bool = False) -> CatalogPolicy:
    payload = yaml.safe_load(POLICY.format(self_approval=str(self_approval).lower()))
    return CatalogPolicy.model_validate(payload)


def _approvals(fixture: str) -> PendingVisibilityApprovals:
    payload = yaml.safe_load((FIXTURES / fixture).read_text(encoding="utf-8"))
    return PendingVisibilityApprovals.model_validate(payload)


def _resolve(
    fixture: str,
    *,
    self_approval: bool = False,
    proposer_role: str | None = None,
    on: date = ON,
    commit: str = COMMIT,
) -> VisibilityResolution:
    return resolve_visibility(
        METRIC,
        policy=_policy(self_approval=self_approval),
        approvals=_approvals(fixture),
        current_commit=commit,
        on=on,
        proposer_role=proposer_role,
    )


# --- every failure omits ---------------------------------------------------


@pytest.mark.parametrize(
    "fixture, expected, kwargs",
    [
        ("none.yaml", VisibilityDenial.NO_APPROVAL, {}),
        ("rejected.yaml", VisibilityDenial.REJECTED, {}),
        ("expired.yaml", VisibilityDenial.EXPIRED, {}),
        ("commit-mismatch.yaml", VisibilityDenial.COMMIT_MISMATCH, {}),
        ("role-not-permitted.yaml", VisibilityDenial.ROLE_NOT_PERMITTED, {}),
        (
            "self-approved.yaml",
            VisibilityDenial.SELF_APPROVAL,
            {"proposer_role": "product_analytics"},
        ),
    ],
)
def test_every_failure_omits_the_field(
    fixture: str, expected: VisibilityDenial, kwargs: dict[str, str]
) -> None:
    resolution = _resolve(fixture, **kwargs)  # type: ignore[arg-type]
    assert not resolution.exposes("public_name")
    assert resolution.denial_for("public_name") is expected


def test_rejected_is_distinguishable_from_absent() -> None:
    """Both omit, but a rejection is a decision and absence is a gap."""
    assert _resolve("rejected.yaml").denial_for("public_name") is VisibilityDenial.REJECTED
    assert _resolve("none.yaml").denial_for("public_name") is VisibilityDenial.NO_APPROVAL


def test_an_absent_approvals_file_denies_everything() -> None:
    """Not "nothing to check" — "nothing is approved"."""
    resolution = resolve_visibility(
        METRIC,
        policy=_policy(),
        approvals=None,
        current_commit=COMMIT,
        on=ON,
    )
    assert not resolution.exposes("public_name")
    assert not resolution.exposes("expected_available_from")
    assert resolution.denial_for("public_name") is VisibilityDenial.NO_APPROVAL


# --- the approved path -----------------------------------------------------


def test_a_resolving_approval_exposes_only_the_approved_field() -> None:
    """Approval is per metric per field: `public_name` says nothing about the date."""
    resolution = _resolve("approved.yaml")
    assert resolution.exposes("public_name")
    assert not resolution.exposes("expected_available_from")
    assert resolution.denial_for("expected_available_from") is VisibilityDenial.NO_APPROVAL


def test_expiry_boundary_is_inclusive_of_the_expiry_date() -> None:
    assert _resolve("expired.yaml", on=date(2026, 8, 10)).exposes("public_name")
    assert not _resolve("expired.yaml", on=date(2026, 8, 11)).exposes("public_name")


# --- policy drives self-approval, not code ---------------------------------


def test_self_approval_permission_comes_from_the_governed_policy() -> None:
    """No invented semantics: flipping the policy flips the outcome."""
    refused = _resolve("self-approved.yaml", proposer_role="product_analytics")
    permitted = _resolve(
        "self-approved.yaml", proposer_role="product_analytics", self_approval=True
    )
    assert not refused.exposes("public_name")
    assert permitted.exposes("public_name")


def test_a_different_proposer_is_not_self_approval() -> None:
    assert _resolve("self-approved.yaml", proposer_role="data_governance").exposes("public_name")


# --- fields the policy does not declare exposable --------------------------


def test_a_field_outside_the_policy_allowlist_is_never_exposed() -> None:
    resolution = _resolve("approved.yaml")
    assert not resolution.exposes("calculation_basis")
    assert resolution.denial_for("calculation_basis") is VisibilityDenial.FIELD_NOT_EXPOSABLE


# --- no default is ever substituted ----------------------------------------


@pytest.mark.parametrize(
    "fixture", ["none.yaml", "rejected.yaml", "expired.yaml", "commit-mismatch.yaml"]
)
def test_no_failure_path_substitutes_a_value(fixture: str) -> None:
    """FR-060: omitted, never defaulted, placeholdered or inferred."""
    from semantic_catalog.contracts.metric import Lifecycle, Metric
    from semantic_catalog.loader.lifecycle import LifecycleState, PendingReason
    from semantic_catalog.loader.projection import PendingCandidates, project_pending

    metric = Metric.model_validate(
        {
            "catalog_schema_version": 1,
            "kind": "metric",
            "name": METRIC,
            "owner": "product_analytics",
            "access": "standard",
            "grain_family": "day",
            "versions": [
                {
                    "version": 1,
                    "effective_from": date(2026, 8, 11),
                    "source_view": "semantic.fixture",
                    "grain": "date",
                    "aggregation": "sum",
                    "additivity": "additive",
                    "unit": "events",
                    "time_dimension": "date",
                    "calculation_basis": "Base de cálculo do fixture.",
                    "content": {
                        "lang": "pt-BR",
                        "label": "Rótulo do fixture",
                        "description": "Descrição do fixture.",
                    },
                }
            ],
        }
    )
    state = LifecycleState(
        metric_id=METRIC,
        lifecycle=Lifecycle.PENDING,
        missing_fields=(),
        reasons=(PendingReason.SOURCE_NOT_APPROVED,),
        unapproved_sources=(),
    )
    stub = project_pending(
        metric,
        state,
        visibility=_resolve(fixture),
        candidates=PendingCandidates(
            public_name="Rótulo do fixture", expected_available_from=date(2027, 1, 1)
        ),
    )
    payload = stub.to_public_dict()
    assert stub.public_name is None
    assert stub.expected_available_from is None
    assert "public_name" not in payload, "omission must be literal, not a null key"
    assert "expected_available_from" not in payload
    assert "Rótulo do fixture" not in str(payload)


def test_an_approved_candidate_is_emitted_verbatim() -> None:
    """The gate withholds; it never rewrites what it lets through."""
    from semantic_catalog.contracts.metric import Lifecycle, Metric
    from semantic_catalog.loader.lifecycle import LifecycleState, PendingReason
    from semantic_catalog.loader.projection import PendingCandidates, project_pending

    metric = Metric.model_validate(
        {
            "catalog_schema_version": 1,
            "kind": "metric",
            "name": METRIC,
            "owner": "product_analytics",
            "access": "standard",
            "grain_family": "day",
            "versions": [
                {
                    "version": 1,
                    "effective_from": date(2026, 8, 11),
                    "source_view": "semantic.fixture",
                    "grain": "date",
                    "aggregation": "sum",
                    "additivity": "additive",
                    "unit": "events",
                    "time_dimension": "date",
                    "calculation_basis": "Base de cálculo do fixture.",
                    "content": {
                        "lang": "pt-BR",
                        "label": "Rótulo do fixture",
                        "description": "Descrição do fixture.",
                    },
                }
            ],
        }
    )
    stub = project_pending(
        metric,
        LifecycleState(METRIC, Lifecycle.PENDING, (), (PendingReason.SOURCE_NOT_APPROVED,), ()),
        visibility=_resolve("approved.yaml"),
        candidates=PendingCandidates(public_name="Rótulo do fixture"),
    )
    assert stub.public_name == "Rótulo do fixture"
    assert stub.to_public_dict()["public_name"] == "Rótulo do fixture"
    assert "expected_available_from" not in stub.to_public_dict()
