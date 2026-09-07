"""Completion-evidence tests for T015-T020 (governance and audit contracts)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, cast

import pytest
from pydantic import ValidationError

from semantic_catalog.contracts.access_tag import (
    AccessTagRegistry,
    PrincipalType,
    TagDenial,
)
from semantic_catalog.contracts.approval import (
    PendingVisibilityApprovals,
    VisibilityDenial,
)
from semantic_catalog.contracts.audit_event import (
    CatalogDecisionAuditEvent,
    ForbiddenAuditContentError,
)
from semantic_catalog.contracts.policy import (
    ApprovalResolutionError,
    CatalogPolicy,
    ChangeClass,
    PolicySet,
    PolicyUnresolvableError,
)
from semantic_catalog.contracts.reason_codes import (
    REASON_CODE_OUTCOME,
    Outcome,
    ReasonCode,
    codes_with_outcome,
    outcome_for,
)
from semantic_catalog.contracts.reason_message import (
    MissingReasonMessageError,
    ReasonMessage,
    ReasonMessageRegistry,
)

pytestmark = pytest.mark.unit


def _content(**extra: object) -> dict[str, object]:
    return {"lang": "pt-BR", **extra}


# --- T015 reason codes -------------------------------------------------------


def test_t015_forty_one_codes_declared() -> None:
    assert len(ReasonCode) == 41


def test_t015_every_outcome_class_is_inhabited() -> None:
    """A declared outcome that no code can express is a state nothing may emit.

    ALLOW was uninhabited until ``REQUEST_ALLOWED``, which made a clean allow
    impossible to record in a ``CatalogDecisionAuditEvent`` — the event requires
    a code and matches it against the outcome. Allowing something was literally
    unauditable.
    """
    for outcome in Outcome:
        assert codes_with_outcome(outcome), f"no code is classified {outcome.value}"


def test_t015_every_code_has_exactly_one_outcome() -> None:
    """T015 evidence: every code has an outcome and none is undetermined."""
    assert set(REASON_CODE_OUTCOME) == set(ReasonCode)
    for code in ReasonCode:
        assert isinstance(outcome_for(code), Outcome)


def test_t015_outcome_partition_is_complete() -> None:
    total = sum(len(codes_with_outcome(o)) for o in Outcome)
    assert total == len(ReasonCode)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (ReasonCode.SOURCE_STATE_PARTIAL, Outcome.DENY),
        (ReasonCode.SOURCE_LAGGING_WITHIN_TOLERANCE, Outcome.ALLOW_WITH_CAVEAT),
        (ReasonCode.COVERAGE_ENDS_BEFORE_PERIOD, Outcome.DENY),
        (ReasonCode.METRIC_PENDING, Outcome.DENY),
        (ReasonCode.POLICY_UNRESOLVABLE, Outcome.DENY),
        (ReasonCode.RELEASE_WITHDRAWN, Outcome.DENY),
        (ReasonCode.COMPARABILITY_RULE_MISSING, Outcome.DENY),
    ],
)
def test_t015_load_bearing_classifications(code: ReasonCode, expected: Outcome) -> None:
    """Partial denies while lagging-within-tolerance allows: FR-070."""
    assert outcome_for(code) is expected


# --- T016 policy -------------------------------------------------------------


def _policy(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "catalog_schema_version": 1,
        "kind": "catalog_policy",
        "policy_id": "catalog_core",
        "policy_version": 1,
        "effective_from": date(2026, 1, 1),
        "owner_role": "data_governance",
        "approval_roles": ("data_governance", "product_analytics"),
        "authorization": {
            "default": "deny",
            "require_access_tag": True,
            "unknown_tag_behaviour": "fail_closed",
            "self_approval_allowed": False,
        },
        "publication": {
            "require_complete_contract": True,
            "require_owner": True,
            "require_pt_br_content": True,
            "require_reason_message_for_publishable_codes": True,
        },
        "pending_visibility": {
            "exposable_fields": ("public_name", "expected_available_from"),
            "require_visibility_approval": True,
            "approval_expiry_behaviour": "omit_field",
        },
        "refusal": {
            "disclose_answerable_subset": True,
            "disclose_replacement_metric_id": True,
        },
    }
    return base | overrides


def test_t016_policy_validates() -> None:
    assert CatalogPolicy.model_validate(_policy()).policy_version == 1


def test_t016_authorization_default_cannot_be_allow() -> None:
    auth = cast(dict[str, Any], _policy()["authorization"]).copy()
    auth["default"] = "allow"
    with pytest.raises(ValidationError):
        CatalogPolicy.model_validate(_policy(authorization=auth))


def test_t016_exactly_one_effective_policy_resolves() -> None:
    policy_set = PolicySet.model_validate({"policies": (_policy(),)})
    assert policy_set.resolve_effective(date(2026, 6, 1)).policy_id == "catalog_core"


def test_t016_no_effective_policy_fails_closed() -> None:
    """T016 evidence: unresolvable policy raises rather than defaulting."""
    policy_set = PolicySet.model_validate({"policies": (_policy(),)})
    with pytest.raises(PolicyUnresolvableError, match="no catalog policy is effective"):
        policy_set.resolve_effective(date(2025, 12, 31))


def test_t016_ambiguous_policy_fails_closed() -> None:
    policy_set = PolicySet.model_validate(
        {
            "policies": (
                _policy(policy_id="catalog_core"),
                _policy(policy_id="catalog_other"),
            )
        }
    )
    with pytest.raises(PolicyUnresolvableError, match="are effective"):
        policy_set.resolve_effective(date(2026, 6, 1))


def test_t016_newest_effective_policy_wins_when_dates_differ() -> None:
    policy_set = PolicySet.model_validate(
        {
            "policies": (
                _policy(policy_version=1, effective_from=date(2026, 1, 1)),
                _policy(policy_version=2, effective_from=date(2026, 3, 1), supersedes_version=1),
            )
        }
    )
    assert policy_set.resolve_effective(date(2026, 6, 1)).policy_version == 2


def test_t016_cross_cutting_change_requires_every_owner_plus_governance() -> None:
    policy = CatalogPolicy.model_validate(_policy())
    approvers = policy.resolve_approvers(
        ChangeClass.CROSS_CUTTING,
        affected_owner_roles=("product_analytics", "data_platform"),
    )
    assert approvers == {"product_analytics", "data_platform", "data_governance"}


def test_t016_unresolvable_approvers_fail_closed_not_fallback() -> None:
    """Never falls back to the single-metric rule (ADR 0003)."""
    policy = CatalogPolicy.model_validate(_policy())
    with pytest.raises(ApprovalResolutionError):
        policy.resolve_approvers(ChangeClass.CROSS_CUTTING)
    with pytest.raises(ApprovalResolutionError):
        policy.resolve_approvers(ChangeClass.SINGLE_METRIC)


def test_t016_self_approval_refused_by_default() -> None:
    policy = CatalogPolicy.model_validate(_policy())
    assert policy.permits_self_approval("data_governance", frozenset({"data_governance"})) is False
    assert (
        policy.permits_self_approval("data_governance", frozenset({"data_governance", "other"}))
        is True
    )


def test_t016_self_approval_allowed_only_when_policy_grants_it() -> None:
    auth = cast(dict[str, Any], _policy()["authorization"]).copy()
    auth["self_approval_allowed"] = True
    policy = CatalogPolicy.model_validate(_policy(authorization=auth))
    assert policy.permits_self_approval("data_governance", frozenset({"data_governance"})) is True


# --- T017 access tags --------------------------------------------------------


def _registry(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "catalog_schema_version": 1,
        "kind": "access_tags",
        "tags": (
            {
                "id": "standard",
                "owner_role": "data_governance",
                "effective_from": date(2026, 1, 1),
                "allowed_principal_types": ("user", "service_principal"),
                "allowed_authorization_scopes": ("default",),
                "content": _content(label="Padrão", description="Métricas de produto."),
            },
            {
                "id": "legacy_internal",
                "owner_role": "data_governance",
                "effective_from": date(2026, 1, 1),
                "deprecated_from": date(2026, 7, 1),
                "replacement_tag": "standard",
                "allowed_principal_types": ("user",),
                "allowed_authorization_scopes": ("default",),
                "content": _content(label="Interno", description="Obsoleta."),
            },
        ),
    }
    return base | overrides


@pytest.mark.parametrize(
    ("tag", "principal", "scope", "expected"),
    [
        ("standard", PrincipalType.USER, "default", None),
        ("not_in_registry", PrincipalType.USER, "default", TagDenial.UNKNOWN),
        ("legacy_internal", PrincipalType.USER, "default", TagDenial.DEPRECATED),
        ("standard", PrincipalType.USER, "finance", TagDenial.SCOPE_MISMATCH),
        (
            "legacy_internal",
            PrincipalType.SERVICE_PRINCIPAL,
            "default",
            TagDenial.DEPRECATED,
        ),
    ],
)
def test_t017_deny_by_default_branches(
    tag: str, principal: PrincipalType, scope: str, expected: TagDenial | None
) -> None:
    """T017 evidence: unknown / expired / deprecated / scope mismatch fail closed."""
    registry = AccessTagRegistry.model_validate(_registry())
    assert (
        registry.authorize(
            tag, principal_type=principal, authorization_scope=scope, on=date(2026, 8, 1)
        )
        is expected
    )


def test_t017_deprecated_tag_denies_even_with_a_valid_replacement() -> None:
    registry = AccessTagRegistry.model_validate(_registry())
    denial = registry.authorize(
        "legacy_internal",
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        on=date(2026, 8, 1),
    )
    assert denial is TagDenial.DEPRECATED


def test_t017_tag_not_yet_effective_denies() -> None:
    registry = AccessTagRegistry.model_validate(_registry())
    assert (
        registry.authorize(
            "standard",
            principal_type=PrincipalType.USER,
            authorization_scope="default",
            on=date(2025, 6, 1),
        )
        is TagDenial.NOT_YET_EFFECTIVE
    )


def test_t017_dangling_replacement_rejected() -> None:
    tags = list(cast(tuple[dict[str, Any], ...], _registry()["tags"]))
    tags[1] = tags[1] | {"replacement_tag": "nonexistent"}
    with pytest.raises(ValidationError, match="not in the registry"):
        AccessTagRegistry.model_validate(_registry(tags=tuple(tags)))


# --- T018 reason messages ----------------------------------------------------


def _message(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "reason_code": "SOURCE_BEYOND_TOLERANCE",
        "version": 1,
        "effective_from": date(2026, 8, 1),
        "owner_role": "data_governance",
        "reviewed_by_role": "product_analytics",
        "interpolation_fields": ("source_id", "delay_tolerance"),
        "message": "A fonte {source_id} excedeu a tolerância de {delay_tolerance}.",
    }
    return base | overrides


def test_t018_message_renders_declared_fields() -> None:
    message = ReasonMessage.model_validate(_message())
    assert (
        message.render({"source_id": "google_play", "delay_tolerance": "P2D"})
        == "A fonte google_play excedeu a tolerância de P2D."
    )


def test_t018_interpolation_outside_the_allowlist_rejected() -> None:
    """T018 evidence: metric values and PII are not in the vocabulary at all."""
    with pytest.raises(ValidationError, match="outside the"):
        ReasonMessage.model_validate(
            _message(
                interpolation_fields=("metric_value",),
                message="Valor {metric_value}.",
            )
        )


def test_t018_undeclared_placeholder_rejected() -> None:
    with pytest.raises(ValidationError, match="undeclared"):
        ReasonMessage.model_validate(
            _message(interpolation_fields=(), message="A fonte {source_id} falhou.")
        )


def test_t018_render_without_a_value_raises_rather_than_leaking_a_placeholder() -> None:
    message = ReasonMessage.model_validate(_message())
    with pytest.raises(ValueError, match="missing interpolation values"):
        message.render({"source_id": "google_play"})


def test_t018_missing_canonical_message_raises_never_falls_back() -> None:
    registry = ReasonMessageRegistry.model_validate(
        {
            "catalog_schema_version": 1,
            "kind": "reason_messages",
            "lang": "pt-BR",
            "messages": (_message(),),
        }
    )
    assert registry.require(ReasonCode.SOURCE_BEYOND_TOLERANCE).version == 1
    with pytest.raises(MissingReasonMessageError, match="never translated at answer time"):
        registry.require(ReasonCode.METRIC_PENDING)


def test_t018_missing_codes_reports_the_build_blocking_set() -> None:
    registry = ReasonMessageRegistry.model_validate(
        {
            "catalog_schema_version": 1,
            "kind": "reason_messages",
            "lang": "pt-BR",
            "messages": (_message(),),
        }
    )
    publishable = frozenset({ReasonCode.SOURCE_BEYOND_TOLERANCE, ReasonCode.METRIC_PENDING})
    assert registry.missing_codes(publishable) == (ReasonCode.METRIC_PENDING,)


# --- T019 pending visibility approvals ---------------------------------------

_EXPOSABLE = ("public_name", "expected_available_from")


def _approvals(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "catalog_schema_version": 1,
        "kind": "pending_visibility_approvals",
        "approvals": (
            {
                "metric_id": "retention_rate_d7",
                "field_name": "public_name",
                "approval_status": "approved",
                "approved_by_role": "data_governance",
                "approved_at": date(2026, 8, 5),
                "source_commit": "4f9c2a1",
                "expires_at": date(2027, 8, 5),
            },
            {
                "metric_id": "retention_rate_d7",
                "field_name": "expected_available_from",
                "approval_status": "rejected",
                "approved_by_role": "data_governance",
                "approved_at": date(2026, 8, 5),
                "source_commit": "4f9c2a1",
            },
        ),
    }
    return base | overrides


def _evaluate(approvals: PendingVisibilityApprovals, field: str, **kw: object) -> object:
    defaults: dict[str, object] = {
        "current_commit": "4f9c2a1",
        "on": date(2026, 8, 11),
        "exposable_fields": _EXPOSABLE,
    }
    return approvals.evaluate("retention_rate_d7", field, **(defaults | kw))  # type: ignore[arg-type]


def test_t019_approved_field_is_exposed() -> None:
    approvals = PendingVisibilityApprovals.model_validate(_approvals())
    assert _evaluate(approvals, "public_name") is None


@pytest.mark.parametrize(
    ("field", "kwargs", "expected"),
    [
        ("expected_available_from", {}, VisibilityDenial.REJECTED),
        ("public_name", {"current_commit": "deadbee"}, VisibilityDenial.COMMIT_MISMATCH),
        ("public_name", {"on": date(2028, 1, 1)}, VisibilityDenial.EXPIRED),
        ("owner", {}, VisibilityDenial.FIELD_NOT_EXPOSABLE),
    ],
)
def test_t019_every_failure_omits_the_field(
    field: str, kwargs: dict[str, object], expected: VisibilityDenial
) -> None:
    """T019 evidence: missing/expired/rejected/commit-mismatch all resolve to omit."""
    approvals = PendingVisibilityApprovals.model_validate(_approvals())
    assert _evaluate(approvals, field, **kwargs) is expected


def test_t019_absent_approval_omits() -> None:
    approvals = PendingVisibilityApprovals.model_validate(_approvals(approvals=()))
    assert _evaluate(approvals, "public_name") is VisibilityDenial.NO_APPROVAL


def test_t019_self_approval_omits_unless_permitted() -> None:
    approvals = PendingVisibilityApprovals.model_validate(_approvals())
    assert (
        _evaluate(approvals, "public_name", proposer_role="data_governance")
        is VisibilityDenial.SELF_APPROVAL
    )
    assert (
        _evaluate(
            approvals,
            "public_name",
            proposer_role="data_governance",
            self_approval_allowed=True,
        )
        is None
    )


def test_t019_role_outside_the_permitted_set_omits() -> None:
    approvals = PendingVisibilityApprovals.model_validate(_approvals())
    assert (
        _evaluate(approvals, "public_name", permitted_roles=frozenset({"product_analytics"}))
        is VisibilityDenial.ROLE_NOT_PERMITTED
    )


def test_t019_duplicate_approval_for_one_field_rejected() -> None:
    entry = {
        "metric_id": "m",
        "field_name": "public_name",
        "approval_status": "approved",
        "approved_by_role": "data_governance",
        "approved_at": date(2026, 8, 5),
        "source_commit": "4f9c2a1",
    }
    with pytest.raises(ValidationError, match="two approvals"):
        PendingVisibilityApprovals.model_validate(_approvals(approvals=(entry, dict(entry))))


# --- T020 audit event contract -----------------------------------------------


def _event(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "correlation_id": "corr-0001",
        "occurred_at": datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
        "decision_id": "dec_4b81e0a7",
        "principal_id": "7f3c9a2e-opaque",
        "principal_type": "user",
        "requested_operation": "validate",
        "metric_ids": ("active_users",),
        "outcome": "DENY",
        "reason_code": "METRIC_PENDING",
        "policy_version": "3",
        "catalog_release_id": "cat_9f2a1c4e",
    }
    return base | overrides


def test_t020_valid_event_constructs() -> None:
    assert CatalogDecisionAuditEvent.model_validate(_event()).principal_id == "7f3c9a2e-opaque"


def test_t020_event_without_principal_id_fails_construction() -> None:
    """T020 evidence: an actorless audit event is a contract violation."""
    payload = _event()
    del payload["principal_id"]
    with pytest.raises(ValidationError):
        CatalogDecisionAuditEvent.model_validate(payload)


@pytest.mark.parametrize(
    "principal",
    [
        "person@example.com",
        "192.168.0.4",
        "AKIA" + "X" * 16,  # synthetic: matches the AWS key shape, is not a real or example key
        "gh" + "p_" + "y" * 30,  # synthetic: matches the token shape, is not a real token
    ],
)
def test_t020_denylist_is_enforced_by_the_model(principal: str) -> None:
    """T020 evidence: the denylist is enforced by the model, not by convention."""
    with pytest.raises(ValidationError) as excinfo:
        CatalogDecisionAuditEvent.model_validate(_event(principal_id=principal))
    message = str(excinfo.value)
    assert "principal_id contains a" in message
    assert "never direct PII, credentials or prompt text" in message


def test_t020_forbidden_content_type_is_a_value_error() -> None:
    assert issubclass(ForbiddenAuditContentError, ValueError)


def test_t020_outcome_must_match_the_reason_code_classification() -> None:
    with pytest.raises(ValidationError, match="unauditable"):
        CatalogDecisionAuditEvent.model_validate(_event(outcome="ALLOW"))


def test_t020_denial_event_still_carries_the_actor() -> None:
    """The access-refusal case is precisely what the actor reference exists for."""
    event = CatalogDecisionAuditEvent.model_validate(
        _event(reason_code="ACCESS_DENIED", outcome="DENY")
    )
    assert event.principal_id
    assert event.outcome is Outcome.DENY


def test_t020_no_prompt_text_field_exists() -> None:
    forbidden = {"question", "prompt", "query_text", "user_input", "email", "ip_address"}
    assert forbidden.isdisjoint(CatalogDecisionAuditEvent.model_fields)


def test_t020_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        CatalogDecisionAuditEvent.model_validate(_event(question="quantos usuários ativos?"))
