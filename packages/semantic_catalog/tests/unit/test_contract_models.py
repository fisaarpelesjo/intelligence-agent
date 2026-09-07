"""Completion-evidence tests for T009-T014 (domain contract models).

Each test names the task and the evidence clause it discharges.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from semantic_catalog.contracts.comparability import ComparabilityRule, Relation
from semantic_catalog.contracts.dimension import Dimension
from semantic_catalog.contracts.glossary import GlossaryTerm
from semantic_catalog.contracts.metric import Metric
from semantic_catalog.contracts.owner import Owner, OwnerKind, OwnerRegistry
from semantic_catalog.contracts.retention import RetentionContract
from semantic_catalog.contracts.source import Source

pytestmark = pytest.mark.unit


def _content(**extra: object) -> dict[str, object]:
    return {"lang": "pt-BR", **extra}


def _metric_version(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "version": 1,
        "effective_from": date(2024, 1, 1),
        "effective_to": None,
        "source_view": "semantic.product_daily_metrics",
        "grain": "date x product x platform",
        "aggregation": "count_distinct",
        "additivity": "non_additive",
        "unit": "users",
        "time_dimension": "date",
        "calculation_basis": "Usuários distintos com pelo menos um evento no dia.",
        "exclusions": ("Não é somável entre dias.",),
        "allowed_dimensions": ("product", "platform"),
        "content": _content(
            label="Usuários ativos",
            description="Usuários distintos que usaram o produto no dia.",
        ),
    }
    return base | overrides


def _metric(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "catalog_schema_version": 1,
        "kind": "metric",
        "name": "active_users",
        "owner": "product_analytics",
        "access": "standard",
        "grain_family": "day",
        "versions": (_metric_version(),),
    }
    return base | overrides


def _source(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
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
        "content": _content(label="Google Play Store"),
    }
    return base | overrides


# --- T009 metric models ------------------------------------------------------


def test_t009_complete_metric_validates() -> None:
    assert Metric.model_validate(_metric()).name == "active_users"


@pytest.mark.parametrize(
    "field",
    ["name", "owner", "access", "grain_family", "versions"],
)
def test_t009_missing_required_field_fails(field: str) -> None:
    """T009 evidence: a metric missing any required field fails construction."""
    payload = _metric()
    del payload[field]
    with pytest.raises(ValidationError):
        Metric.model_validate(payload)


def test_t009_unknown_field_is_rejected_fail_closed() -> None:
    with pytest.raises(ValidationError):
        Metric.model_validate(_metric(unexpected_key="x"))


def test_t009_no_type_coercion_under_strict_mode() -> None:
    """A quoted version number is an authoring error, not an integer."""
    with pytest.raises(ValidationError):
        Metric.model_validate(_metric(versions=(_metric_version(version="1"),)))


def test_t009_overlapping_versions_rejected() -> None:
    versions = (
        _metric_version(version=1, effective_from=date(2024, 1, 1), effective_to=date(2024, 6, 30)),
        _metric_version(version=2, effective_from=date(2024, 6, 1)),
    )
    with pytest.raises(ValidationError, match="overlap"):
        Metric.model_validate(_metric(versions=versions))


def test_t009_duplicate_version_numbers_rejected() -> None:
    versions = (
        _metric_version(version=1, effective_from=date(2024, 1, 1), effective_to=date(2024, 6, 30)),
        _metric_version(version=1, effective_from=date(2024, 7, 1)),
    )
    with pytest.raises(ValidationError, match="duplicate version"):
        Metric.model_validate(_metric(versions=versions))


def test_t009_ratio_without_denominator_rejected() -> None:
    with pytest.raises(ValidationError, match="numerator and denominator"):
        Metric.model_validate(
            _metric(versions=(_metric_version(aggregation="ratio", unit="rate"),))
        )


def test_t009_unavailable_source_needs_a_reason_code() -> None:
    availability = (
        {"source": "website", "status": "unavailable", "effective_from": date(2024, 1, 1)},
    )
    with pytest.raises(ValidationError, match="reason_code"):
        Metric.model_validate(_metric(source_availability=availability))


def test_t009_frozen_after_construction() -> None:
    metric = Metric.model_validate(_metric())
    with pytest.raises(ValidationError):
        metric.name = "other"  # type: ignore[misc]


# --- T010 source models ------------------------------------------------------


def test_t010_source_without_delay_tolerance_fails() -> None:
    """T010 evidence: a source without delay_tolerance fails — no global default."""
    payload = _source()
    del payload["delay_tolerance"]
    with pytest.raises(ValidationError):
        Source.model_validate(payload)


def test_t010_iso_duration_parsed() -> None:
    assert Source.model_validate(_source()).delay_tolerance == timedelta(days=2)


def test_t010_month_duration_rejected_as_ambiguous() -> None:
    with pytest.raises(ValidationError, match="days or smaller"):
        Source.model_validate(_source(delay_tolerance="P1M"))


def test_t010_fixed_offset_is_not_a_timezone() -> None:
    with pytest.raises(ValidationError, match="IANA"):
        Source.model_validate(_source(reporting_timezone="-03:00"))


def test_t010_native_zone_preserved_verbatim() -> None:
    assert Source.model_validate(_source()).reporting_timezone == "America/Los_Angeles"


def test_t010_telemetry_source_must_not_declare_a_store() -> None:
    with pytest.raises(ValidationError, match="must not declare a store"):
        Source.model_validate(
            _source(id="android_app", type="product_telemetry", store="google_play")
        )


# --- T011 dimension models ---------------------------------------------------


def _dimension(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "catalog_schema_version": 1,
        "kind": "dimension",
        "id": "app_version",
        "owner": "product_analytics",
        "permitted_values": "open",
        "content": _content(
            label="Versão do aplicativo",
            description="Versão instalada no dispositivo no momento do evento.",
        ),
        "source_applicability": ({"source": "android_app", "available_from": date(2023, 1, 1)},),
    }
    return base | overrides


def test_t011_dimension_without_ptbr_content_fails() -> None:
    payload = _dimension()
    del payload["content"]
    with pytest.raises(ValidationError):
        Dimension.model_validate(payload)


def test_t011_missing_lang_marker_fails() -> None:
    with pytest.raises(ValidationError):
        Dimension.model_validate(_dimension(content={"label": "x", "description": "y"}))


def test_t011_absence_from_applicability_means_not_applicable() -> None:
    """FR-010: website is absent, so app_version does not apply to it."""
    dimension = Dimension.model_validate(_dimension())
    assert dimension.applies_to("android_app") is True
    assert dimension.applies_to("website") is False


# --- T012 comparability and glossary -----------------------------------------


def _rule(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "catalog_schema_version": 1,
        "kind": "comparability",
        "id": "downloads_vs_installs",
        "subject": "metric_pair",
        "left": "downloads",
        "right": "installs",
        "relation": "not_comparable",
        "content": _content(reason="Contam eventos diferentes."),
    }
    return base | overrides


def test_t012_non_permissive_relation_needs_a_reason() -> None:
    """T012 evidence: a non-permissive relation without a pt-BR reason fails."""
    with pytest.raises(ValidationError, match="must state a pt-BR reason"):
        ComparabilityRule.model_validate(_rule(content=_content()))


def test_t012_caveated_relation_needs_a_caveat() -> None:
    with pytest.raises(ValidationError, match="must state the caveat"):
        ComparabilityRule.model_validate(
            _rule(relation="comparable_with_caveat", content=_content(reason="Aproximado."))
        )


def test_t012_combinable_rule_validates() -> None:
    rule = ComparabilityRule.model_validate(_rule(relation="combinable", content=_content()))
    assert rule.relation is Relation.COMBINABLE


def test_t012_rule_cannot_relate_a_metric_to_itself() -> None:
    with pytest.raises(ValidationError, match="to itself"):
        ComparabilityRule.model_validate(_rule(right="downloads"))


def test_t012_glossary_term_validates() -> None:
    term = GlossaryTerm.model_validate(
        {
            "catalog_schema_version": 1,
            "kind": "glossary",
            "id": "eligible_event",
            "owner": "product_analytics",
            "content": _content(term="Evento elegível", definition="Ação que qualifica a coorte."),
        }
    )
    assert term.id == "eligible_event"


# --- T013 retention contract -------------------------------------------------


def _retention(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "window_days": 7,
        "retention_style": "exact_day",
        "cohort_assignment": "first_eligible_activity",
        "numerator": "Membros da coorte que retornam no dia 7.",
        "denominator": "População elegível original da coorte.",
        "min_maturity_days": 7,
    }
    return base | overrides


def test_t013_unset_fields_are_reported_by_name_never_defaulted() -> None:
    """T013 evidence: a null marks the metric incomplete and never defaults."""
    contract = RetentionContract.model_validate(_retention())
    assert contract.cohort_timezone is None
    assert contract.eligible_event is None
    assert contract.identity_rule is None
    assert contract.unset_required_fields() == (
        "cohort_timezone",
        "eligible_event",
        "identity_rule",
    )
    assert contract.is_publishable is False


def test_t013_publishable_only_when_all_externally_authored_fields_are_set() -> None:
    contract = RetentionContract.model_validate(
        _retention(
            cohort_timezone="America/Sao_Paulo",
            eligible_event="Sessão iniciada.",
            identity_rule="Identificador de instalação.",
        )
    )
    assert contract.unset_required_fields() == ()
    assert contract.is_publishable is True


def test_t013_maturity_shorter_than_window_rejected() -> None:
    with pytest.raises(ValidationError, match="shorter than the D7 window"):
        RetentionContract.model_validate(_retention(min_maturity_days=3))


def test_t013_rolling_retention_is_not_expressible() -> None:
    with pytest.raises(ValidationError):
        RetentionContract.model_validate(_retention(retention_style="rolling"))


def test_t013_unsupported_window_rejected() -> None:
    with pytest.raises(ValidationError):
        RetentionContract.model_validate(_retention(window_days=14, min_maturity_days=14))


def test_t013_cohort_metric_reports_unset_fields_through_the_metric() -> None:
    metric = Metric.model_validate(
        _metric(
            name="retention_rate_d7",
            grain_family="cohort",
            retention=_retention(),
            versions=(
                _metric_version(
                    aggregation="ratio",
                    additivity="ratio",
                    unit="rate",
                    time_dimension="cohort_date",
                    numerator="Retornos no dia 7.",
                    denominator="Coorte elegível.",
                ),
            ),
        )
    )
    assert metric.unset_required_fields() == (
        "retention.cohort_timezone",
        "retention.eligible_event",
        "retention.identity_rule",
    )


def test_t013_day_grained_metric_must_not_declare_retention() -> None:
    with pytest.raises(ValidationError, match="must not declare a retention contract"):
        Metric.model_validate(_metric(retention=_retention()))


# --- T014 owner registry -----------------------------------------------------


def test_t014_owner_registry_validates_and_resolves() -> None:
    registry = OwnerRegistry.model_validate(
        {
            "catalog_schema_version": 1,
            "kind": "owners",
            "owners": (
                {
                    "id": "product_analytics",
                    "name": "Product Analytics",
                    "kind": "team",
                    "review_group": "@org/product-analytics",
                },
            ),
        }
    )
    owner = registry.resolve("product_analytics")
    assert owner is not None
    assert owner.kind is OwnerKind.TEAM
    assert registry.resolve("nobody") is None


def test_t014_entry_naming_an_individual_fails() -> None:
    """T014 evidence: an entry naming an individual fails validation."""
    with pytest.raises(ValidationError, match="never individuals"):
        Owner.model_validate(
            {
                "id": "someone",
                "name": "person@example.com",
                "kind": "team",
                "review_group": "@org/team",
            }
        )


def test_t014_person_kind_is_not_expressible() -> None:
    with pytest.raises(ValidationError):
        Owner.model_validate({"id": "x", "name": "X", "kind": "person", "review_group": "@org/x"})


def test_t014_duplicate_owner_ids_rejected() -> None:
    entry = {
        "id": "product_analytics",
        "name": "Product Analytics",
        "kind": "team",
        "review_group": "@org/pa",
    }
    with pytest.raises(ValidationError, match="duplicate owner id"):
        OwnerRegistry.model_validate(
            {"catalog_schema_version": 1, "kind": "owners", "owners": (entry, dict(entry))}
        )
