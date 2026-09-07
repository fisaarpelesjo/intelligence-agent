"""Reproducible historical queries — T108 (FR-018, FR-067, FR-068; SC-015, SC-016).

Three properties that together make a historical figure trustworthy.

**The as-of pin.** Re-issuing a query with the same pin resolves the same metric
versions, so the figure is computed under the definition that was in force then
— not under whatever the definition has since become.

**Segmentation, never blending.** A range crossing a definition change returns
one figure per version. A blended number is arithmetic over two different
questions, and it looks exactly like a single answer.

**Stability from revisions, not storage.** Identical values on re-issue are a
claim about unchanged data revisions, verified by comparing them — never a
replay of a stored result, because a cache would make the two indistinguishable
while changing what "identical" means.
"""

from __future__ import annotations

from datetime import date

import pytest
from semantic_catalog.contracts.audit_event import PrincipalType
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode
from semantic_catalog.validation.pipeline import evaluate

from analytics_query.contracts._base import build
from analytics_query.contracts.request import AnalyticsQuery, DateRange
from analytics_query.decision.bridge import to_catalog_request
from analytics_query.decision.revision_stability import Stability, compare_revisions
from analytics_query.identity.normalize import derive_identity

from ..fixtures.catalog.bundle import (
    ALLOWED_METRIC,
    ALLOWED_SOURCE,
    ON,
    SCOPE,
    STANDARD_ACCESS,
    bundle,
    snapshot,
)

pytestmark = pytest.mark.integration

JULY = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))
PINS = {"policy_version": "p-fixture", "catalog_release_id": "r-fixture"}


def _request(**overrides: object) -> AnalyticsQuery:
    payload: dict[str, object] = {
        "metrics": (ALLOWED_METRIC,),
        "sources": (ALLOWED_SOURCE,),
        "date_range": JULY,
    }
    payload.update(overrides)
    return build(AnalyticsQuery, **payload)


def _decide(request: AnalyticsQuery):
    return evaluate(
        to_catalog_request(request, requester_access=STANDARD_ACCESS),
        bundle(),
        principal_type=PrincipalType.USER,
        authorization_scope=SCOPE,
        on=ON,
        snapshot=snapshot(),
    )


# --- the as-of pin (FR-018) --------------------------------------------------


def test_the_same_request_re_issued_resolves_identically() -> None:
    first, second = _decide(_request()), _decide(_request())
    assert first.outcome is second.outcome
    assert first.reason_code is second.reason_code


def test_the_as_of_pin_participates_in_the_identity() -> None:
    """Two different pins are two different questions."""
    pinned = derive_identity(_request(as_of=date(2026, 6, 30)), **PINS)
    unpinned = derive_identity(_request(), **PINS)
    assert pinned != unpinned


def test_the_identity_is_stable_across_re_issues() -> None:
    assert derive_identity(_request(), **PINS) == derive_identity(_request(), **PINS)


def test_a_re_issue_with_a_different_release_is_a_different_identity() -> None:
    """A figure computed under a different catalog release is a different claim."""
    base = derive_identity(_request(), **PINS)
    other = derive_identity(_request(), policy_version="p-fixture", catalog_release_id="r-other")
    assert base != other


# --- segmentation, never blending (SC-016) ----------------------------------


def test_a_range_crossing_a_definition_change_is_governed_upstream() -> None:
    """`001` owns version resolution; this feature never blends."""
    wide = _decide(_request(date_range=DateRange(start=date(2026, 1, 1), end=date(2026, 7, 31))))
    assert wide.reason_code is not None
    if wide.outcome is Outcome.ALLOW_WITH_CAVEAT:
        codes = {limitation.code for limitation in wide.limitations}
        assert codes, "a caveated allow must say what the caveat is"


def test_no_module_blends_across_versions() -> None:
    """Segmentation is reported; a blended figure is never computed."""
    import ast
    from pathlib import Path

    import analytics_query

    src = Path(analytics_query.__file__).parent
    for path in sorted(src.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                assert "blend" not in node.name.lower(), f"{path.relative_to(src)}: {node.name}"


# --- stability from revisions, not storage (FR-067, FR-068) -----------------


def test_unchanged_revisions_promise_identical_values() -> None:
    verdict = compare_revisions({ALLOWED_SOURCE: "rev-1"}, {ALLOWED_SOURCE: "rev-1"})
    assert verdict.stability is Stability.REPRODUCIBLE
    assert verdict.values_are_reproducible


def test_a_restatement_is_reported_rather_than_hidden() -> None:
    """A silently different figure that looks like the old one is the failure."""
    verdict = compare_revisions({ALLOWED_SOURCE: "rev-1"}, {ALLOWED_SOURCE: "rev-2"})
    assert verdict.stability is Stability.RESTATED
    assert verdict.reason_code is ReasonCode.PERIOD_RESTATED
    assert verdict.changed_sources == (ALLOWED_SOURCE,)


def test_stability_never_consults_a_stored_result() -> None:
    """Identical values come from the pin and the revisions, not from a cache."""
    import ast
    import inspect

    from analytics_query.decision import revision_stability

    tree = ast.parse(inspect.getsource(revision_stability))
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            node.value = ast.Constant("")
    code = ast.unparse(tree).lower()
    for marker in ("cache", "stored", "persist", "load_result"):
        assert marker not in code


def test_an_unresolvable_revision_is_undetermined_not_reproducible() -> None:
    """Two unknowns are not evidence of sameness."""
    verdict = compare_revisions({ALLOWED_SOURCE: None}, {ALLOWED_SOURCE: None})
    assert verdict.stability is Stability.UNDETERMINED
    assert not verdict.values_are_reproducible
