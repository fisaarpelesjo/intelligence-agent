"""Auto-degradation is forbidden — T070 (FR-022; quickstart Scenario 6d).

**No code path answers a multi-source request by dropping a stale required
source and returning the remainder.** A narrower result is never returned in
place of the requested comparison.

The failure this guards against is the most tempting one in the whole feature.
Two of three sources are healthy; returning their answer feels helpful, and the
output is a real number computed from real data. It is also **not the comparison
that was asked for**, and nothing in it says so. The reader takes a two-source
figure as a three-source one.

So the rule is blunt: the request as asked is denied, and the healthy sources may
only be **named**. The subset is disclosure, never a payload — no window, no
figure, no partial result travels with it.
"""

from __future__ import annotations

import io
import tokenize
from datetime import date
from pathlib import Path

import pytest

from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode
from semantic_catalog.freshness.external import load_snapshot
from semantic_catalog.loader.bundle import Bundle, build_bundle
from semantic_catalog.validation.decision import (
    CatalogDecision,
    CatalogValidationRequest,
    DateRange,
)
from semantic_catalog.validation.pipeline import evaluate

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CATALOG = FIXTURES / "decision_matrix" / "catalog"
FRESHNESS = FIXTURES / "freshness"
SRC = Path(__file__).resolve().parents[2] / "src" / "semantic_catalog"

ON = date(2026, 8, 11)
WINDOW = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))


@pytest.fixture(scope="module")
def bundle() -> Bundle:
    return build_bundle(
        CATALOG,
        current_commit="fixture0",
        on=ON,
        source_commits={"app_a": "fixture0", "store_a": "fixture0"},
    )


def _cross_source(bundle: Bundle, fixture: str) -> CatalogDecision:
    return evaluate(
        CatalogValidationRequest(
            metrics=("cross_source_metric",),
            sources=("app_a", "store_a"),
            date_range=WINDOW,
            requester_access=("standard",),
        ),
        bundle,
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        on=ON,
        snapshot=load_snapshot(FRESHNESS / fixture),
    )


def test_one_stale_required_source_denies_the_whole_request(bundle: Bundle) -> None:
    decision = _cross_source(bundle, "one_source_beyond_tolerance.yaml")
    assert decision.outcome is Outcome.DENY
    assert decision.reason_code is ReasonCode.SOURCE_BEYOND_TOLERANCE
    assert decision.subject.id == "store_a"


def test_the_healthy_remainder_is_disclosed_and_is_still_a_denial(bundle: Bundle) -> None:
    decision = _cross_source(bundle, "one_source_beyond_tolerance.yaml")
    assert decision.answerable_subset == ("app_a",)
    assert decision.outcome is Outcome.DENY, "a subset never converts a denial into a result"


def test_the_disclosure_carries_no_window_and_no_figure(bundle: Bundle) -> None:
    """Nothing in the denial can be mistaken for the narrower answer."""
    decision = _cross_source(bundle, "one_source_beyond_tolerance.yaml")
    assert decision.comparable_window is None
    assert decision.segments == ()
    assert all(s in bundle.internal.sources for s in decision.answerable_subset)


def test_the_same_request_allows_when_every_required_source_is_healthy(
    bundle: Bundle,
) -> None:
    """Proves the denial is about the stale source, not about the request shape."""
    decision = _cross_source(bundle, "complete.yaml")
    assert decision.outcome is not Outcome.DENY
    assert decision.answerable_subset == ()


def test_no_module_narrows_a_request_by_dropping_a_required_source() -> None:
    """A structural guard, because the tempting implementation is a one-liner.

    Scans executable code — comments and docstrings stripped — for the shapes a
    degradation would take: removing a source from the request, or re-running
    the pipeline against a reduced source list.
    """
    suspicious = ("request.sources.remove", "sources.discard", "retry_without", "fallback_sources")
    for path in sorted(SRC.rglob("*.py")):
        tokens = tokenize.generate_tokens(io.StringIO(path.read_text(encoding="utf-8")).readline)
        code = " ".join(
            tok.string for tok in tokens if tok.type not in (tokenize.COMMENT, tokenize.STRING)
        )
        for shape in suspicious:
            assert shape not in code, f"{path.name}: {shape}"


def test_the_denial_reports_every_source_that_was_asked_for(bundle: Bundle) -> None:
    """The evaluation covers the request as asked, never a narrowed copy of it.

    A degradation would leave a decision whose evidence and disclosure describe
    fewer sources than the caller named. Here the stale one is named as the
    subject and the healthy one as disclosure — both present, neither dropped.
    """
    decision = _cross_source(bundle, "one_source_beyond_tolerance.yaml")
    mentioned = {decision.subject.id, *decision.answerable_subset}
    assert mentioned == {"app_a", "store_a"}
