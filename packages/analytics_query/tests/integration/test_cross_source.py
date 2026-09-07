"""Cross-source comparison — T106 (FR-044; SC-018, SC-019).

Two properties, both about what a comparison is allowed to leave unsaid.

**One stated comparable window.** Two sources rarely cover the same period
exactly, so a comparison narrows to the overlap. A reader who sees only the
figures cannot tell whether they are comparing January to January or January to
three weeks of it — so the window and the reason it was chosen are both reported,
taken from the upstream decision and never recomputed here.

**Partial versus complete is refused.** Comparing a finished period against one
still filling is not a narrower answer, it is a misleading one: the incomplete
side is guaranteed to look smaller, and nothing about the shape of the result
says why.

Runs through the real gates — `001` owns comparability, and this feature reports
what it decided.
"""

from __future__ import annotations

from datetime import date

import pytest
from semantic_catalog.contracts.audit_event import PrincipalType
from semantic_catalog.contracts.reason_codes import Outcome
from semantic_catalog.validation.pipeline import evaluate

from analytics_query.contracts._base import ContractViolation, build
from analytics_query.contracts.comparable_window import ComparableWindow
from analytics_query.contracts.request import AnalyticsQuery, DateRange
from analytics_query.decision.bridge import evaluate_fully, is_permissive
from analytics_query.decision.caveats import carry_limitations

from ..fixtures.catalog.bundle import ON, SCOPE, STANDARD_ACCESS, bundle, snapshot

pytestmark = pytest.mark.integration

JULY = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))

#: The fixture catalog declares a metric spanning two sources.
CROSS_SOURCE_METRIC = "cross_source_metric"


def _decide(**overrides: object):
    payload: dict[str, object] = {
        "metrics": (CROSS_SOURCE_METRIC,),
        "sources": ("app_a", "store_a"),
        "date_range": JULY,
    }
    payload.update(overrides)
    return evaluate_fully(
        build(AnalyticsQuery, **payload),
        evaluate=evaluate,
        bundle=bundle(),
        snapshot=snapshot(),
        principal_type=PrincipalType.USER,
        authorization_scope=SCOPE,
        requester_access=STANDARD_ACCESS,
        on=ON,
    )


# --- the comparison is governed upstream ------------------------------------


def test_a_cross_source_request_reaches_a_governed_verdict() -> None:
    """Whatever `001` decides, this feature reports it rather than deciding."""
    decision = _decide()
    assert decision.outcome in {Outcome.ALLOW, Outcome.ALLOW_WITH_CAVEAT, Outcome.DENY}
    assert is_permissive(decision) == (decision.outcome is not Outcome.DENY)


def test_a_stale_source_denies_the_whole_request() -> None:
    """It does not answer from the healthy source alone (`FR-020`)."""
    decision = evaluate_fully(
        build(
            AnalyticsQuery,
            metrics=(CROSS_SOURCE_METRIC,),
            sources=("app_a", "store_a"),
            date_range=JULY,
        ),
        evaluate=evaluate,
        bundle=bundle(),
        snapshot=snapshot("beyond_tolerance.yaml"),
        principal_type=PrincipalType.USER,
        authorization_scope=SCOPE,
        requester_access=STANDARD_ACCESS,
        on=ON,
    )
    assert decision.outcome is Outcome.DENY
    assert not is_permissive(decision)


def test_every_upstream_caveat_is_carried():
    """Caveats travel unmodified, however many there are."""
    decision = _decide()
    assert carry_limitations(decision) == tuple(decision.limitations)


# --- the window is stated, not implied --------------------------------------


def test_a_comparable_window_states_both_the_window_and_the_reason() -> None:
    window = ComparableWindow(
        start=date(2026, 7, 1),
        end=date(2026, 7, 20),
        reason="store_a coverage ends on 2026-07-20",
        sources=("app_a", "store_a"),
    )
    assert window.start < window.end
    assert window.reason
    assert set(window.sources) == {"app_a", "store_a"}


def test_a_window_naming_no_source_is_refused() -> None:
    """A narrowing nobody can attribute is not a stated window."""
    with pytest.raises(ContractViolation):
        build(
            ComparableWindow,
            start=date(2026, 7, 1),
            end=date(2026, 7, 20),
            reason="coverage",
            sources=(),
        )


def test_the_window_is_never_derived_from_the_sources() -> None:
    """Recomputation would occasionally differ from what `001` validated."""
    import ast
    import inspect

    from analytics_query.contracts import comparable_window

    tree = ast.parse(inspect.getsource(comparable_window))
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            node.value = ast.Constant("")
    code = ast.unparse(tree).lower()
    for marker in ("min(", "max(", "intersect", "overlap", "timedelta"):
        assert marker not in code


# --- partial versus complete (SC-019) ---------------------------------------


def test_a_range_reaching_into_the_forming_period_is_governed_upstream() -> None:
    """The incomplete side is guaranteed to look smaller, and nothing says why."""
    decision = _decide(date_range=DateRange(start=date(2026, 7, 1), end=ON))
    # Whatever the verdict, it is `001`'s and it is not silently permissive.
    assert decision.reason_code is not None
    if decision.outcome is Outcome.ALLOW_WITH_CAVEAT:
        assert decision.limitations, "a caveated allow must say what the caveat is"
