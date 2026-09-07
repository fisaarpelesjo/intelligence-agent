"""Completion-evidence tests for T023-T027 (loading, upgrade, L1, L2, result)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from semantic_catalog.contracts._base import SCHEMA_VERSION
from semantic_catalog.loader.load import (
    DuplicateIdentifierError,
    MalformedFileError,
    UnknownKindError,
    UnsupportedSchemaVersionError,
    load_catalog,
    load_file,
)
from semantic_catalog.loader.upgrade import MigrationError, migration_path, upgrade_payload
from semantic_catalog.validation.l1_schema import validate_file, validate_tree
from semantic_catalog.validation.l2_referential import (
    parse_codeowners_groups,
    validate_references,
)
from semantic_catalog.validation.result import (
    Severity,
    Subject,
    ValidationFinding,
    ValidationLayer,
    ValidationReport,
)

pytestmark = pytest.mark.unit

OWNERS = """\
catalog_schema_version: 1
kind: owners
owners:
  - id: product_analytics
    name: Product Analytics
    kind: team
    review_group: "@org/product-analytics"
"""

SOURCE = """\
catalog_schema_version: 1
kind: source
id: android_app
type: product_telemetry
product: mobile_app
platform: android
reporting_timezone: America/Sao_Paulo
earliest_available_date: 2023-01-01
expected_refresh_interval: P1D
delay_tolerance: P2D
owner: product_analytics
content:
  lang: pt-BR
  label: Aplicativo Android
"""

DIMENSION = """\
catalog_schema_version: 1
kind: dimension
id: platform
owner: product_analytics
permitted_values: open
content:
  lang: pt-BR
  label: Plataforma
  description: Plataforma do produto.
source_applicability:
  - source: android_app
    available_from: 2023-01-01
"""

METRIC = """\
catalog_schema_version: 1
kind: metric
name: active_users
owner: product_analytics
access: standard
grain_family: day
versions:
  - version: 1
    effective_from: 2024-01-01
    source_view: semantic.product_daily_metrics
    grain: date x platform
    aggregation: count_distinct
    additivity: non_additive
    unit: users
    time_dimension: date
    calculation_basis: Usuários distintos com evento no dia.
    allowed_dimensions: [platform]
    content:
      lang: pt-BR
      label: Usuários ativos
      description: Usuários distintos no dia.
source_availability:
  - source: android_app
    status: available
    available_from: 2023-01-01
    effective_from: 2024-01-01
"""

POLICY = """\
catalog_schema_version: 1
kind: catalog_policy
policy_id: catalog_core
policy_version: 1
effective_from: 2024-01-01
owner_role: data_governance
approval_roles: [data_governance]
authorization:
  default: deny
  require_access_tag: true
  unknown_tag_behaviour: fail_closed
  self_approval_allowed: false
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


def _tree(tmp_path: Path, **files: str) -> Path:
    root = tmp_path / "semantic"
    layout = {
        "owners": root / "owners.yaml",
        "source": root / "sources" / "android_app.yaml",
        "dimension": root / "dimensions" / "platform.yaml",
        "metric": root / "metrics" / "active_users.yaml",
    }
    for key, text in files.items():
        path = layout[key]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    root.mkdir(parents=True, exist_ok=True)
    return root


# --- T023 loader -------------------------------------------------------------


def test_t023_valid_tree_loads(tmp_path: Path) -> None:
    root = _tree(tmp_path, owners=OWNERS, source=SOURCE, dimension=DIMENSION, metric=METRIC)
    catalog = load_catalog(root)
    assert set(catalog.metrics) == {"active_users"}
    assert set(catalog.sources) == {"android_app"}
    assert catalog.owners is not None
    assert not catalog.is_empty()


def test_t023_unknown_kind_is_refused(tmp_path: Path) -> None:
    """The directory is never used to infer the contract."""
    root = tmp_path / "semantic" / "metrics"
    root.mkdir(parents=True)
    path = root / "x.yaml"
    path.write_text("catalog_schema_version: 1\nkind: not_a_contract\n", encoding="utf-8")
    with pytest.raises(UnknownKindError, match="not a governed contract"):
        load_file(path)


def test_t023_missing_kind_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "x.yaml"
    path.write_text("catalog_schema_version: 1\n", encoding="utf-8")
    with pytest.raises(UnknownKindError):
        load_file(path)


@pytest.mark.parametrize("version", [0, SCHEMA_VERSION + 1, 99])
def test_t023_unsupported_schema_version_is_refused(tmp_path: Path, version: int) -> None:
    path = tmp_path / "owners.yaml"
    path.write_text(
        OWNERS.replace("catalog_schema_version: 1", f"catalog_schema_version: {version}"),
        encoding="utf-8",
    )
    with pytest.raises(UnsupportedSchemaVersionError, match="outside the supported window"):
        load_file(path)


def test_t023_non_integer_schema_version_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "owners.yaml"
    path.write_text(
        OWNERS.replace("catalog_schema_version: 1", 'catalog_schema_version: "1"'), encoding="utf-8"
    )
    with pytest.raises(UnsupportedSchemaVersionError, match="must be an integer"):
        load_file(path)


def test_t023_unknown_field_is_refused(tmp_path: Path) -> None:
    """extra=forbid surfaces through the loader."""
    path = tmp_path / "android_app.yaml"
    path.write_text(SOURCE + "unexpected_key: x\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_file(path)


@pytest.mark.parametrize(
    "content",
    ["", "- a\n- b\n", "just a string\n"],
)
def test_t023_malformed_file_is_refused(tmp_path: Path, content: str) -> None:
    path = tmp_path / "x.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(MalformedFileError):
        load_file(path)


def test_t023_unparsable_yaml_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "x.yaml"
    path.write_text("kind: [unclosed\n", encoding="utf-8")
    with pytest.raises(MalformedFileError, match="cannot be read as YAML"):
        load_file(path)


def test_t023_duplicate_identifier_is_refused(tmp_path: Path) -> None:
    """Which definition wins must never depend on filesystem ordering."""
    root = _tree(tmp_path, owners=OWNERS, source=SOURCE)
    (root / "sources" / "duplicate.yaml").write_text(SOURCE, encoding="utf-8")
    with pytest.raises(DuplicateIdentifierError, match="already defined by"):
        load_catalog(root)


def test_t023_second_singleton_registry_is_refused(tmp_path: Path) -> None:
    root = _tree(tmp_path, owners=OWNERS)
    (root / "owners_copy.yaml").write_text(OWNERS, encoding="utf-8")
    with pytest.raises(DuplicateIdentifierError, match="a second owners file"):
        load_catalog(root)


def test_t023_missing_root_is_refused(tmp_path: Path) -> None:
    with pytest.raises(MalformedFileError, match="is not a directory"):
        load_catalog(tmp_path / "nope")


# --- T024 upgrade path -------------------------------------------------------


def test_t024_current_version_needs_no_migration() -> None:
    payload = {"catalog_schema_version": SCHEMA_VERSION, "kind": "owners"}
    assert upgrade_payload(payload, from_version=SCHEMA_VERSION) == payload
    assert migration_path(SCHEMA_VERSION) == ()


def test_t024_upgrade_does_not_mutate_its_input() -> None:
    payload = {"catalog_schema_version": SCHEMA_VERSION, "kind": "owners"}
    upgraded = upgrade_payload(payload, from_version=SCHEMA_VERSION)
    upgraded["kind"] = "changed"
    assert payload["kind"] == "owners"


def test_t024_unsupported_version_raises() -> None:
    with pytest.raises(MigrationError, match="outside the supported window"):
        upgrade_payload({"catalog_schema_version": 99}, from_version=99)


def test_t024_migration_path_is_total_for_supported_versions() -> None:
    """A supported version with no migration is a bug, not a pass-through."""
    from semantic_catalog.contracts._base import SUPPORTED_SCHEMA_VERSIONS

    for version in SUPPORTED_SCHEMA_VERSIONS:
        steps = migration_path(version)
        if steps:  # pragma: no cover - no N-1 exists at schema version 1
            upgrade_payload({"catalog_schema_version": version}, from_version=version)


# --- T025 L1 -----------------------------------------------------------------


def test_t025_valid_tree_produces_no_findings(tmp_path: Path) -> None:
    root = _tree(tmp_path, owners=OWNERS, source=SOURCE, dimension=DIMENSION, metric=METRIC)
    report = validate_tree(root)
    assert report.is_valid(), report.render()


def test_t025_schema_violation_names_the_offending_field(tmp_path: Path) -> None:
    """T025 evidence: each rule has a failing fixture naming the offending field."""
    path = tmp_path / "android_app.yaml"
    path.write_text(SOURCE.replace("delay_tolerance: P2D\n", ""), encoding="utf-8")
    findings = validate_file(path)
    assert findings
    assert any(f.subject.field_path == "delay_tolerance" for f in findings)
    assert all(f.layer is ValidationLayer.L1_SCHEMA for f in findings)


def test_t025_filename_must_match_identifier(tmp_path: Path) -> None:
    path = tmp_path / "wrong_name.yaml"
    path.write_text(SOURCE, encoding="utf-8")
    rules = {f.rule for f in validate_file(path)}
    assert "filename_mismatch" in rules


def test_t025_filename_rule_exempts_contracts_with_a_fixed_canonical_name(
    tmp_path: Path,
) -> None:
    """The rule applies only where the contract path is ``{id}.yaml``.

    ``catalog-file-contracts §4.4`` fixes the policy file at
    ``semantic/policies/catalog-policy.yaml``. ``policy_id`` is an ``Identifier``
    and so is snake_case, meaning the stem can never equal it — applying the rule
    here would refuse the one path the contract mandates.
    """
    path = tmp_path / "catalog-policy.yaml"
    path.write_text(POLICY, encoding="utf-8")
    rules = {f.rule for f in validate_file(path)}
    assert "filename_mismatch" not in rules, rules


def test_t025_identifier_casing_is_enforced(tmp_path: Path) -> None:
    """Non-snake_case identifiers are refused and the offending field is named.

    The `Identifier` type catches this during model validation, so the finding
    arrives as `schema_violation` rather than L1's own casing rule. What matters
    for FR-053 is that it is refused and that the message names `id`.
    """
    path = tmp_path / "AndroidApp.yaml"
    path.write_text(SOURCE.replace("id: android_app", "id: AndroidApp"), encoding="utf-8")
    findings = validate_file(path)
    assert findings
    assert any(f.subject.field_path == "id" for f in findings)


def test_t025_non_sequential_version_numbers_reported(tmp_path: Path) -> None:
    text = METRIC.replace("  - version: 1\n", "  - version: 2\n")
    path = tmp_path / "active_users.yaml"
    path.write_text(text, encoding="utf-8")
    rules = {f.rule for f in validate_file(path)}
    assert "version_numbers_not_sequential" in rules


def test_t025_unloadable_file_produces_a_finding_not_a_skip(tmp_path: Path) -> None:
    root = tmp_path / "semantic"
    root.mkdir()
    (root / "broken.yaml").write_text(
        "kind: nonsense\ncatalog_schema_version: 1\n", encoding="utf-8"
    )
    report = validate_tree(root)
    assert not report.is_valid()
    assert {f.rule for f in report.findings} == {"load_refused"}


def test_t025_missing_root_reports_rather_than_passing(tmp_path: Path) -> None:
    report = validate_tree(tmp_path / "nope")
    assert not report.is_valid()


# --- T026 L2 -----------------------------------------------------------------


def _codeowners(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "CODEOWNERS"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def test_t026_complete_catalog_resolves(tmp_path: Path) -> None:
    root = _tree(tmp_path, owners=OWNERS, source=SOURCE, dimension=DIMENSION, metric=METRIC)
    report = validate_references(load_catalog(root))
    assert report.is_valid(), report.render()


def test_t026_unresolvable_owner_names_both_ends(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        owners=OWNERS,
        source=SOURCE,
        dimension=DIMENSION,
        metric=METRIC.replace("owner: product_analytics", "owner: ghost_team"),
    )
    report = validate_references(load_catalog(root))
    assert not report.is_valid()
    finding = next(f for f in report.findings if f.rule == "owner_unresolved")
    assert "active_users" in finding.message
    assert "ghost_team" in finding.message


def test_t026_unresolvable_source_reference_reported(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        owners=OWNERS,
        source=SOURCE,
        dimension=DIMENSION,
        metric=METRIC.replace("- source: android_app", "- source: ios_app"),
    )
    rules = {f.rule for f in validate_references(load_catalog(root)).findings}
    assert "source_unresolved" in rules


def test_t026_unresolvable_dimension_reference_reported(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        owners=OWNERS,
        source=SOURCE,
        dimension=DIMENSION,
        metric=METRIC.replace("allowed_dimensions: [platform]", "allowed_dimensions: [country]"),
    )
    rules = {f.rule for f in validate_references(load_catalog(root)).findings}
    assert "dimension_unresolved" in rules


def test_t026_missing_owners_registry_reported(tmp_path: Path) -> None:
    root = _tree(tmp_path, source=SOURCE, dimension=DIMENSION, metric=METRIC)
    rules = {f.rule for f in validate_references(load_catalog(root)).findings}
    assert "owners_registry_missing" in rules


def test_t026_review_group_must_exist_in_codeowners(tmp_path: Path) -> None:
    """Ownership record and routing file must not diverge (research §R-7)."""
    root = _tree(tmp_path, owners=OWNERS, source=SOURCE, dimension=DIMENSION, metric=METRIC)
    good = _codeowners(tmp_path, "semantic/** @org/product-analytics\n")
    assert validate_references(load_catalog(root), codeowners=good).is_valid()

    bad = _codeowners(tmp_path, "semantic/** @org/somebody-else\n")
    report = validate_references(load_catalog(root), codeowners=bad)
    assert not report.is_valid()
    assert any(f.rule == "review_group_unresolved" for f in report.findings)


def test_t026_absent_codeowners_fails_closed(tmp_path: Path) -> None:
    root = _tree(tmp_path, owners=OWNERS, source=SOURCE, dimension=DIMENSION, metric=METRIC)
    report = validate_references(load_catalog(root), codeowners=tmp_path / "NOPE")
    assert not report.is_valid()


def test_t026_codeowners_parser_ignores_comments_and_blanks(tmp_path: Path) -> None:
    path = _codeowners(
        tmp_path,
        """
        # a comment @org/not-a-group-because-comment

        semantic/** @org/a @org/b
        """,
    )
    assert parse_codeowners_groups(path) == frozenset({"@org/a", "@org/b"})


# --- T027 validation result --------------------------------------------------


def _finding(**overrides: object) -> ValidationFinding:
    payload: dict[str, object] = {
        "layer": ValidationLayer.L1_SCHEMA,
        "rule": "example_rule",
        "subject": Subject(kind="metric", identifier="active_users"),
        "message": "metric 'active_users' is wrong",
    }
    return ValidationFinding.model_validate(payload | overrides)


def test_t027_finding_requires_a_subject() -> None:
    """T027 evidence: no result is constructible without an identified subject."""
    with pytest.raises(ValidationError):
        ValidationFinding.model_validate(
            {"layer": ValidationLayer.L1_SCHEMA, "rule": "r", "message": "something is wrong"}
        )


def test_t027_subject_requires_kind_and_identifier() -> None:
    with pytest.raises(ValidationError):
        Subject.model_validate({"kind": "metric"})
    with pytest.raises(ValidationError):
        Subject.model_validate({"kind": "", "identifier": ""})


def test_t027_generic_message_is_rejected() -> None:
    """SC-004: zero generic refusals — the message must name its subject."""
    with pytest.raises(ValidationError, match="generic refusals are"):
        _finding(message="the catalog is invalid")


def test_t027_report_is_invalid_when_any_error_present() -> None:
    report = ValidationReport.from_findings([_finding()])
    assert not report.is_valid()
    assert len(report.errors) == 1


def test_t027_warnings_do_not_invalidate() -> None:
    report = ValidationReport.from_findings([_finding(severity=Severity.WARNING)])
    assert report.is_valid()
    assert len(report.warnings) == 1


def test_t027_empty_report_is_valid() -> None:
    assert ValidationReport().is_valid()


def test_t027_reports_merge_and_filter_by_layer() -> None:
    l1 = ValidationReport.from_findings([_finding()])
    l2 = ValidationReport.from_findings([_finding(layer=ValidationLayer.L2_REFERENTIAL)])
    merged = l1.merge(l2)
    assert len(merged.findings) == 2
    assert len(merged.by_layer(ValidationLayer.L2_REFERENTIAL)) == 1


def test_t027_render_names_layer_severity_and_rule() -> None:
    line = ValidationReport.from_findings([_finding()]).render()[0]
    assert line.startswith("[L1/error] example_rule:")
    assert "active_users" in line
