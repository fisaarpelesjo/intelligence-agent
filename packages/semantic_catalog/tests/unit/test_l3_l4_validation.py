"""L3 reconciliation and L4 policy — T092, T093 (FR-009, FR-054, FR-056, FR-058, FR-074).

Every rule in both layers has a failing case here, because a validator with no
failing case is a validator nobody has proved fires.

L3's asymmetry is the design: **declared-but-absent fails, absent-but-declared
warns**. A declaration the warehouse cannot support sends a consumer to ask a
question nothing can answer; ungoverned data is just a warehouse being a
warehouse.

L4's limit is stated as plainly as its rules: it checks that pt-BR content is
**present and declared**, never that the Portuguese is correct. That is D-10, a
named reviewer duty, and no assertion here may be read as covering it.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from semantic_catalog.contracts.dimension import Dimension, DimensionContent
from semantic_catalog.contracts.metric import Lifecycle
from semantic_catalog.contracts.policy import CatalogPolicy, PolicySet
from semantic_catalog.contracts.reason_codes import ReasonCode
from semantic_catalog.loader.load import LoadedCatalog, load_catalog
from semantic_catalog.validation.l3_reconciliation import (
    ObservedCoverageSet,
    load_observed_coverage,
    validate_reconciliation,
)
from semantic_catalog.validation.l4_policy import validate_policy
from semantic_catalog.validation.result import Severity

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
PRODUCTION = Path(__file__).resolve().parents[4] / "semantic"
OBSERVED = FIXTURES / "coverage" / "observed.yaml"
ON = date(2026, 8, 11)


@pytest.fixture(scope="module")
def catalog() -> LoadedCatalog:
    return load_catalog(PRODUCTION)


@pytest.fixture(scope="module")
def policy(catalog: LoadedCatalog) -> CatalogPolicy:
    return PolicySet(policies=catalog.policies).resolve_effective(ON)


@pytest.fixture(scope="module")
def observed() -> ObservedCoverageSet:
    return load_observed_coverage(OBSERVED)


def _without(observed: ObservedCoverageSet, metric_id: str) -> ObservedCoverageSet:
    return ObservedCoverageSet(
        rows=tuple(row for row in observed.rows if row.metric != metric_id),
        is_fixture=observed.is_fixture,
    )


def _rules(report: Any, severity: Severity) -> set[str]:
    return {f.rule for f in report.findings if f.severity is severity}


# --- T092: L3 reconciliation ------------------------------------------------


def test_a_fixture_observation_says_so_in_the_report(
    catalog: LoadedCatalog, observed: ObservedCoverageSet
) -> None:
    """A green L3 against a fixture is not a statement about production."""
    report = validate_reconciliation(catalog, observed)
    assert "observed_coverage_is_a_fixture" in _rules(report, Severity.WARNING)


def test_a_complete_observation_reconciles(
    catalog: LoadedCatalog, observed: ObservedCoverageSet
) -> None:
    report = validate_reconciliation(catalog, observed)
    assert report.is_valid(), report.render()


def test_declared_but_absent_fails(catalog: LoadedCatalog, observed: ObservedCoverageSet) -> None:
    """OD-106 (2026-09-03): o par dirigido virou mrr_usd — os fantasmas aposentaram; e o
    par-vivo continua exigido MESMO num sliding (o predates e o que o sliding dispensa)."""
    report = validate_reconciliation(catalog, _without(observed, "mrr_usd"))
    assert not report.is_valid()
    assert "declared_without_coverage" in _rules(report, Severity.ERROR)
    assert any("mrr_usd" in f.message for f in report.errors)


def test_absent_but_declared_only_warns(
    catalog: LoadedCatalog, observed: ObservedCoverageSet
) -> None:
    report = validate_reconciliation(catalog, observed)
    warnings = [f for f in report.warnings if f.rule == "coverage_without_declaration"]
    # OD-106 (2026-09-03): o par nao-governado da fixture regenerada e o cac_brl — a
    # decisao datada de 2026-08-30 o mantem indisponivel enquanto o armazem o cobre.
    assert [f.subject.identifier for f in warnings] == ["cac_brl"]
    assert report.is_valid()


def test_a_declaration_predating_observed_coverage_fails(catalog: LoadedCatalog) -> None:
    """Claiming days the source does not have is the same lie, later in the range.

    OD-106 (2026-09-03): dirigido em COPIA com o sliding DESLIGADO — num sliding o
    predates e dispensado por semantica, entao a regra e provada onde ela vale: numa
    declaracao de data fixa cuja janela observada comeca depois."""
    metric = catalog.metrics["mrr_usd"]
    fixed = metric.model_copy(
        update={
            "source_availability": tuple(
                entry.model_copy(update={"sliding": False}) for entry in metric.source_availability
            )
        }
    )
    patched_metrics = dict(catalog.metrics)
    patched_metrics["mrr_usd"] = fixed
    patched = _replace(catalog, metrics=patched_metrics)
    rows = load_observed_coverage(OBSERVED).rows
    shifted = ObservedCoverageSet(
        rows=tuple(
            row.model_copy(update={"min_date": date(2026, 1, 1)})
            if row.metric == "mrr_usd"
            else row
            for row in rows
        ),
        is_fixture=True,
    )
    report = validate_reconciliation(patched, shifted)
    assert "declared_availability_predates_coverage" in _rules(report, Severity.ERROR)

    # E a MESMA janela contra a declaracao DESLIZANTE real nao acende: o sliding
    # dispensa o predates por desenho, nunca por acidente.
    sliding_report = validate_reconciliation(catalog, shifted)
    assert "declared_availability_predates_coverage" not in _rules(sliding_report, Severity.ERROR)


def test_a_dimension_applicable_to_no_declared_source_fails(
    catalog: LoadedCatalog, observed: ObservedCoverageSet
) -> None:
    """The combination matrix would advertise it and every request would refuse."""
    # OD-106 (2026-09-03): a dimensao dirigida precisa ser uma que uma metrica COM fonte
    # declarada permita — os fantasmas aposentaram, entao e "country" (permitida pelas
    # servidas), estreitada para uma fonte que ninguem declara mais.
    dimension = catalog.dimensions["country"]
    narrowed = dimension.model_copy(
        update={
            "source_applicability": tuple(
                entry.model_copy(update={"source": "website"})
                for entry in (dimension.source_applicability or ())
            )
            or ()
        }
    )
    if not narrowed.source_applicability:
        pytest.skip("no dimension in the production catalog declares source applicability")
    patched = _with_dimension(catalog, narrowed)
    report = validate_reconciliation(patched, observed)
    assert "dimension_not_applicable_to_any_declared_source" in _rules(report, Severity.ERROR)


# --- T093: L4 policy --------------------------------------------------------


def test_the_production_catalog_passes_every_policy_rule(
    catalog: LoadedCatalog, policy: CatalogPolicy
) -> None:
    report = validate_policy(catalog, policy)
    assert report.is_valid(), report.render()


def test_a_missing_content_block_fails(catalog: LoadedCatalog, policy: CatalogPolicy) -> None:
    """Reached with ``model_construct`` deliberately: the contract refuses it at
    L1, and this sweep is what catches a *future* contract that forgets to."""
    dimension = next(iter(catalog.dimensions.values()))
    patched = _with_dimension(catalog, _broken_dimension(dimension, None))
    report = validate_policy(patched, policy)
    assert "pt_br_content_missing" in _rules(report, Severity.ERROR)


def test_a_blank_content_field_fails(catalog: LoadedCatalog, policy: CatalogPolicy) -> None:
    """A present-but-empty field is a missing field with extra steps."""
    dimension = next(iter(catalog.dimensions.values()))
    blank = _broken_content(dimension.content, label="   ")
    patched = _with_dimension(catalog, _broken_dimension(dimension, blank))
    report = validate_policy(patched, policy)
    assert "pt_br_content_missing" in _rules(report, Severity.ERROR)


def test_a_content_block_not_declared_pt_br_fails(
    catalog: LoadedCatalog, policy: CatalogPolicy
) -> None:
    dimension = next(iter(catalog.dimensions.values()))
    wrong = _broken_content(dimension.content, lang="en-US")
    patched = _with_dimension(catalog, _broken_dimension(dimension, wrong))
    report = validate_policy(patched, policy)
    assert "content_lang_not_pt_br" in _rules(report, Severity.ERROR)


def test_a_policy_that_switches_off_the_visibility_approval_fails(
    catalog: LoadedCatalog, policy: CatalogPolicy
) -> None:
    """FR-058 is unconditional, so a policy switching it off disagrees with the
    requirement rather than configuring it."""
    relaxed = policy.model_copy(
        update={
            "pending_visibility": policy.pending_visibility.model_copy(
                update={"require_visibility_approval": False}
            )
        }
    )
    report = validate_policy(catalog, relaxed)
    assert "pending_visibility_approval_not_required" in _rules(report, Severity.ERROR)


def test_an_approval_for_a_non_exposable_field_fails(
    catalog: LoadedCatalog, policy: CatalogPolicy
) -> None:
    narrowed = policy.model_copy(
        update={
            "pending_visibility": policy.pending_visibility.model_copy(
                update={"exposable_fields": ("expected_available_from",)}
            )
        }
    )
    patched = _with_approval(catalog, "retention_rate_d1", "public_name")
    report = validate_policy(patched, narrowed)
    assert "visibility_approval_field_not_exposable" in _rules(report, Severity.ERROR)


def test_an_approval_for_a_published_metric_warns(
    catalog: LoadedCatalog, policy: CatalogPolicy
) -> None:
    patched = _with_approval(catalog, "retention_rate_d1", "public_name")
    report = validate_policy(patched, policy, lifecycles={"retention_rate_d1": Lifecycle.PUBLISHED})
    assert "visibility_approval_for_non_pending_metric" in _rules(report, Severity.WARNING)


def test_a_publishable_code_with_no_message_fails(
    catalog: LoadedCatalog, policy: CatalogPolicy
) -> None:
    """FR-074: it fails the build, not the answer."""
    registry = catalog.reason_messages
    assert registry is not None
    stripped = registry.model_copy(
        update={
            "messages": tuple(
                m for m in registry.messages if m.reason_code is not ReasonCode.RELEASE_WITHDRAWN
            )
        }
    )
    patched = _replace(catalog, reason_messages=stripped)
    report = validate_policy(patched, policy)
    assert "publishable_code_without_message" in _rules(report, Severity.ERROR)
    assert any("RELEASE_WITHDRAWN" in f.message for f in report.errors)


def test_a_missing_message_registry_fails(catalog: LoadedCatalog, policy: CatalogPolicy) -> None:
    report = validate_policy(_replace(catalog, reason_messages=None), policy)
    assert "reason_message_registry_missing" in _rules(report, Severity.ERROR)


def test_language_correctness_is_not_claimed() -> None:
    """D-10. L4 checks presence and declaration; correctness stays a reviewer
    duty, and no rule here may be read as covering it."""
    source = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "semantic_catalog"
        / "validation"
        / "l4_policy.py"
    ).read_text(encoding="utf-8")
    assert "D-10" in source
    assert "langdetect" not in source and "detect_language" not in source


# --- helpers ----------------------------------------------------------------


def _replace(catalog: LoadedCatalog, **changes: Any) -> LoadedCatalog:
    fields: dict[str, Any] = {name: getattr(catalog, name) for name in catalog.__dataclass_fields__}
    fields.update(changes)
    return LoadedCatalog(**fields)


def _with_dimension(catalog: LoadedCatalog, dimension: Dimension) -> LoadedCatalog:
    dimensions: dict[str, Dimension] = {**catalog.dimensions, dimension.id: dimension}
    return _replace(catalog, dimensions=dimensions)


def _broken_dimension(dimension: Dimension, content: Any) -> Dimension:
    """A contract violation the models would refuse, built on purpose.

    ``model_construct`` skips validation, which is the only way to reach these
    rules: L1 already refuses them, and this sweep exists to catch a *future*
    contract that stops refusing them.
    """
    fields: dict[str, Any] = dict(dimension.__dict__)
    fields["content"] = content
    return Dimension.model_construct(None, **fields)


def _broken_content(content: DimensionContent, **changes: Any) -> DimensionContent:
    fields: dict[str, Any] = dict(content.__dict__)
    fields.update(changes)
    return DimensionContent.model_construct(None, **fields)


def _with_approval(catalog: LoadedCatalog, metric_id: str, field_name: str) -> LoadedCatalog:
    from semantic_catalog.contracts.approval import (
        PendingVisibilityApproval,
        PendingVisibilityApprovals,
    )

    approval = PendingVisibilityApproval.model_validate(
        {
            "metric_id": metric_id,
            "field_name": field_name,
            "approval_status": "approved",
            "approved_by_role": "data_governance",
            "approved_at": "2026-08-11",
            "source_commit": "abc1234",
        }
    )
    return _replace(
        catalog,
        approvals=PendingVisibilityApprovals.model_validate(
            {
                "catalog_schema_version": 1,
                "kind": "pending_visibility_approvals",
                "approvals": [approval.model_dump(mode="json")],
            }
        ),
    )
