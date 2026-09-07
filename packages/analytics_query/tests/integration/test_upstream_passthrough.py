"""Upstream passthrough — T067 (FR-003, FR-004, FR-015, FR-017; SC-008).

A denial from gates 1, 2, 4, 5 or 6 reaches the caller carrying **`001`'s own
reason code**, never a `002` restatement.

The distinction matters more than it looks. If this feature re-coded an upstream
refusal, two things would break at once: the caller could no longer tell whether
a metric is undeclared or merely unavailable to them, and `001` could change a
code without `002` noticing it had drifted. Passing the code through means there
is exactly one vocabulary for governance refusals, and it belongs upstream.

Existence and lifecycle (`FR-003`, `FR-004`) are the clearest cases: this feature
holds no list of metrics and no lifecycle rule, so it *cannot* answer those
questions itself even if someone wanted it to.
"""

from __future__ import annotations

from datetime import date

import pytest
from semantic_catalog.contracts.audit_event import PrincipalType
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode

from analytics_query.contracts._base import build
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.contracts.request import AnalyticsQuery, DateRange
from analytics_query.decision.caveats import carry_limitations, has_caveats, merge_limitations
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

#: One denial per non-authorisation gate this feature must not restate.
UPSTREAM_DENIALS = [
    ReasonCode.METRIC_NOT_GOVERNED,
    ReasonCode.METRIC_PENDING,
    ReasonCode.DIMENSION_NOT_ALLOWED_FOR_METRIC,
    ReasonCode.SOURCE_NOT_GOVERNED,
    ReasonCode.METRIC_NOT_AVAILABLE_FOR_SOURCE,
]


def _refuse(code: ReasonCode) -> PipelineRefusal:
    def evaluate(_request: object, _bundle: object, **_kwargs: object) -> object:
        return decision(outcome=Outcome.DENY, reason_code=code)

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
            required_sources=frozenset({"google_play"}),
        )
    return caught.value


@pytest.mark.parametrize("code", UPSTREAM_DENIALS, ids=lambda c: c.value)
def test_the_upstream_code_passes_through_verbatim(code: ReasonCode) -> None:
    refusal = _refuse(code)
    assert refusal.code is code
    assert isinstance(refusal.code, ReasonCode)


@pytest.mark.parametrize("code", UPSTREAM_DENIALS, ids=lambda c: c.value)
def test_the_refusal_is_never_recoded_into_the_002_namespace(code: ReasonCode) -> None:
    """One vocabulary for governance refusals, and it belongs upstream."""
    refusal = _refuse(code)
    assert not isinstance(refusal.code, AnalyticsReasonCode)
    assert refusal.code.value not in {c.value for c in AnalyticsReasonCode}


@pytest.mark.parametrize("code", UPSTREAM_DENIALS, ids=lambda c: c.value)
def test_an_upstream_denial_stops_before_any_cost(code: ReasonCode) -> None:
    assert _refuse(code).stage == "upstream"


def test_this_feature_holds_no_metric_or_lifecycle_knowledge() -> None:
    """`FR-003`/`FR-004` cannot be answered here even deliberately."""
    from pathlib import Path

    import analytics_query

    src = Path(analytics_query.__file__).parent
    for path in sorted(src.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for marker in ("KNOWN_METRICS", "METRIC_REGISTRY", "LIFECYCLE_STATES", "is_published"):
            assert marker not in text, f"{path.relative_to(src)} holds catalog knowledge"


# --- caveats survive the journey (FR-017) -----------------------------------


def test_limitations_are_carried_unmodified() -> None:
    from semantic_catalog.validation.decision import Limitation

    limitations = (
        Limitation(code="SPANS_DEFINITION_CHANGE", message_pt_br="a", applies_to="installs"),
        Limitation(code="PARTIAL_PERIOD", message_pt_br="b", applies_to="installs"),
    )
    allowed = decision(
        outcome=Outcome.ALLOW_WITH_CAVEAT,
        reason_code=ReasonCode.SPANS_DEFINITION_CHANGE,
        limitations=limitations,
    )

    carried = carry_limitations(allowed)
    assert carried == limitations
    assert [c.code for c in carried] == ["SPANS_DEFINITION_CHANGE", "PARTIAL_PERIOD"]
    assert has_caveats(allowed)


def test_no_caveat_is_summarised_away() -> None:
    from semantic_catalog.validation.decision import Limitation

    many = tuple(
        Limitation(code=f"C{i}", message_pt_br=f"m{i}", applies_to="installs") for i in range(5)
    )
    assert len(carry_limitations(decision(limitations=many))) == 5


def test_execution_caveats_append_after_upstream_ones() -> None:
    """Order tells a reader which qualification came from where."""
    from semantic_catalog.validation.decision import Limitation

    upstream = (Limitation(code="UP", message_pt_br="u", applies_to="installs"),)
    ours = (Limitation(code="OURS", message_pt_br="o", applies_to="installs"),)
    merged = merge_limitations(upstream, ours)
    assert [m.code for m in merged] == ["UP", "OURS"]


def test_a_resembling_execution_caveat_is_not_deduplicated_away() -> None:
    from semantic_catalog.validation.decision import Limitation

    same = Limitation(code="X", message_pt_br="m", applies_to="installs")
    assert len(merge_limitations((same,), (same,))) == 2
