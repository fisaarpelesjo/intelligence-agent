"""Fingerprint, version gate and release validation — T086, T087, T088.

Quickstart Scenario 9 and Scenario 18. Three things are proved here:

**The fingerprint input set is closed and equals the authoritative
classification.** Not "roughly matches" — equals, computed from
``CLASSIFICATION`` rather than from a list maintained beside it. A Semantic edit
moves the digest; a Descriptive edit does not.

**The version gate cannot be skipped.** A Semantic edit with no new block fails.
A Semantic edit to a *closed* block fails whether or not a new block was
appended. A Descriptive edit to a closed block passes.

**A clean merge is not validation.** Two branches each appending ``version: 2``
merge without a textual conflict and produce a file the ``Metric`` contract
cannot even load — so the collision is detected from the raw payload, as a
finding naming the metric, rather than as a stack trace naming a validator.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from semantic_catalog.contracts.classification import (
    CLASSIFICATION,
    FINGERPRINT_INPUTS,
    FieldClass,
)
from semantic_catalog.contracts.metric import Metric
from semantic_catalog.loader.load import LoadedCatalog, load_catalog
from semantic_catalog.resolution.fingerprint import (
    fingerprint_inputs,
    metric_fingerprints,
    version_fingerprint,
)
from semantic_catalog.validation.l4_version import (
    FingerprintBaseline,
    moved_fields,
    validate_version_gate,
)
from semantic_catalog.validation.release import detect_version_collisions, validate_release

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "versioned_catalog"
PRODUCTION = Path(__file__).resolve().parents[4] / "semantic"
CATALOG = FIXTURES / "catalog"
ON = date(2026, 8, 11)


@pytest.fixture(scope="module")
def catalog() -> LoadedCatalog:
    return load_catalog(CATALOG)


@pytest.fixture(scope="module")
def metric(catalog: LoadedCatalog) -> Metric:
    return catalog.metrics["fixture_metric"]


def _edit(metric: Metric, version_index: int, **changes: Any) -> Metric:
    payload: dict[str, Any] = metric.model_dump(mode="json")
    payload["versions"][version_index].update(changes)
    return Metric.model_validate(payload)


# --- T086: the fingerprint input set is closed ------------------------------


def test_the_input_set_equals_the_authoritative_classification() -> None:
    """Computed from §4.4's executable map, not restated beside it."""
    semantic = {p for p, c in CLASSIFICATION.items() if c is FieldClass.SEMANTIC}
    as_of = {
        "MetricVersion.version",
        "MetricVersion.effective_from",
        "MetricVersion.effective_to",
    }
    assert semantic | as_of == FINGERPRINT_INPUTS


def test_only_fingerprinted_paths_appear_in_the_inputs(metric: Metric) -> None:
    for path in fingerprint_inputs(metric.versions[0]):
        assert path in FINGERPRINT_INPUTS
    assert "MetricVersion.content" not in fingerprint_inputs(metric.versions[0])
    assert "MetricVersion.allowed_dimensions" not in fingerprint_inputs(metric.versions[0])


def test_a_semantic_edit_moves_the_digest(metric: Metric) -> None:
    edited = _edit(metric, 0, aggregation="count_distinct")
    assert version_fingerprint(metric, metric.versions[0]) != version_fingerprint(
        edited, edited.versions[0]
    )


def test_a_descriptive_edit_does_not_move_the_digest(metric: Metric) -> None:
    """``content.description`` is Descriptive and deliberately unfingerprinted:
    a description is allowed to improve without redefining the metric."""
    edited = _edit(
        metric,
        0,
        content={
            "lang": "pt-BR",
            "label": "Sessoes do aplicativo",
            "description": "Texto revisado, mesma definicao.",
        },
    )
    assert version_fingerprint(metric, metric.versions[0]) == version_fingerprint(
        edited, edited.versions[0]
    )


def test_moving_an_effective_date_moves_the_digest(metric: Metric) -> None:
    """The three as-of Lifecycle fields change no formula and change which
    definition answers which period, which is the same harm."""
    edited = _edit(metric, 2, effective_to="2026-12-31")
    assert version_fingerprint(metric, metric.versions[2]) != version_fingerprint(
        edited, edited.versions[2]
    )


def test_a_metric_level_semantic_change_moves_every_version(metric: Metric) -> None:
    """``grain_family`` lives on the metric and changes what all of them mean."""
    payload: dict[str, Any] = metric.model_dump(mode="json")
    payload["grain_family"] = "cohort"
    payload["retention"] = {
        "window_days": 1,
        "retention_style": "exact_day",
        "cohort_assignment": "first_eligible_activity",
        "cohort_timezone": "America/Sao_Paulo",
        "numerator": "Usuarios ativos no dia alvo.",
        "denominator": "Usuarios da coorte.",
        "min_maturity_days": 1,
    }
    edited = Metric.model_validate(payload)
    before = metric_fingerprints(metric)
    after = metric_fingerprints(edited)
    assert all(before[n] != after[n] for n in before)


def test_the_digest_is_stable_across_runs(metric: Metric) -> None:
    assert metric_fingerprints(metric) == metric_fingerprints(metric)


# --- T087: the version gate -------------------------------------------------


def test_a_semantic_edit_without_a_new_block_fails(catalog: LoadedCatalog, metric: Metric) -> None:
    """Quickstart Scenario 9: change ``aggregation``, append nothing, fail."""
    baseline = FingerprintBaseline.from_catalog(catalog)
    edited = {**catalog.metrics, "fixture_metric": _edit(metric, 2, aggregation="sum")}
    report = validate_version_gate(edited, baseline)
    rules = {f.rule for f in report.errors}
    assert "semantic_edit_without_new_version" in rules
    assert any("MetricVersion.aggregation" in f.message for f in report.errors)


def test_a_semantic_edit_to_a_closed_version_fails(catalog: LoadedCatalog, metric: Metric) -> None:
    """Even with a new block appended. The new block governs new dates, so
    touching a closed one can only be rewriting an answered period."""
    baseline = FingerprintBaseline.from_catalog(catalog)
    payload: dict[str, Any] = metric.model_dump(mode="json")
    payload["versions"][0]["unit"] = "events"
    payload["versions"][2]["effective_to"] = "2025-12-31"
    payload["versions"].append(
        {
            **payload["versions"][2],
            "version": 4,
            "effective_from": "2026-01-01",
            "effective_to": None,
        }
    )
    report = validate_version_gate(
        {**catalog.metrics, "fixture_metric": Metric.model_validate(payload)}, baseline
    )
    assert "closed_version_semantic_edit" in {f.rule for f in report.errors}


def test_a_descriptive_edit_to_a_closed_version_passes(
    catalog: LoadedCatalog, metric: Metric
) -> None:
    baseline = FingerprintBaseline.from_catalog(catalog)
    edited = _edit(
        metric,
        0,
        content={
            "lang": "pt-BR",
            "label": "Sessoes do aplicativo",
            "description": "Texto revisado, mesma definicao.",
        },
    )
    report = validate_version_gate({**catalog.metrics, "fixture_metric": edited}, baseline)
    assert report.is_valid(), report.render()


def test_a_semantic_edit_with_a_new_block_passes(catalog: LoadedCatalog, metric: Metric) -> None:
    """The whole point of the gate is that this is the supported path."""
    baseline = FingerprintBaseline.from_catalog(catalog)
    payload: dict[str, Any] = metric.model_dump(mode="json")
    payload["versions"][2]["effective_to"] = "2025-12-31"
    payload["versions"].append(
        {
            **payload["versions"][2],
            "version": 4,
            "effective_from": "2026-01-01",
            "effective_to": None,
            "aggregation": "sum",
        }
    )
    report = validate_version_gate(
        {**catalog.metrics, "fixture_metric": Metric.model_validate(payload)}, baseline
    )
    # Closing the open block moves its fingerprint, and that IS a closed-version
    # question — but the block was open in the baseline, so the appended version
    # is what the gate asks for.
    assert "closed_version_semantic_edit" not in {f.rule for f in report.errors}
    assert "semantic_edit_without_new_version" not in {f.rule for f in report.errors}


def test_deleting_a_version_fails(catalog: LoadedCatalog, metric: Metric) -> None:
    """FR-065: deprecated versions stay resolvable for audit forever."""
    baseline = FingerprintBaseline.from_catalog(catalog)
    payload: dict[str, Any] = metric.model_dump(mode="json")
    payload["versions"] = payload["versions"][:2]
    report = validate_version_gate(
        {**catalog.metrics, "fixture_metric": Metric.model_validate(payload)}, baseline
    )
    assert "version_removed" in {f.rule for f in report.errors}


def test_deleting_a_metric_fails(catalog: LoadedCatalog) -> None:
    baseline = FingerprintBaseline.from_catalog(catalog)
    remaining = {k: v for k, v in catalog.metrics.items() if k != "fixture_metric"}
    report = validate_version_gate(remaining, baseline)
    assert "metric_removed" in {f.rule for f in report.errors}


def test_a_gap_between_versions_fails_with_no_baseline(
    catalog: LoadedCatalog, metric: Metric
) -> None:
    """The contract refuses overlaps but permits a hole, and a day inside one
    has no governed definition."""
    payload: dict[str, Any] = metric.model_dump(mode="json")
    payload["versions"][1]["effective_from"] = "2025-07-15"
    report = validate_version_gate({"fixture_metric": Metric.model_validate(payload)})
    assert "version_range_gap" in {f.rule for f in report.errors}


def test_the_authored_catalogs_have_no_gaps(catalog: LoadedCatalog) -> None:
    assert validate_version_gate(catalog).is_valid()


def test_moved_fields_names_what_changed() -> None:
    assert moved_fields({"a": 1, "b": 2}, {"a": 1, "b": 3}) == ("b",)
    assert moved_fields({"a": 1}, {"a": 1, "c": 9}) == ("c",)


# --- T088: whole-release validation and concurrent collisions ---------------


def _merged_copy(tmp_path: Path, mutate: Callable[[str], str]) -> Path:
    root = tmp_path / "catalog"
    shutil.copytree(CATALOG, root)
    target = root / "metrics" / "fixture_stable_metric.yaml"
    target.write_text(mutate(target.read_text(encoding="utf-8")), encoding="utf-8")
    return root


def _unchanged(text: str) -> str:
    return text


def _with_conflict_markers(text: str) -> str:
    markers = (
        "<<<<<<< HEAD",
        "name: a",
        "=======",
        "name: b",
        ">>>>>>> other",
    )
    return text + "\n" + "\n".join(markers) + "\n"


def _with_unknown_kind(text: str) -> str:
    return text.replace("kind: metric", "kind: nonsense")


_APPENDED_BLOCK = """
  - version: 2
    effective_from: 2026-01-01
    source_view: semantic.fixture_daily
    grain: date x product
    aggregation: sum
    additivity: additive
    unit: events
    time_dimension: date
    calculation_basis: Eventos registrados no dia, definicao {tag}.
    content:
      lang: pt-BR
      label: Eventos do aplicativo
      description: Eventos registrados no dia.
"""


def test_two_branches_appending_version_2_merge_cleanly_and_fail_validation(
    tmp_path: Path,
) -> None:
    """Quickstart Scenario 18. Git sees two additions and takes both; the result
    is a catalog that merged without a conflict and is invalid."""

    def merge(text: str) -> str:
        head, _, tail = text.partition("source_availability:")
        both = _APPENDED_BLOCK.format(tag="a") + _APPENDED_BLOCK.format(tag="b")
        return head.rstrip("\n") + "\n" + both + "source_availability:" + tail

    root = _merged_copy(tmp_path, merge)
    report = detect_version_collisions(root)
    rules = {f.rule for f in report.errors}
    assert "concurrent_version_collision" in rules
    assert "version_ranges_overlap" in rules
    assert any("fixture_stable_metric" in f.message for f in report.errors)

    validation = validate_release(root, commit="merge-commit", on=ON)
    assert not validation.valid
    assert validation.commit == "merge-commit"


def test_an_unresolved_conflict_marker_is_a_finding_not_a_parse_error(
    tmp_path: Path,
) -> None:
    root = _merged_copy(tmp_path, _with_conflict_markers)
    report = detect_version_collisions(root)
    assert "unresolved_merge_conflict" in {f.rule for f in report.errors}


def test_the_production_release_validates_atomically() -> None:
    """One verdict for the whole tree, from every layer at once.

    Run against the production catalog rather than a fixture, because only a
    real release carries the complete governed message registry — a miniature
    fixture declares the handful of codes its own rows reach, and FR-074 asks
    for all of them.
    """
    validation = validate_release(PRODUCTION, commit="head", on=ON)
    assert validation.valid, validation.report.render()


def test_a_fixture_release_fails_only_on_its_incomplete_message_registry(
    tmp_path: Path,
) -> None:
    """The fixture catalogs are not releases, and the report says exactly why."""
    root = _merged_copy(tmp_path, _unchanged)
    validation = validate_release(root, commit="fixture-commit", on=ON)
    assert {f.rule for f in validation.errors} == {"publishable_code_without_message"}


def test_a_release_that_does_not_load_reports_rather_than_raises(tmp_path: Path) -> None:
    """Atomic validation must produce a verdict; an exception is not one."""
    root = _merged_copy(tmp_path, _with_unknown_kind)
    validation = validate_release(root, commit="broken", on=ON)
    assert not validation.valid
    assert "release_does_not_load" in {f.rule for f in validation.errors}
