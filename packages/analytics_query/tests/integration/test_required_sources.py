"""Required-source reduction — T071 (FR-019, FR-020; SC-018).

Two properties that look similar and protect different things.

**`FR-019` — reduction is delegated.** `001` derives which sources a set of
metrics actually requires. This feature does not compute that set, because a
reduction computed here could differ from the catalog's and quietly drop the
source whose staleness would have refused the request.

**`FR-020` — a narrower answer is never substituted.** When a required source is
unavailable, the request refuses. ``answerable_subset`` may be *disclosed* on
that denial so the caller knows what they could ask instead, but it is never
returned as a result. That distinction is the point: a narrower answer arriving
in the shape of the answer asked for is worse than no answer, because nobody
notices.
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest
from semantic_catalog.contracts.audit_event import PrincipalType
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode

import analytics_query
from analytics_query.contracts._base import build
from analytics_query.contracts.request import AnalyticsQuery, DateRange
from analytics_query.decision.bridge import to_catalog_request
from analytics_query.execution.ledger import AuthorizationContext
from analytics_query.execution.ledger_memory import InMemoryExecutionLedger
from analytics_query.pipeline import PipelineRefusal, run_until_evaluation

from ..fixtures.catalog.decisions import decision
from ..fixtures.observations.reader import FixtureObservationReader

pytestmark = pytest.mark.integration

ON = date(2026, 8, 12)
JULY = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))
CONTEXT = AuthorizationContext(
    authorization_scope="tenant-a",
    granted_access_tags=frozenset({"installs:read"}),
    principal_type=PrincipalType.USER.value,
    authorization_policy_pin="authpol-1",
)


# --- FR-019: this feature computes no reduction -----------------------------


def test_the_request_is_translated_without_alteration() -> None:
    request = build(
        AnalyticsQuery,
        metrics=("installs", "sessions"),
        dimensions=("country",),
        sources=("google_play", "ios_app"),
        date_range=JULY,
    )
    translated = to_catalog_request(request, requester_access=("installs:read",))

    assert translated.metrics == ("installs", "sessions")
    assert translated.dimensions == ("country",)
    assert translated.sources == ("google_play", "ios_app")
    assert translated.date_range.start == JULY.start
    assert translated.date_range.end == JULY.end


def test_an_empty_source_set_is_passed_through_empty() -> None:
    """The catalog derives required sources from the metrics; this feature does not.

    Filling the set in here would be the reduction `FR-019` delegates, performed
    in the one place that cannot see the catalog.
    """
    request = build(AnalyticsQuery, metrics=("installs",), date_range=JULY)
    assert to_catalog_request(request, requester_access=()).sources == ()


def test_no_module_derives_required_sources() -> None:
    src = Path(analytics_query.__file__).parent
    for path in sorted(src.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                name = node.name.lower()
                assert "required_source" not in name, f"{path.relative_to(src)}: {node.name}"
                assert "reduce_source" not in name, f"{path.relative_to(src)}: {node.name}"


def test_filter_values_are_not_sent_upstream() -> None:
    """The catalog governs combinations, not which values are selected."""
    from analytics_query.contracts.operators import GovernedOperator
    from analytics_query.contracts.request import GovernedFilter

    request = build(
        AnalyticsQuery,
        metrics=("installs",),
        date_range=JULY,
        filters=(
            build(
                GovernedFilter,
                dimension="country",
                operator=GovernedOperator.EQ,
                values=("BR",),
            ),
        ),
    )
    assert "BR" not in to_catalog_request(request, requester_access=()).model_dump_json()


def test_no_comparison_or_aggregate_is_invented() -> None:
    """`BD-1`: neither is part of this feature's request surface."""
    translated = to_catalog_request(
        build(AnalyticsQuery, metrics=("installs",), date_range=JULY), requester_access=()
    )
    assert translated.comparison is None
    assert translated.aggregate is None


# --- FR-020: a narrower answer is never substituted -------------------------


def _refuse_with_subset(subset: tuple[str, ...]) -> PipelineRefusal:
    def evaluate(_request: object, _bundle: object, **_kwargs: object) -> object:
        return decision(
            outcome=Outcome.DENY,
            reason_code=ReasonCode.SOURCE_BEYOND_TOLERANCE,
            answerable_subset=subset,
        )

    with pytest.raises(PipelineRefusal) as caught:
        run_until_evaluation(
            build(AnalyticsQuery, metrics=("installs",), date_range=JULY),
            evaluate=evaluate,  # type: ignore[arg-type]
            catalog_bundle=object(),  # type: ignore[arg-type]
            ledger=InMemoryExecutionLedger(),
            observations=FixtureObservationReader(),
            context=CONTEXT,
            correlation_id="c-1",
            principal_ref="p-1",
            on=ON,
            catalog_release_id="r-1",
            required_sources=frozenset({"google_play", "ios_app"}),
        )
    return caught.value


def test_an_unavailable_required_source_refuses() -> None:
    """It does not answer from the remainder."""
    refusal = _refuse_with_subset(("google_play",))
    assert refusal.stage == "upstream"
    assert refusal.code is ReasonCode.SOURCE_BEYOND_TOLERANCE


def test_the_answerable_subset_never_arrives_as_a_result() -> None:
    """It rides on the denial as disclosure, and carries no rows or values."""
    refusal = _refuse_with_subset(("google_play",))
    assert refusal.violation.code is ReasonCode.SOURCE_BEYOND_TOLERANCE
    assert not hasattr(refusal, "result")
    assert not hasattr(refusal, "rows")


def test_the_reduction_never_widens_or_narrows_the_request() -> None:
    """What the catalog is asked is what the caller asked."""
    request = build(
        AnalyticsQuery, metrics=("installs",), sources=("google_play", "ios_app"), date_range=JULY
    )
    seen: list[object] = []

    def evaluate(catalog_request: object, _bundle: object, **_kwargs: object) -> object:
        seen.append(catalog_request)
        return decision(outcome=Outcome.DENY, reason_code=ReasonCode.SOURCE_BEYOND_TOLERANCE)

    with pytest.raises(PipelineRefusal):
        run_until_evaluation(
            request,
            evaluate=evaluate,  # type: ignore[arg-type]
            catalog_bundle=object(),  # type: ignore[arg-type]
            ledger=InMemoryExecutionLedger(),
            observations=FixtureObservationReader(),
            context=CONTEXT,
            correlation_id="c-1",
            principal_ref="p-1",
            on=ON,
            catalog_release_id="r-1",
            required_sources=frozenset({"google_play", "ios_app"}),
        )

    asked = seen[0]
    assert asked.sources == ("google_play", "ios_app")  # type: ignore[attr-defined]
    assert asked.metrics == ("installs",)  # type: ignore[attr-defined]
