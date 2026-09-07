"""Unsafe combinations — T084 (FR-029, FR-030, FR-050; quickstart Scenario 5).

Evidence: each unsafe combination is **refused or redirected with a stated
reason**. Not a bare denial — a reader who is told only "no" builds the number
themselves, which is the outcome the catalog exists to prevent.

Two families, and keeping them apart is the point:

**Comparability** (Gate 6) — whether two things may be put side by side at all.
Deny-by-default: a pair no governed rule authorises is refused, because a chart
comparing store-reported downloads with device-recorded sessions is plausible,
confident and wrong.

**Grain and additivity** (Gate 5) — whether an aggregation preserves what the
metric means. Summing a point-in-time rating gives a number no one has ever
seen; mixing a cohort-grained metric with a day-grained one gives a row with no
referent.

Nothing is inferred from similar names, matching grain, matching unit or a
shared source. Every permission here is a rule a human wrote.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from semantic_catalog.comparability.caveats import caveat_limitations, declared_text
from semantic_catalog.comparability.gate import (
    check_comparability,
    find_rule,
    pairs_requiring_a_rule,
)
from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.contracts.comparability import RuleSubject
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode
from semantic_catalog.freshness.external import load_snapshot
from semantic_catalog.loader.bundle import Bundle, build_bundle
from semantic_catalog.provenance.audit_emit import (
    CollectingSink,
    EvaluatedDecision,
    evaluate_and_emit,
)
from semantic_catalog.provenance.revision import load_revisions
from semantic_catalog.validation.decision import CatalogValidationRequest, DateRange

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CATALOG = FIXTURES / "decision_matrix" / "catalog"
FRESHNESS = FIXTURES / "freshness"
REVISIONS = FIXTURES / "revisions"

ON = date(2026, 8, 11)
WINDOW = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))
PRINCIPAL = "prn_" + "u" * 24


@pytest.fixture(scope="module")
def bundle() -> Bundle:
    return build_bundle(
        CATALOG,
        current_commit="fixture0",
        on=ON,
        source_commits={"app_a": "fixture0", "store_a": "fixture0"},
    )


def _run(
    bundle: Bundle,
    *,
    metrics: tuple[str, ...],
    sources: tuple[str, ...],
    access: tuple[str, ...] = ("standard",),
    scope: str = "default",
    aggregate: str | None = None,
    sink: CollectingSink | None = None,
) -> EvaluatedDecision:
    return evaluate_and_emit(
        CatalogValidationRequest(
            metrics=metrics,
            sources=sources,
            date_range=WINDOW,
            requester_access=access,
            aggregate=aggregate,
        ),
        bundle,
        sink or CollectingSink(),
        principal_id=PRINCIPAL,
        principal_type=PrincipalType.USER,
        authorization_scope=scope,
        correlation_id="corr-unsafe",
        on=ON,
        snapshot=load_snapshot(FRESHNESS / "complete.yaml"),
        revisions=load_revisions(REVISIONS / "both_stable.yaml"),
    )


# --- deny-by-default --------------------------------------------------------


def test_a_pair_with_no_governed_rule_is_refused(bundle: Bundle) -> None:
    """Absence of a rule is not permission."""
    result = _run(bundle, metrics=("app_sessions", "cross_source_metric"), sources=("app_a",))
    assert result.decision.outcome is Outcome.DENY
    assert result.decision.reason_code is ReasonCode.COMPARABILITY_RULE_MISSING
    assert result.decision.message_pt_br


def test_a_declared_non_combinable_pair_is_refused_with_its_business_reason(
    bundle: Bundle,
) -> None:
    result = _run(bundle, metrics=("app_sessions", "store_downloads"), sources=("app_a", "store_a"))
    decision = result.decision
    assert decision.outcome is Outcome.DENY
    assert decision.reason_code is ReasonCode.METRICS_NOT_COMPARABLE
    reasons = [limitation.message_pt_br for limitation in decision.limitations]
    assert any("eventos diferentes" in text for text in reasons), reasons


def test_the_refusal_names_the_pair(bundle: Bundle) -> None:
    result = _run(bundle, metrics=("app_sessions", "store_downloads"), sources=("app_a", "store_a"))
    assert "app_sessions" in result.decision.subject.id
    assert "store_downloads" in result.decision.subject.id


# --- reversed operands ------------------------------------------------------


def test_operand_order_does_not_change_the_outcome(bundle: Bundle) -> None:
    """A rule relating A to B governs the request naming B and A."""
    forward = _run(
        bundle, metrics=("app_sessions", "store_downloads"), sources=("app_a", "store_a")
    )
    reversed_ = _run(
        bundle, metrics=("store_downloads", "app_sessions"), sources=("store_a", "app_a")
    )
    assert forward.decision.reason_code is reversed_.decision.reason_code
    assert forward.decision.decision_id == reversed_.decision.decision_id


def test_find_rule_matches_either_operand_order(bundle: Bundle) -> None:
    rules = bundle.internal.comparability_rules
    pairs = pairs_requiring_a_rule(("store_downloads", "app_sessions"), ())
    assert len(pairs) == 1
    assert find_rule(rules, pairs[0]) is not None


# --- permitted with a caveat ------------------------------------------------


def test_a_caveated_pair_is_permitted_and_carries_its_declared_caveat(
    bundle: Bundle,
) -> None:
    """US4 scenario 3: permitted, and labelled with the authored wording."""
    result = _run(bundle, metrics=("app_sessions", "store_rating"), sources=("app_a", "store_a"))
    decision = result.decision
    assert decision.outcome is Outcome.ALLOW_WITH_CAVEAT
    assert decision.reason_code is ReasonCode.COMPARABLE_WITH_CAVEAT
    caveats = [limitation.message_pt_br for limitation in decision.limitations]
    assert any("ordem de grandeza" in text for text in caveats), caveats


def test_the_declared_caveat_is_authored_not_generated(bundle: Bundle) -> None:
    """The rule's caveat, verbatim — never a sentence composed at answer time."""
    rule = bundle.internal.comparability_rules["app_sessions_vs_store_rating"]
    result = _run(bundle, metrics=("app_sessions", "store_rating"), sources=("app_a", "store_a"))
    texts = [limitation.message_pt_br for limitation in result.decision.limitations]
    assert rule.content.caveat in texts


def test_a_caveated_comparison_keeps_complete_provenance(bundle: Bundle) -> None:
    from semantic_catalog.contracts.audit_event import EvidenceKind

    result = _run(bundle, metrics=("app_sessions", "store_rating"), sources=("app_a", "store_a"))
    decision = result.decision
    kinds = {ref.kind for ref in decision.evidence_refs}
    assert decision.freshness
    assert EvidenceKind.FRESHNESS_SNAPSHOT in kinds
    assert EvidenceKind.COVERAGE_WINDOW in kinds
    assert all(
        v.last_successful_update is not None for v in decision.freshness if v.status != "unknown"
    )
    assert decision.limitations


def test_a_combinable_pair_passes_without_a_caveat(bundle: Bundle) -> None:
    """Proves the gate is not refusing everything."""
    result = _run(bundle, metrics=("cross_source_metric",), sources=("app_a", "store_a"))
    assert result.decision.outcome is not Outcome.DENY
    assert result.decision.reason_code is not ReasonCode.COMPARABLE_WITH_CAVEAT


# --- authorisation still wins -----------------------------------------------


def test_an_unauthorised_incomparable_request_refuses_on_authorisation(
    bundle: Bundle,
) -> None:
    """Gate 3 before Gate 6: a refusal must not reveal that two metrics relate."""
    result = _run(
        bundle,
        metrics=("app_sessions", "store_downloads"),
        sources=("app_a", "store_a"),
        access=(),
    )
    assert result.decision.reason_code is ReasonCode.ACCESS_DENIED
    assert result.decision.reason_code is not ReasonCode.METRICS_NOT_COMPARABLE


def test_an_authorisation_refusal_leaks_no_comparability_reason(bundle: Bundle) -> None:
    result = _run(
        bundle,
        metrics=("app_sessions", "store_downloads"),
        sources=("app_a", "store_a"),
        access=(),
    )
    decision = result.decision
    assert decision.limitations == ()
    assert decision.freshness == ()
    assert decision.data_revisions == ()


# --- grain and additivity (Gate 5, FR-050) ----------------------------------


def test_mixed_grain_families_are_refused(bundle: Bundle) -> None:
    result = _run(bundle, metrics=("cohort_retention", "app_sessions"), sources=("app_a",))
    assert result.decision.outcome is Outcome.DENY
    assert result.decision.reason_code is ReasonCode.GRAIN_FAMILY_MISMATCH


def test_summing_a_point_in_time_metric_is_refused(bundle: Bundle) -> None:
    result = _run(bundle, metrics=("store_rating",), sources=("store_a",), aggregate="sum")
    assert result.decision.reason_code is ReasonCode.AGGREGATION_INVALID_FOR_ADDITIVITY
    assert result.decision.subject.id == "store_rating"


def test_summing_a_ratio_is_refused(bundle: Bundle) -> None:
    result = _run(bundle, metrics=("cohort_retention",), sources=("app_a",), aggregate="sum")
    assert result.decision.reason_code is ReasonCode.AGGREGATION_INVALID_FOR_ADDITIVITY


def test_grain_is_checked_before_comparability(bundle: Bundle) -> None:
    """A cohort/day mix is refused on grain, not on a missing comparability rule.

    Both are true of the request; the grain mismatch is the more actionable
    thing to report, and the contracted order says so.
    """
    result = _run(bundle, metrics=("cohort_retention", "app_sessions"), sources=("app_a",))
    assert result.decision.reason_code is ReasonCode.GRAIN_FAMILY_MISMATCH


# --- nothing is inferred ----------------------------------------------------


def test_matching_grain_and_unit_do_not_imply_comparability(bundle: Bundle) -> None:
    """Both day-grained, both counted in events, and still refused."""
    left = bundle.internal.metrics["app_sessions"].versions[0]
    right = bundle.internal.metrics["cross_source_metric"].versions[0]
    assert left.aggregation is right.aggregation
    assert left.additivity is right.additivity
    result = _run(bundle, metrics=("app_sessions", "cross_source_metric"), sources=("app_a",))
    assert result.decision.reason_code is ReasonCode.COMPARABILITY_RULE_MISSING


def test_sharing_a_source_does_not_imply_comparability(bundle: Bundle) -> None:
    result = _run(bundle, metrics=("app_sessions", "cross_source_metric"), sources=("app_a",))
    assert result.decision.outcome is Outcome.DENY


def test_a_rule_for_a_different_pair_does_not_govern_this_one(bundle: Bundle) -> None:
    rules = bundle.internal.comparability_rules
    pairs = pairs_requiring_a_rule(("app_sessions", "cross_source_metric"), ())
    assert find_rule(rules, pairs[0]) is None


# --- the checker itself -----------------------------------------------------


def test_a_single_metric_on_a_single_source_needs_no_rule() -> None:
    assert pairs_requiring_a_rule(("app_sessions",), ("app_a",)) == ()


def test_both_metric_and_source_pairs_are_checked() -> None:
    pairs = pairs_requiring_a_rule(("a", "b"), ("x", "y"))
    assert {p.subject for p in pairs} == {RuleSubject.METRIC_PAIR, RuleSubject.SOURCE_PAIR}


def test_a_denial_outranks_a_caveat_within_the_gate(bundle: Bundle) -> None:
    """A caveat cannot soften a pair the catalog says must not be compared."""
    checks = check_comparability(
        bundle.internal.comparability_rules,
        ("app_sessions", "store_downloads", "store_rating"),
        ("app_a", "store_a"),
    )
    codes = {c.reason_code for c in checks}
    assert ReasonCode.METRICS_NOT_COMPARABLE in codes
    assert ReasonCode.COMPARABLE_WITH_CAVEAT in codes

    result = _run(
        bundle,
        metrics=("app_sessions", "store_downloads", "store_rating"),
        sources=("app_a", "store_a"),
    )
    assert result.decision.reason_code is ReasonCode.METRICS_NOT_COMPARABLE


def test_declared_text_returns_nothing_without_a_rule() -> None:
    checks = check_comparability({}, ("a", "b"), ())
    assert declared_text(checks[0]) is None
    assert caveat_limitations(checks) == ()


def test_a_combinable_rule_contributes_no_limitation(bundle: Bundle) -> None:
    checks = check_comparability(
        bundle.internal.comparability_rules, ("cross_source_metric",), ("app_a", "store_a")
    )
    assert [c.reason_code for c in checks] == [None]
    assert caveat_limitations(checks) == ()


def test_limitations_are_stable_across_runs(bundle: Bundle) -> None:
    first = _run(bundle, metrics=("app_sessions", "store_rating"), sources=("app_a", "store_a"))
    second = _run(bundle, metrics=("app_sessions", "store_rating"), sources=("app_a", "store_a"))
    assert [x.applies_to for x in first.decision.limitations] == [
        x.applies_to for x in second.decision.limitations
    ]


# --- audit ------------------------------------------------------------------


def test_every_unsafe_combination_is_audited(bundle: Bundle) -> None:
    sink = CollectingSink()
    for metrics, sources in [
        (("app_sessions", "store_downloads"), ("app_a", "store_a")),
        (("app_sessions", "cross_source_metric"), ("app_a",)),
        (("app_sessions", "store_rating"), ("app_a", "store_a")),
    ]:
        _run(bundle, metrics=metrics, sources=sources, sink=sink)
    assert sink.count == 3
    assert all(event.reason_code is not None for event in sink.events)
