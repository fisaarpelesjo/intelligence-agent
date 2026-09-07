"""Completion-evidence tests for T021 (classification) and T022 (schema export)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from semantic_catalog.contracts.classification import (
    CLASSIFICATION,
    FINGERPRINT_INPUTS,
    FieldClass,
    UnclassifiedFieldError,
    class_of,
    fields_in_class,
    is_fingerprinted,
    model_field_paths,
    verify_exhaustive,
)
from semantic_catalog.contracts.export import (
    EXPORTED_MODELS,
    check_drift,
    export_all,
    render_schema,
    schema_filename,
)

pytestmark = pytest.mark.unit


# --- T021 classification -----------------------------------------------------


def test_t021_map_covers_every_model_field_exactly_once() -> None:
    """T021 evidence: full coverage, no unassigned or double-assigned field."""
    verify_exhaustive()
    actual = model_field_paths()
    assert set(CLASSIFICATION) == actual
    assert len(CLASSIFICATION) == len(actual)


def test_t021_inherited_base_fields_are_classified() -> None:
    """catalog_schema_version, kind and the pt-BR lang marker all have a class."""
    assert class_of("Metric.catalog_schema_version") is FieldClass.STABLE_IDENTITY
    assert class_of("Metric.kind") is FieldClass.STABLE_IDENTITY
    for content_model in (
        "MetricContent",
        "SourceContent",
        "DimensionContent",
        "GlossaryContent",
        "ComparabilityContent",
        "AccessTagContent",
    ):
        assert class_of(f"{content_model}.lang") is FieldClass.DESCRIPTIVE


def test_t021_every_root_contract_declares_schema_version_and_kind() -> None:
    roots = [p.split(".")[0] for p in CLASSIFICATION if p.endswith(".catalog_schema_version")]
    for root in roots:
        assert class_of(f"{root}.kind") is FieldClass.STABLE_IDENTITY


def test_t021_unknown_path_raises_never_defaults() -> None:
    with pytest.raises(UnclassifiedFieldError, match="has no classification"):
        class_of("Metric.does_not_exist")


def test_t021_classes_partition_the_map() -> None:
    total = sum(len(fields_in_class(c)) for c in FieldClass)
    assert total == len(CLASSIFICATION)


@pytest.mark.parametrize(
    "path",
    [
        "MetricVersion.source_view",
        "MetricVersion.aggregation",
        "MetricVersion.calculation_basis",
        "MetricVersion.exclusions",
        "RetentionContract.identity_rule",
        "RetentionContract.eligible_event",
        "Source.delay_tolerance",
        "Metric.grain_family",
    ],
)
def test_t021_semantic_fields_are_fingerprinted(path: str) -> None:
    assert class_of(path) is FieldClass.SEMANTIC
    assert is_fingerprinted(path)


@pytest.mark.parametrize(
    "path",
    ["MetricVersion.version", "MetricVersion.effective_from", "MetricVersion.effective_to"],
)
def test_t021_as_of_lifecycle_fields_are_fingerprinted(path: str) -> None:
    """Protected even though they change no formula: they reassign which
    definition answers which period."""
    assert class_of(path) is FieldClass.LIFECYCLE
    assert is_fingerprinted(path)


def test_t021_restatements_are_lifecycle_but_not_fingerprinted() -> None:
    """A restatement moves the data revision, not the definition (FR-066)."""
    assert class_of("Source.restatements") is FieldClass.LIFECYCLE
    assert not is_fingerprinted("Source.restatements")


@pytest.mark.parametrize(
    "path",
    [
        "MetricContent.label",
        "Metric.synonyms",
        "MetricVersion.allowed_dimensions",
        "Metric.access",
        "Metric.owner",
        "SourceAvailability.status",
    ],
)
def test_t021_non_semantic_fields_are_not_fingerprinted(path: str) -> None:
    assert not is_fingerprinted(path)


def test_t021_fingerprint_input_set_is_closed() -> None:
    """Exactly the Semantic fields plus the three as-of Lifecycle fields."""
    semantic = set(fields_in_class(FieldClass.SEMANTIC))
    as_of = {
        "MetricVersion.version",
        "MetricVersion.effective_from",
        "MetricVersion.effective_to",
    }
    assert semantic | as_of == FINGERPRINT_INPUTS


def test_t021_previously_undocumented_fields_are_classified_and_not_semantic() -> None:
    """The 23 fields added to §4.4 must not have widened the fingerprint set."""
    added = {
        "AccessTag.effective_from",
        "AccessTagContent.lang",
        "AccessTagRegistry.tags",
        "CatalogPolicy.effective_from",
        "ComparabilityContent.lang",
        "DimensionContent.lang",
        "GlossaryContent.lang",
        "Metric.versions",
        "MetricContent.lang",
        "Owner.name",
        "OwnerRegistry.owners",
        "PendingVisibilityApproval.metric_id",
        "PendingVisibilityApprovals.approvals",
        "PolicySet.policies",
        "ReasonMessage.effective_from",
        "ReasonMessage.version",
        "ReasonMessageRegistry.lang",
        "ReasonMessageRegistry.messages",
        "Source.platform",
        "Source.product",
        "Source.store",
        "Source.type",
        "SourceContent.lang",
    }
    assert len(added) == 23
    assert added <= set(CLASSIFICATION)
    for path in sorted(added):
        assert class_of(path) is not FieldClass.SEMANTIC, path
        assert not is_fingerprinted(path), path


# --- T022 schema export ------------------------------------------------------


def test_t022_export_writes_one_schema_per_contract(tmp_path: Path) -> None:
    written = export_all(tmp_path)
    assert len(written) == len(EXPORTED_MODELS)
    for kind in EXPORTED_MODELS:
        assert (tmp_path / schema_filename(kind)).is_file()


def test_t022_regeneration_is_byte_identical(tmp_path: Path) -> None:
    """T022 evidence: regeneration is byte-identical on a clean tree."""
    export_all(tmp_path)
    first = {p.name: p.read_bytes() for p in sorted(tmp_path.iterdir())}
    export_all(tmp_path)
    second = {p.name: p.read_bytes() for p in sorted(tmp_path.iterdir())}
    assert first == second


def test_t022_no_drift_immediately_after_export(tmp_path: Path) -> None:
    export_all(tmp_path)
    assert check_drift(tmp_path) == ()


def test_t022_hand_edit_is_detected_as_drift(tmp_path: Path) -> None:
    """A generated schema is never a second source of truth."""
    export_all(tmp_path)
    target = tmp_path / schema_filename("metric")
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["title"] = "hand edited"
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    assert "metric" in check_drift(tmp_path)


def test_t022_missing_file_is_detected_as_drift(tmp_path: Path) -> None:
    export_all(tmp_path)
    (tmp_path / schema_filename("source")).unlink()
    assert "source" in check_drift(tmp_path)


def test_t022_schema_carries_do_not_edit_and_version_metadata() -> None:
    schema = json.loads(render_schema(EXPORTED_MODELS["metric"], "metric"))
    assert "x-do-not-edit" in schema
    assert schema["x-generated-by"] == "semantic_catalog.contracts.export"
    #: RE-DERIVADO em 2026-08-30: era `== 1`, e o `FR-808` moveu a versao para 2 quando
    #: `value_column` nasceu. O que importa e que o esquema exportado carregue A VERSAO
    #: CORRENTE DO MODELO, e nao um numero que alguem lembra de atualizar.
    from semantic_catalog.contracts._base import SCHEMA_VERSION

    assert schema["x-catalog-schema-version"] == SCHEMA_VERSION
    assert schema["$id"].endswith("metric.schema.json")


def test_t022_schema_forbids_additional_properties() -> None:
    """extra=forbid must survive into the generated schema."""
    schema = json.loads(render_schema(EXPORTED_MODELS["metric"], "metric"))
    assert schema.get("additionalProperties") is False


def test_t022_committed_schemas_match_the_models() -> None:
    """The repository's schemas/ must not drift from the source of truth."""
    committed = Path(__file__).resolve().parents[4] / "schemas"
    if not committed.is_dir():  # pragma: no cover - repo layout guard
        pytest.skip("schemas/ not present")
    assert check_drift(committed) == ()
