"""Completion-evidence tests for T112/T113 — D-1 candidate vs approved.

The failure this guards against is specific: a delay tolerance nobody signed off
being authored into a source file and then, because nothing can tell approved
from unapproved, driving a real ALLOW/DENY and being printed to a user inside a
refusal as though it were governed policy.

Every denial path is exercised, and each one asserts the two properties that
make the mechanism fail closed rather than merely fail: **no default is
substituted** and **the authored candidate is not modified**.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from semantic_catalog.contracts.freshness_approval import (
    FreshnessApproval,
    FreshnessApprovalRegistry,
    FreshnessDenial,
)
from semantic_catalog.contracts.metric import (
    AvailabilityStatus,
    Metric,
)
from semantic_catalog.contracts.source import Source
from semantic_catalog.validation.publication import (
    metric_eligibility,
    source_eligibility,
)

pytestmark = pytest.mark.unit

COMMIT = "4f9c2a1"
LATER = "b17e0c3"
TODAY = date(2026, 8, 11)


def _source(**overrides: object) -> Source:
    payload: dict[str, object] = {
        "catalog_schema_version": 1,
        "kind": "source",
        "id": "google_play",
        "type": "app_store",
        "product": "mobile_app",
        "platform": "android",
        "store": "google_play",
        "reporting_timezone": "America/Los_Angeles",
        "earliest_available_date": date(2023, 1, 1),
        "expected_refresh_interval": "P1D",
        "delay_tolerance": "P2D",
        "owner": "data_platform",
        "content": {"lang": "pt-BR", "label": "Google Play Store"},
    }
    payload.update(overrides)
    return Source.model_validate(payload)


def _approval(**overrides: object) -> FreshnessApproval:
    payload: dict[str, object] = {
        "source_id": "google_play",
        "approval_status": "approved",
        "expected_refresh_interval": "P1D",
        "delay_tolerance": "P2D",
        "reporting_time_zone": "America/Los_Angeles",
        "earliest_available_date": date(2023, 1, 1),
        "approved_by_role": "data_platform",
        "approved_at": date(2026, 8, 1),
        "source_commit": COMMIT,
    }
    payload.update(overrides)
    return FreshnessApproval.model_validate(payload)


def _registry(*approvals: FreshnessApproval) -> FreshnessApprovalRegistry:
    return FreshnessApprovalRegistry(
        catalog_schema_version=1,
        kind="freshness_approvals",
        approvals=approvals,
    )


def _resolve(
    registry: FreshnessApprovalRegistry,
    source: Source | None = None,
    *,
    on: date = TODAY,
    commit: str = COMMIT,
    permitted_roles: frozenset[str] | None = None,
) -> FreshnessDenial | None:
    return registry.evaluate(
        source or _source(),
        source_content_commit=commit,
        on=on,
        permitted_roles=permitted_roles,
    )


# --- the six denial paths -------------------------------------------------


def test_no_approval_makes_the_source_unpublishable() -> None:
    assert _resolve(_registry()) is FreshnessDenial.NO_APPROVAL


def test_rejected_approval_is_distinguishable_from_an_absent_one() -> None:
    """Both refuse, but a rejection is a decision and absence is a gap."""
    denial = _resolve(_registry(_approval(approval_status="rejected")))
    assert denial is FreshnessDenial.REJECTED
    assert denial is not FreshnessDenial.NO_APPROVAL


def test_expired_approval_carries_nothing_forward() -> None:
    registry = _registry(_approval(expires_at=date(2026, 8, 10)))
    assert _resolve(registry, on=date(2026, 8, 10)) is None
    assert _resolve(registry, on=date(2026, 8, 11)) is FreshnessDenial.EXPIRED


def test_role_not_permitted_by_the_policy_does_not_approve() -> None:
    denial = _resolve(
        _registry(_approval(approved_by_role="product_analytics")),
        permitted_roles=frozenset({"data_platform", "data_governance"}),
    )
    assert denial is FreshnessDenial.ROLE_NOT_PERMITTED


def test_commit_mismatch_refuses_until_re_approved() -> None:
    assert _resolve(_registry(_approval()), commit=LATER) is FreshnessDenial.COMMIT_MISMATCH


def test_editing_an_approved_candidate_invalidates_the_approval() -> None:
    """The whole point: a stale approval must not cover a new value."""
    registry = _registry(_approval())
    assert _resolve(registry) is None
    edited = _source(delay_tolerance="P5D")
    assert _resolve(registry, edited) is FreshnessDenial.CANDIDATE_CHANGED


@pytest.mark.parametrize(
    "field, value",
    [
        ("expected_refresh_interval", "PT12H"),
        ("delay_tolerance", "P9D"),
        ("reporting_timezone", "America/Sao_Paulo"),
        ("earliest_available_date", date(2024, 5, 5)),
    ],
)
def test_every_decision_bearing_field_is_covered_by_the_match(field: str, value: object) -> None:
    registry = _registry(_approval())
    assert _resolve(registry, _source(**{field: value})) is FreshnessDenial.CANDIDATE_CHANGED


# --- the approved path ----------------------------------------------------


def test_a_resolving_approval_makes_the_source_publishable() -> None:
    eligibility = source_eligibility(
        _source(),
        _registry(_approval()),
        source_content_commit=COMMIT,
        on=TODAY,
    )
    assert eligibility.publishable
    assert eligibility.denial is None
    assert eligibility.may_participate_in_decisions
    assert eligibility.may_disclose_delay_tolerance


# --- no default, no mutation ---------------------------------------------


@pytest.mark.parametrize(
    "registry_factory, kwargs",
    [
        (lambda: _registry(), {}),
        (lambda: _registry(_approval(approval_status="rejected")), {}),
        (lambda: _registry(_approval(expires_at=date(2026, 8, 1))), {}),
        (lambda: _registry(_approval()), {"commit": LATER}),
    ],
)
def test_no_denial_path_substitutes_a_default_or_edits_the_candidate(
    registry_factory: object, kwargs: dict[str, str]
) -> None:
    source = _source()
    before = source.model_dump()
    registry = registry_factory()  # type: ignore[operator]
    denial = _resolve(registry, source, **kwargs)  # type: ignore[arg-type]

    assert denial is not None
    assert source.model_dump() == before, "resolution must never modify the authored candidate"
    assert source.delay_tolerance == timedelta(days=2), "no default is ever substituted"


def test_an_unapproved_source_may_not_disclose_its_delay_tolerance() -> None:
    """FR-076: an unapproved figure quoted in a refusal reads as governed policy."""
    eligibility = source_eligibility(_source(), _registry(), source_content_commit=COMMIT, on=TODAY)
    assert not eligibility.may_disclose_delay_tolerance
    assert not eligibility.may_participate_in_decisions


# --- fingerprint baseline timing -----------------------------------------


def test_first_approval_establishes_baseline_not_a_semantic_change() -> None:
    """FR-077: an unapproved source has no baseline to change."""
    source = _source()
    before = source_eligibility(source, _registry(), source_content_commit=COMMIT, on=TODAY)
    assert not before.contributes_to_fingerprint

    after = source_eligibility(
        source, _registry(_approval()), source_content_commit=COMMIT, on=TODAY
    )
    assert after.contributes_to_fingerprint


# --- metric consequence ---------------------------------------------------


def _metric(*availability: tuple[str, str]) -> Metric:
    return Metric.model_validate(
        {
            "catalog_schema_version": 1,
            "kind": "metric",
            "name": "downloads",
            "owner": "product_analytics",
            "access": "standard",
            "grain_family": "day",
            "versions": [
                {
                    "version": 1,
                    "effective_from": date(2026, 8, 11),
                    "source_view": "semantic.store_daily_metrics",
                    "grain": "date x store",
                    "aggregation": "sum",
                    "additivity": "additive",
                    "unit": "events",
                    "time_dimension": "date",
                    "calculation_basis": "Downloads relatados pela loja no dia.",
                    "allowed_dimensions": ["store"],
                    "content": {
                        "lang": "pt-BR",
                        "label": "Downloads",
                        "description": "Downloads relatados pelas lojas.",
                    },
                }
            ],
            "source_availability": [
                {
                    "source": source,
                    "status": status,
                    "effective_from": date(2026, 8, 11),
                    **(
                        {"available_from": date(2023, 1, 1)}
                        if status == AvailabilityStatus.AVAILABLE
                        else {"reason_code": "IDENTITY_RULE_UNSATISFIABLE"}
                    ),
                }
                for source, status in availability
            ],
        }
    )


def test_a_metric_reading_an_unapproved_source_is_unpublishable() -> None:
    result = metric_eligibility(_metric(("google_play", "available")), frozenset())
    assert not result.publishable
    assert result.unapproved_sources == ("google_play",)


def test_a_source_the_metric_declares_unavailable_does_not_block_it() -> None:
    """An `unavailable` declaration is a governance decision, not a dependency."""
    metric = _metric(("google_play", "available"), ("website", "unavailable"))
    result = metric_eligibility(metric, frozenset({"google_play"}))
    assert result.publishable
    assert result.unapproved_sources == ()


def test_a_metric_with_no_available_source_is_unpublishable() -> None:
    result = metric_eligibility(_metric(("website", "unavailable")), frozenset({"google_play"}))
    assert not result.publishable


# --- registry integrity ---------------------------------------------------


def test_two_approvals_for_one_source_are_refused() -> None:
    with pytest.raises(ValidationError, match="two freshness approvals"):
        _registry(_approval(), _approval(source_commit=LATER))


def test_expiry_before_approval_is_refused() -> None:
    with pytest.raises(ValidationError, match="expires"):
        _approval(approved_at=date(2026, 8, 10), expires_at=date(2026, 8, 1))


def test_an_unknown_time_zone_is_refused() -> None:
    with pytest.raises(ValidationError, match="not a known IANA time zone"):
        _approval(reporting_time_zone="UTC-3")


def test_the_registry_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        FreshnessApprovalRegistry.model_validate(
            {
                "catalog_schema_version": 1,
                "kind": "freshness_approvals",
                "approvals": [],
                "signed_off": True,
            }
        )
