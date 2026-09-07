"""Baseline deviation check — T111 (BD-1 … BD-5).

`research.md § Baseline deviations` recorded five statements in
`docs/intelligence-agent.yaml` that the approved architecture had overtaken. Two
of them changed a governance rule's shape and got ADRs; all five needed the YAML
corrected, because **an ADR is not used to leave an obsolete statement
standing** — the ADR records why, the edit stops the conflict resurfacing in
every future feature.

This is the deviation check T111's evidence names. A clean run means the
baseline no longer conflicts with the constitution, the spec, the ADRs or the
implemented behaviour on any of the five points.

It asserts the **corrected** state, not the correction event, so it keeps
working as a regression guard: if somebody reverts `tenant_isolation` to `true`
or drops `calculation_basis`, this fails rather than the conflict quietly
returning.

Two things it deliberately does not do. It does not check the whole baseline —
unrelated architecture is out of scope for T111 and out of scope here. And it
does not treat the baseline as authoritative over anything: where the two
disagree, the higher artifact governs and the YAML is what gets fixed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.contract

REPO = Path(__file__).resolve().parents[4]
BASELINE = REPO / "docs" / "intelligence-agent.yaml"
SPEC = REPO / "specs" / "001-semantic-catalog" / "spec.md"
RESEARCH = REPO / "specs" / "001-semantic-catalog" / "research.md"
ADR = REPO / "docs" / "adr"

#: The eight cohort fields ADR 0002 enumerates. Retention metrics carry them as
#: a conditional requirement, not as universal fields.
COHORT_FIELDS = frozenset(
    {
        "window_days",
        "retention_style",
        "cohort_timezone",
        "eligible_event",
        "identity_rule",
        "numerator",
        "denominator",
        "min_maturity_days",
    }
)

#: The constitution's enumeration. A floor, never a ceiling (ADR 0002).
CONSTITUTION_FIELDS = (
    "name",
    "label",
    "description",
    "source_view",
    "grain",
    "aggregation",
    "unit",
    "time_dimension",
    "allowed_dimensions",
    "source_availability",
    "owner",
    "version",
    "limitations",
)


@pytest.fixture(scope="module")
def baseline() -> dict[str, Any]:
    return yaml.safe_load(BASELINE.read_text(encoding="utf-8"))


def test_the_baseline_is_valid_yaml(baseline: dict[str, Any]) -> None:
    assert isinstance(baseline, dict)
    assert baseline["project"]["name"] == "intelligence-agent"


# --- BD-1 -------------------------------------------------------------------


def test_bd1_lowest_common_coverage_is_scoped_to_cross_source(baseline: dict[str, Any]) -> None:
    """Constitution III and FR-023: a single-source request is never narrowed."""
    assert baseline["data_freshness"]["rules"]["use_lowest_common_coverage"] == "cross_source_only"


def test_bd1_has_its_adr() -> None:
    # Flattened: the sentence wraps mid-phrase, and a literal substring check
    # would pass or fail on where the wrap landed.
    adr = " ".join(
        (ADR / "0001-lowest-common-coverage-scoped-to-cross-source.md")
        .read_text(encoding="utf-8")
        .split()
    )
    assert "**Status**: Accepted" in adr
    assert "cross-source requests only" in adr
    assert "does not license leaving the baseline statement obsolete" in adr


def test_bd1_matches_the_implemented_gate() -> None:
    """The baseline now says what Gate 7 does."""
    gate = (
        REPO / "packages/semantic_catalog/src/semantic_catalog/validation/gates/coverage.py"
    ).read_text(encoding="utf-8")
    assert "cross-source requests only" in gate.lower() or "cross_source" in gate.lower()
    assert "ADR 0001" in gate or "BD-1" in gate


# --- BD-2 -------------------------------------------------------------------


def test_bd2_three_retention_metrics_replace_the_single_one(baseline: dict[str, Any]) -> None:
    """FR-044 and A-16: further windows are new metrics, not parameters."""
    metrics = baseline["semantic_layer"]["initial_metrics"]
    assert "retention_rate" not in metrics
    assert {"retention_rate_d1", "retention_rate_d7", "retention_rate_d30"} <= set(metrics)


def test_bd2_matches_the_authored_catalog(baseline: dict[str, Any]) -> None:
    """The baseline names metrics the catalog actually governs."""
    metrics = set(baseline["semantic_layer"]["initial_metrics"])
    authored = {p.stem for p in (REPO / "semantic" / "metrics").glob("*.yaml")}
    assert metrics <= authored, sorted(metrics - authored)


# --- BD-3 -------------------------------------------------------------------


def test_bd3_required_fields_are_a_superset_of_the_constitution(baseline: dict[str, Any]) -> None:
    """ADR 0002: strictly additive. Nothing constitutional is dropped."""
    required = baseline["semantic_layer"]["metric_contract"]["required_fields"]
    missing = [f for f in CONSTITUTION_FIELDS if f not in required]
    assert not missing, f"constitutional fields dropped: {missing}"
    assert {"additivity", "exclusions", "calculation_basis"} <= set(required)


def test_bd3_cohort_fields_are_gated_not_universal(baseline: dict[str, Any]) -> None:
    contract = baseline["semantic_layer"]["metric_contract"]
    cohort = contract["cohort_required_fields"]
    assert cohort["applies_when"] == "grain_family == cohort"
    assert set(cohort["fields"]) == COHORT_FIELDS
    # Universal and conditional stay separate: a day-grained metric must not
    # inherit a cohort requirement.
    assert not COHORT_FIELDS & set(contract["required_fields"])


def test_bd3_status_is_recorded_as_derived(baseline: dict[str, Any]) -> None:
    """Lifecycle is derived, never authored (data-model §5), so it cannot sit in
    a list of required *authored* fields."""
    assert baseline["semantic_layer"]["metric_contract"]["derived_fields"] == ["status"]


def test_bd3_matches_the_implemented_contract(baseline: dict[str, Any]) -> None:
    """Every field the baseline now requires exists on the models."""
    from semantic_catalog.contracts.metric import Metric, MetricVersion
    from semantic_catalog.contracts.retention import RetentionContract

    known = set(Metric.model_fields) | set(MetricVersion.model_fields)
    known |= {"label", "description", "limitations"}  # nested under content
    required = set(baseline["semantic_layer"]["metric_contract"]["required_fields"])
    assert required <= known, sorted(required - known)

    cohort = set(baseline["semantic_layer"]["metric_contract"]["cohort_required_fields"]["fields"])
    assert cohort <= set(RetentionContract.model_fields), sorted(
        cohort - set(RetentionContract.model_fields)
    )


def test_bd3_has_its_adr() -> None:
    adr = " ".join(
        (ADR / "0002-metric-contract-required-fields-extended.md")
        .read_text(encoding="utf-8")
        .split()
    )
    assert "**Status**: Accepted" in adr
    assert "floor, not a ceiling" in adr
    assert "does not license leaving the baseline statement obsolete" in adr


# --- BD-4 -------------------------------------------------------------------


def test_bd4_tenant_isolation_is_conditional(baseline: dict[str, Any]) -> None:
    """Constitution IV: required only where separated domains share a deployment."""
    controls = baseline["security"]["controls"]
    assert controls["tenant_isolation"] == "conditional"
    assert "single-tenant" in controls["tenant_isolation_condition"]


def test_bd4_left_every_other_control_alone(baseline: dict[str, Any]) -> None:
    controls = baseline["security"]["controls"]
    for control in ("raw_access", "core_access"):
        assert controls[control] is False
    for control in ("pii_redaction", "audit_logs", "tool_allowlists"):
        assert controls[control] is True


# --- BD-5 -------------------------------------------------------------------


def test_bd5_catalog_coverage_is_separated_from_query_enablement(
    baseline: dict[str, Any],
) -> None:
    """A-1: the catalog governs all six sources from the outset. The phasing
    still governs which are queried end to end. Both hold."""
    slice_phase = next(p for p in baseline["implementation_phases"] if p["order"] == 2)
    note = slice_phase["scope_note"]
    assert "catálogo" in note.lower() or "catalogo" in note.lower()
    assert "A-1" in note
    # The phasing itself is unchanged — this was a clarification, not an override.
    assert slice_phase["sources"] == ["android_app", "ios_app"]


def test_bd5_all_six_sources_are_governed() -> None:
    authored = {p.stem for p in (REPO / "semantic" / "sources").glob("*.yaml")}
    # SEVEN since 2026-08-26: `subscription_daily` was declared over the first
    # view built on measured data. BD-5 asks that every authored source be
    # governed, and the seventh is -- it has an owner, a review group and no
    # approval, which is what governed-and-unpublishable looks like.
    assert len(authored) == 7, sorted(authored)


# --- the reconciliation record ---------------------------------------------


def test_every_deviation_is_traceable_to_its_governing_source(baseline: dict[str, Any]) -> None:
    """No silent conflict resolution: each correction names what outranked the
    baseline."""
    record = baseline["baseline_reconciliation"]
    assert record["applied_by"] == "T111"
    assert record["deviation_count"] == 5
    ids = [d["id"] for d in record["deviations"]]
    assert ids == ["BD-1", "BD-2", "BD-3", "BD-4", "BD-5"], ids
    for deviation in record["deviations"]:
        assert deviation["governing_source"].strip(), deviation["id"]
        assert deviation["previous"] is not None, deviation["id"]
        assert deviation["corrected_to"] is not None, deviation["id"]
        assert deviation["resolution"].strip(), deviation["id"]


def test_only_bd1_and_bd3_carry_an_adr(baseline: dict[str, Any]) -> None:
    """research.md: 2 ADRs, 5 YAML updates. No deviation is resolved by ADR alone."""
    record = baseline["baseline_reconciliation"]
    with_adr = {d["id"] for d in record["deviations"] if d["adr"]}
    assert with_adr == {"BD-1", "BD-3"}, sorted(with_adr)
    for deviation in record["deviations"]:
        if deviation["adr"]:
            assert (REPO / deviation["adr"]).is_file(), deviation["adr"]


def test_the_deviation_count_matches_research(baseline: dict[str, Any]) -> None:
    """research.md removed a sixth item as consistent rather than deviant."""
    text = RESEARCH.read_text(encoding="utf-8")
    assert "**Count: 5 deviations (BD-1 … BD-5).**" in text
    assert baseline["baseline_reconciliation"]["deviation_count"] == 5
    assert "sexto" in baseline["baseline_reconciliation"]["deviation_count_note"].lower()


def test_the_record_claims_no_readiness(baseline: dict[str, Any]) -> None:
    """Baseline reconciliation is not a release decision."""
    record = baseline["baseline_reconciliation"]
    claims = " ".join(record["not_claimed"]).lower()
    for absent in ("produção", "ext-a", "ext-b", "sc-002", "retenção", "primeira feature"):
        assert absent in claims, absent
    assert "T114" in record["not_claimed_note"]
    assert record["governed_outcomes_recorded"]["external_readiness_state"]["value"] == (
        "none_declared"
    )


def test_the_recorded_outcomes_match_the_implementation(baseline: dict[str, Any]) -> None:
    """The baseline states what the feature actually does, not what it hopes."""
    outcomes = baseline["baseline_reconciliation"]["governed_outcomes_recorded"]
    assert outcomes["canonical_business_timezone"]["value"] == "America/Sao_Paulo"
    assert outcomes["source_freshness_tolerance"]["scope"] == "per_source"
    assert outcomes["coverage_scope"]["value"] == "required_sources_only"
    assert outcomes["publication_state"]["value"] == "fail_closed"

    from semantic_catalog.periods.canonical import CANONICAL_TIMEZONE

    assert outcomes["canonical_business_timezone"]["value"] == CANONICAL_TIMEZONE


def test_retention_is_recorded_as_pending_not_available(baseline: dict[str, Any]) -> None:
    """FR-048 and D-8: identity rule and eligible event are business inputs, and
    inferring them is forbidden."""
    record = baseline["baseline_reconciliation"]
    assert any("retenção" in item.lower() for item in record["not_claimed"])
    spec = SPEC.read_text(encoding="utf-8")
    assert "FR-048" in spec
