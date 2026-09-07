"""As-of stability and overlapping versions — T094 (FR-034, FR-069).

Quickstart Scenarios 8 and 9. Two properties, and both are about *not* changing:

**A closed period keeps its version.** June 2025 resolved to ``@1`` before
version 4 was appended and resolves to ``@1`` afterwards. The failure this
prevents is the one nobody notices: a figure published months ago quietly
recomputed under a definition that did not exist when it was published.

**An identical request against an identical catalog yields an identical
``decision_id``.** Across processes, across evaluation timestamps, across the
order the caller happened to list the metrics in. That is what makes SC-021
testable rather than aspirational.

Overlapping ranges are rejected at both levels: the ``Metric`` contract refuses
to construct one, and the resolution functions refuse a hand-built sequence the
contract never saw.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.contracts.metric import Metric, MetricVersion
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode
from semantic_catalog.freshness.external import FreshnessSnapshot, load_snapshot
from semantic_catalog.loader.bundle import Bundle, build_bundle
from semantic_catalog.resolution.as_of import (
    OverlappingVersionsError,
    resolve_as_of,
    resolve_version,
    segment,
    segment_versions,
    spans_definition_change,
    uncovered_spans,
)
from semantic_catalog.validation.decision import CatalogValidationRequest, DateRange
from semantic_catalog.validation.pipeline import evaluate, resolved_version_ids

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "versioned_catalog"
CATALOG = FIXTURES / "catalog"
COMMIT = "fixture0"
ON = date(2026, 8, 11)


@pytest.fixture(scope="module")
def bundle() -> Bundle:
    # ADR 0033: `FIXTURES` already points at the fixture's own directory, so `CATALOG`
    # is that catalog -- and it CARRIES an approval naming `fixture0`. This is one of the
    # few places where the comparand actually resolves and decides, so it states the
    # commit per source. `_covers` matches by prefix and fixture0 == fixture0, so the
    # behaviour is unchanged; what changes is that the exercise moves to the new comparand.
    return build_bundle(
        CATALOG,
        current_commit=COMMIT,
        on=ON,
        source_commits={"fixture_source": COMMIT},
    )


@pytest.fixture(scope="module")
def snapshot() -> FreshnessSnapshot:
    return load_snapshot(FIXTURES / "freshness.yaml")


@pytest.fixture(scope="module")
def metric(bundle: Bundle) -> Metric:
    return bundle.internal.metrics["fixture_metric"]


def _request(start: date, end: date, metrics: tuple[str, ...] = ("fixture_metric",)):
    return CatalogValidationRequest(
        metrics=metrics,
        sources=("fixture_source",),
        date_range=DateRange(start=start, end=end),
        requester_access=("standard",),
    )


# --- as-of resolution -------------------------------------------------------


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2025, 1, 1), 1),
        (date(2025, 6, 30), 1),
        (date(2025, 7, 1), 2),
        (date(2025, 9, 30), 2),
        (date(2025, 10, 1), 3),
        (date(2026, 8, 11), 3),
    ],
)
def test_a_date_resolves_to_the_version_in_effect_then(
    metric: Metric, day: date, expected: int
) -> None:
    """Boundary days included: ``effective_from`` is the first day of the new
    definition, ``effective_to`` the last day of the old one."""
    resolved = resolve_as_of(metric, day)
    assert resolved is not None
    assert resolved.version == expected


def test_a_date_before_the_first_version_resolves_to_nothing(metric: Metric) -> None:
    """``None`` is a real answer. Falling back to version 1 would describe a
    period the catalog never claimed to cover."""
    assert resolve_as_of(metric, date(2024, 12, 31)) is None


# --- segmentation -----------------------------------------------------------


def test_a_range_inside_one_version_is_one_segment(metric: Metric) -> None:
    segments = segment(metric, date(2025, 2, 1), date(2025, 3, 31))
    assert [(s.metric_version_id, s.start, s.end) for s in segments] == [
        ("fixture_metric@1", date(2025, 2, 1), date(2025, 3, 31))
    ]
    assert not spans_definition_change(segments)


def test_a_range_crossing_one_change_is_two_segments_never_blended(metric: Metric) -> None:
    segments = segment(metric, date(2025, 6, 1), date(2025, 8, 31))
    assert [(s.metric_version_id, s.start, s.end) for s in segments] == [
        ("fixture_metric@1", date(2025, 6, 1), date(2025, 6, 30)),
        ("fixture_metric@2", date(2025, 7, 1), date(2025, 8, 31)),
    ]
    assert spans_definition_change(segments)
    assert sum(s.days for s in segments) == 92


def test_a_range_crossing_two_changes_is_three_segments(metric: Metric) -> None:
    segments = segment(metric, date(2025, 6, 1), date(2025, 11, 30))
    assert [s.version for s in segments] == [1, 2, 3]
    assert [s.start for s in segments] == [
        date(2025, 6, 1),
        date(2025, 7, 1),
        date(2025, 10, 1),
    ]


def test_segments_are_ordered_deterministically(metric: Metric) -> None:
    """Same input, same order, every time — the decision cites these."""
    first = segment(metric, date(2025, 1, 1), date(2026, 1, 1))
    second = segment(metric, date(2025, 1, 1), date(2026, 1, 1))
    assert first == second
    assert [s.start for s in first] == sorted(s.start for s in first)


def test_days_no_version_covers_are_reported_not_absorbed(metric: Metric) -> None:
    """A day before the first definition is a gap, not version 1's problem."""
    start, end = date(2024, 12, 1), date(2025, 1, 31)
    gaps = uncovered_spans(segment(metric, start, end), start, end)
    assert [(g.start, g.end) for g in gaps] == [(date(2024, 12, 1), date(2024, 12, 31))]


# --- overlapping versions ---------------------------------------------------


def _version(number: int, start: date, end: date | None) -> MetricVersion:
    return MetricVersion.model_validate(
        {
            "version": number,
            "effective_from": start,
            "effective_to": end,
            "source_view": "semantic.fixture_daily",
            "grain": "date x product",
            "aggregation": "sum",
            "additivity": "additive",
            "unit": "sessions",
            "time_dimension": "date",
            "calculation_basis": "Sessoes iniciadas no dia.",
            "content": {"lang": "pt-BR", "label": "Sessoes", "description": "Sessoes."},
        }
    )


def test_the_contract_refuses_to_construct_overlapping_versions() -> None:
    with pytest.raises(ValidationError, match="overlap"):
        Metric.model_validate(
            {
                "catalog_schema_version": 1,
                "kind": "metric",
                "name": "overlapping",
                "owner": "fixture_owner",
                "access": "standard",
                "grain_family": "day",
                "versions": [
                    _version(1, date(2025, 1, 1), date(2025, 6, 30)).model_dump(mode="json"),
                    _version(2, date(2025, 6, 1), None).model_dump(mode="json"),
                ],
            }
        )


def test_resolution_refuses_an_overlapping_sequence_it_was_handed() -> None:
    """The contract cannot be the only guard: these functions accept a bare
    sequence, and an overlap would make a historical answer ambiguous."""
    versions = (
        _version(1, date(2025, 1, 1), date(2025, 6, 30)),
        _version(2, date(2025, 6, 1), None),
    )
    with pytest.raises(OverlappingVersionsError):
        resolve_version("overlapping", versions, date(2025, 6, 15))
    with pytest.raises(OverlappingVersionsError):
        segment_versions("overlapping", versions, date(2025, 1, 1), date(2025, 12, 31))


# --- stability --------------------------------------------------------------


def test_a_closed_period_keeps_its_version_when_a_later_one_is_appended(
    metric: Metric,
) -> None:
    """SC-021. Appending version 4 for 2026 must not move June 2025."""
    before = segment(metric, date(2025, 6, 1), date(2025, 6, 30))
    extended = Metric.model_validate(
        {
            **metric.model_dump(mode="json"),
            "versions": [
                *[
                    {**v.model_dump(mode="json"), "effective_to": "2025-12-31"}
                    if v.effective_to is None
                    else v.model_dump(mode="json")
                    for v in metric.versions
                ],
                _version(4, date(2026, 1, 1), None).model_dump(mode="json"),
            ],
        }
    )
    after = segment(extended, date(2025, 6, 1), date(2025, 6, 30))
    assert [s.metric_version_id for s in before] == ["fixture_metric@1"]
    assert [s.metric_version_id for s in after] == ["fixture_metric@1"]


def test_resolved_version_ids_are_as_of_the_range_not_the_newest(bundle: Bundle) -> None:
    """``decision_id`` folds this set in, so taking the newest version would
    make a closed period's identity move whenever the metric was redefined."""
    assert resolved_version_ids(bundle, _request(date(2025, 2, 1), date(2025, 3, 31))) == (
        "fixture_metric@1",
    )
    assert resolved_version_ids(bundle, _request(date(2025, 6, 1), date(2025, 8, 31))) == (
        "fixture_metric@1",
        "fixture_metric@2",
    )


def test_the_same_request_yields_the_same_decision_id_across_runs(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    # ADR 0033: `FIXTURES` already points at the fixture's own directory, so `CATALOG`
    # is that catalog -- and it CARRIES an approval naming `fixture0`. This is one of the
    # few places where the comparand actually resolves and decides, so it states the
    # commit per source. `_covers` matches by prefix and fixture0 == fixture0, so the
    # behaviour is unchanged; what changes is that the exercise moves to the new comparand.
    rebuilt = build_bundle(
        CATALOG,
        current_commit=COMMIT,
        on=ON,
        source_commits={"fixture_source": COMMIT},
    )
    assert rebuilt.release_id == bundle.release_id

    def run(target: Bundle) -> str:
        return evaluate(
            _request(date(2025, 2, 1), date(2025, 3, 31)),
            target,
            principal_type=PrincipalType.USER,
            authorization_scope="default",
            on=ON,
            snapshot=snapshot,
        ).decision_id

    assert run(bundle) == run(rebuilt)


def test_metric_order_does_not_change_the_decision_id(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """The same question asked two ways is one question."""

    def run(metrics: tuple[str, ...]) -> str:
        return evaluate(
            _request(date(2025, 2, 1), date(2025, 3, 31), metrics),
            bundle,
            principal_type=PrincipalType.USER,
            authorization_scope="default",
            on=ON,
            snapshot=snapshot,
        ).decision_id

    assert run(("fixture_metric", "fixture_stable_metric")) == run(
        ("fixture_stable_metric", "fixture_metric")
    )


def test_a_range_crossing_a_change_allows_with_a_caveat_and_carries_segments(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """Quickstart Scenario 8: ALLOW_WITH_CAVEAT, two segments, never blended."""
    decision = evaluate(
        _request(date(2025, 6, 1), date(2025, 8, 31)),
        bundle,
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        on=ON,
        snapshot=snapshot,
    )
    assert decision.outcome is Outcome.ALLOW_WITH_CAVEAT
    assert decision.reason_code is ReasonCode.SPANS_DEFINITION_CHANGE
    assert [s.metric_version_id for s in decision.segments] == [
        "fixture_metric@1",
        "fixture_metric@2",
    ]
    assert "fixture_metric@2" in decision.message_pt_br


def test_a_range_inside_one_version_carries_no_segments(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """Segments are populated only when the range crosses a change
    (decision-contract §2); an unconditional span reads as a narrowed answer."""
    decision = evaluate(
        _request(date(2025, 2, 1), date(2025, 3, 31)),
        bundle,
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        on=ON,
        snapshot=snapshot,
    )
    assert decision.outcome is Outcome.ALLOW
    assert decision.segments == ()
