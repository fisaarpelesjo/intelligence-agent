"""Deprecation boundaries — T089, T090 (FR-036, FR-061 to FR-064).

Quickstart Scenario 16, run through the real pipeline against
``tests/fixtures/deprecated_catalog/``, where the boundary is 2026-06-01.

The four dated outcomes, in order: annotated before, refused on and after,
segmented across, and refused outright when a comparison would need the missing
half. Plus the two rules that are easy to state and easy to lose in a refactor:

* a replacement is **disclosed, never substituted** — no figure, no rewritten
  request, and the answer is still about the metric that was asked for;
* a replacement the requester is not authorised for is **not named at all**,
  because naming it would leak that the two metrics are related.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.contracts.audit_event import EvidenceKind
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode
from semantic_catalog.freshness.external import FreshnessSnapshot, load_snapshot
from semantic_catalog.loader.bundle import Bundle, build_bundle
from semantic_catalog.resolution.deprecation import (
    BoundaryRelation,
    boundary_relation,
    continuation_version,
    deprecation_segments,
)
from semantic_catalog.validation.decision import (
    CatalogDecision,
    CatalogValidationRequest,
    Comparison,
    DateRange,
)
from semantic_catalog.validation.disclosure import PROTECTS_SOURCE_METADATA
from semantic_catalog.validation.pipeline import evaluate

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "deprecated_catalog"
CATALOG = FIXTURES / "catalog"
COMMIT = "fixture0"
ON = date(2026, 8, 11)
BOUNDARY = date(2026, 6, 1)


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


def _check(
    bundle: Bundle,
    snapshot: FreshnessSnapshot,
    metric_id: str,
    start: date,
    end: date,
    *,
    access: tuple[str, ...] = ("standard",),
    scope: str = "default",
    comparison: Comparison | None = None,
) -> CatalogDecision:
    return evaluate(
        CatalogValidationRequest(
            metrics=(metric_id,),
            sources=("fixture_source",),
            date_range=DateRange(start=start, end=end),
            requester_access=access,
            comparison=comparison,
        ),
        bundle,
        principal_type=PrincipalType.USER,
        authorization_scope=scope,
        on=ON,
        snapshot=snapshot,
    )


# --- pure boundary arithmetic ----------------------------------------------


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (date(2026, 5, 1), date(2026, 5, 31), BoundaryRelation.BEFORE),
        (date(2026, 5, 31), date(2026, 5, 31), BoundaryRelation.BEFORE),
        (BOUNDARY, BOUNDARY, BoundaryRelation.AFTER),
        (date(2026, 6, 1), date(2026, 6, 30), BoundaryRelation.AFTER),
        (date(2026, 5, 31), BOUNDARY, BoundaryRelation.SPANS),
        (date(2026, 5, 1), date(2026, 6, 30), BoundaryRelation.SPANS),
    ],
)
def test_the_boundary_day_is_the_first_deprecated_day(
    start: date, end: date, expected: BoundaryRelation
) -> None:
    """Off by one here answers a day with no governed definition."""
    assert boundary_relation(BOUNDARY, start, end) is expected


def test_a_crossing_range_splits_into_an_available_and_an_unavailable_half() -> None:
    segments = deprecation_segments(BOUNDARY, date(2026, 5, 1), date(2026, 6, 30))
    assert [(s.start, s.end, s.available) for s in segments] == [
        (date(2026, 5, 1), date(2026, 5, 31), True),
        (BOUNDARY, date(2026, 6, 30), False),
    ]


def test_a_continuation_version_is_authored_never_inferred(bundle: Bundle) -> None:
    assert continuation_version(bundle.internal.metrics["fixture_metric"]) is None
    assert continuation_version(bundle.internal.metrics["fixture_continued_metric"]) == 2


# --- the four dated outcomes ------------------------------------------------


def test_a_period_before_the_boundary_is_allowed_and_annotated(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    decision = _check(bundle, snapshot, "fixture_metric", date(2026, 5, 1), date(2026, 5, 31))
    assert decision.outcome is Outcome.ALLOW_WITH_CAVEAT
    assert decision.reason_code is ReasonCode.DEPRECATED_METRIC


def test_a_period_on_or_after_the_boundary_is_refused(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    decision = _check(bundle, snapshot, "fixture_metric", BOUNDARY, date(2026, 6, 30))
    assert decision.outcome is Outcome.DENY
    assert decision.reason_code is ReasonCode.METRIC_DEPRECATED_FOR_PERIOD
    assert decision.subject.id == "fixture_metric"


def test_a_crossing_range_is_segmented_not_shortened(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    decision = _check(bundle, snapshot, "fixture_metric", date(2026, 5, 1), date(2026, 6, 30))
    assert decision.outcome is Outcome.ALLOW_WITH_CAVEAT
    assert decision.reason_code is ReasonCode.SPANS_DEPRECATION_BOUNDARY
    unavailable = [
        limitation
        for limitation in decision.limitations
        if limitation.code == ReasonCode.SPANS_DEPRECATION_BOUNDARY.value
    ]
    assert len(unavailable) == 1
    assert unavailable[0].applies_to.startswith("fixture_metric:2026-06-01..2026-06-30")


def test_a_comparison_needing_the_deprecated_half_is_refused(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """FR-063: refused rather than silently shortened to the available part."""
    decision = _check(
        bundle,
        snapshot,
        "fixture_metric",
        date(2026, 5, 1),
        date(2026, 6, 30),
        comparison=Comparison(
            kind="previous_period",
            baseline_range=DateRange(start=date(2026, 4, 1), end=date(2026, 4, 30)),
        ),
    )
    assert decision.outcome is Outcome.DENY
    assert decision.reason_code is ReasonCode.COMPARISON_REQUIRES_DEPRECATED_PERIOD


def test_a_comparison_entirely_before_the_boundary_is_not_refused(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """The refusal is about the missing definition, not about comparing at all."""
    decision = _check(
        bundle,
        snapshot,
        "fixture_metric",
        date(2026, 5, 1),
        date(2026, 5, 31),
        comparison=Comparison(
            kind="previous_period",
            baseline_range=DateRange(start=date(2026, 4, 1), end=date(2026, 4, 30)),
        ),
    )
    assert decision.outcome is Outcome.ALLOW_WITH_CAVEAT
    assert decision.reason_code is ReasonCode.DEPRECATED_METRIC


def test_a_governed_continuation_version_reopens_the_post_boundary_period(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """FR-062. Somebody appended the continuation deliberately; nothing inferred it."""
    decision = _check(bundle, snapshot, "fixture_continued_metric", BOUNDARY, date(2026, 6, 30))
    assert decision.outcome is Outcome.ALLOW_WITH_CAVEAT
    assert decision.reason_code is ReasonCode.DEPRECATED_METRIC


# --- replacement disclosure -------------------------------------------------


def test_the_replacement_is_disclosed_as_guidance(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    decision = _check(bundle, snapshot, "fixture_metric", BOUNDARY, date(2026, 6, 30))
    assert any(
        "replacement=fixture_replacement" in limitation.applies_to
        for limitation in decision.limitations
    )


def test_the_replacement_is_never_substituted(bundle: Bundle, snapshot: FreshnessSnapshot) -> None:
    """The decision stays about the metric that was asked for. No evidence ref,
    no segment and no subject names the replacement as the thing answered."""
    decision = _check(bundle, snapshot, "fixture_metric", BOUNDARY, date(2026, 6, 30))
    assert decision.subject.id == "fixture_metric"
    assert decision.outcome is Outcome.DENY
    assert all("fixture_replacement" not in ref.id for ref in decision.evidence_refs)
    assert decision.segments == ()
    assert decision.answerable_subset == ()


def test_an_unauthorised_replacement_is_not_named(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """``fixture_pointer_metric`` points at a restricted metric. A standard
    requester gets the refusal and learns nothing about the relationship."""
    decision = _check(bundle, snapshot, "fixture_pointer_metric", BOUNDARY, date(2026, 6, 30))
    assert decision.reason_code is ReasonCode.METRIC_DEPRECATED_FOR_PERIOD
    rendered = decision.message_pt_br + " ".join(
        limitation.applies_to + limitation.message_pt_br for limitation in decision.limitations
    )
    assert "fixture_guarded_metric" not in rendered


def test_the_refusal_names_the_metric_and_the_period(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """SC-004: no generic refusals. The governed message carries both."""
    decision = _check(bundle, snapshot, "fixture_metric", BOUNDARY, date(2026, 6, 30))
    assert "fixture_metric" in decision.message_pt_br
    assert "2026-06-30" in decision.message_pt_br


# --- nothing historical was mutated ----------------------------------------


def test_deprecation_deleted_no_historical_definition(bundle: Bundle) -> None:
    """FR-061. The block is still there, unchanged, answering its own period."""
    metric = bundle.internal.metrics["fixture_metric"]
    assert [v.version for v in metric.versions] == [1]
    assert metric.versions[0].effective_from == date(2026, 1, 1)
    assert metric.versions[0].effective_to is None


# --- evidence discloses only what the request stood on ----------------------
#
# Both regressions below were found by this fixture, which is the first catalog
# where several metrics share one source and one of them is restricted.


def test_evidence_cites_coverage_for_the_requested_metrics_only(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """A snapshot carries rows for every metric on a source. Citing them all
    would tell the requester which other metrics that source feeds — including
    ``fixture_guarded_metric``, which they may not see."""
    decision = _check(bundle, snapshot, "fixture_replacement", BOUNDARY, date(2026, 6, 30))
    cited = {
        ref.id.split(":", 1)[0]
        for ref in decision.evidence_refs
        if ref.kind is EvidenceKind.COVERAGE_WINDOW
    }
    assert cited == {"fixture_replacement"}, sorted(cited)


def test_an_authorisation_refusal_cites_the_release_and_nothing_else(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """A resolved version set is a shape. Listing it on a refusal would tell a
    requester who may not see the metric how many times it has been redefined."""
    decision = _check(
        bundle,
        snapshot,
        "fixture_guarded_metric",
        date(2026, 5, 1),
        date(2026, 5, 31),
        access=("standard",),
    )
    assert decision.reason_code is ReasonCode.ACCESS_TAG_SCOPE_MISMATCH
    assert decision.reason_code in PROTECTS_SOURCE_METADATA
    assert [ref.kind for ref in decision.evidence_refs] == [EvidenceKind.CATALOG_RELEASE]
    assert decision.freshness == ()
    assert decision.limitations == ()
