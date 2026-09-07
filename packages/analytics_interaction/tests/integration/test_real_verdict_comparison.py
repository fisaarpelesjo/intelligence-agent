"""The two-execution route on a **real** catalog verdict — ADR 0016.

Every other comparison suite in this package builds its verdict. This one does
not: the ``CatalogDecision`` here comes out of `001`'s production ``evaluate()``
composition, run against `001`'s own fixture catalog and freshness snapshot, and
the comparable window on it is the one gate 7 computed on the way through.

That is the difference the two ADR 0016 defects made invisible. A hand-built
verdict could always show the right shape; the real path produced a decision with
no window at all, and before the transport repair it could not have carried one.
A suite that never ran the real evaluator would have gone on passing.

## What crosses which boundary

```
001  evaluate()  ->  CatalogDecision (public)         gate 7 computed the window
002  window_from_decision(decision)  ->  ComparableWindow (public)
003  window_for_comparison(verdict)  ->  delegates, composes nothing
```

`003` imports `001`'s **public** evaluator and `002`'s **public** reader. No
private module, no second reader, no local reconstruction — `test_no_foreign_values`
guards all three statically, and this file is the behavioural half.

## Still fixture-backed where it must be

`001`'s catalog and snapshot are its own test fixtures, and the comparison
formulas are `003`'s fixture-only set. `D-18` ships empty, so the production
formula gate still refuses every comparison. Nothing here is evidence for any
external record.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.contracts.reason_codes import Outcome
from semantic_catalog.freshness.external import FreshnessSnapshot, load_snapshot
from semantic_catalog.loader.bundle import Bundle, build_bundle
from semantic_catalog.validation.decision import (
    CatalogDecision,
    CatalogValidationRequest,
    Comparison,
    DateRange,
)
from semantic_catalog.validation.pipeline import evaluate

from analytics_interaction.authorization.context_preflight import AuthorizedContext
from analytics_interaction.comparison.refusal import SideSubmission, govern_comparison
from analytics_interaction.comparison.window import window_for_comparison
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.comparison import GovernedComparison

from ..fixtures.comparisons import (
    ABSOLUTE_DIFFERENCE,
    FIXTURE_VERSION,
    RATIO,
    caveat_set,
    executed,
    formula_instances,
)
from ..fixtures.comparisons import (
    request as governed_request,
)

pytestmark = pytest.mark.integration

#: `001`'s own fixture catalog, reached across the monorepo. Deliberately its
#: fixtures rather than a copy: a copy would drift, and the point of this file is
#: that a decision from the *real* evaluator works.
CATALOG_TESTS = Path(__file__).resolve().parents[3] / "semantic_catalog" / "tests"
CATALOG = CATALOG_TESTS / "fixtures" / "decision_matrix" / "catalog"
FRESHNESS = CATALOG_TESTS / "fixtures" / "freshness"

COMMIT = "fixture0"
CATALOG_ON = date(2026, 8, 11)
JULY = (date(2026, 7, 1), date(2026, 7, 31))
JUNE = (date(2026, 6, 1), date(2026, 6, 30))

FIXTURE_SET = formula_instances(ABSOLUTE_DIFFERENCE, RATIO)
NO_CAVEATS = caveat_set()


@pytest.fixture(scope="module")
def bundle() -> Bundle:
    return build_bundle(CATALOG, current_commit=COMMIT, on=CATALOG_ON)


@pytest.fixture(scope="module")
def snapshot() -> FreshnessSnapshot:
    return load_snapshot(FRESHNESS / "complete.yaml")


@pytest.fixture(scope="module")
def real_verdict(bundle: Bundle, snapshot: FreshnessSnapshot) -> CatalogDecision:
    """One period-over-period verdict, from `001`'s production evaluator."""
    request = CatalogValidationRequest(
        metrics=("cross_source_metric",),
        sources=("app_a", "store_a"),
        date_range=DateRange(start=JULY[0], end=JULY[1]),
        comparison=Comparison(
            kind="period_over_period",
            baseline_range=DateRange(start=JUNE[0], end=JUNE[1]),
        ),
        requester_access=("standard",),
    )
    return evaluate(
        request,
        bundle,
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        on=CATALOG_ON,
        snapshot=snapshot,
    )


def _sides(verdict: CatalogDecision) -> tuple[SideSubmission, SideSubmission]:
    """Two executed sides governed by the **same** release and policy as the verdict.

    Taken from the verdict rather than hard-coded, because that is the seam
    `FR-069` guards: a side executed under a different catalog release answers a
    question about a different definition of the same word. Hard-coding a release
    id here would have made this suite fail for a reason unrelated to ADR 0016 —
    which it did, on the first run, and the check was right.
    """

    def side(value: str) -> object:
        return executed(
            Decimal(value),
            catalog_release_id=verdict.catalog_release_id,
            policy_version=verdict.policy_version,
        )

    return (
        SideSubmission(request=governed_request(period=JULY), submit=lambda: side("150")),  # type: ignore[arg-type]
        SideSubmission(request=governed_request(period=JUNE), submit=lambda: side("100")),  # type: ignore[arg-type]
    )


# --- the verdict is real ------------------------------------------------------------


def test_the_verdict_comes_from_the_real_evaluator(real_verdict: CatalogDecision) -> None:
    """Permitted, and carrying the window `001` computed rather than one built here."""
    assert real_verdict.outcome in {Outcome.ALLOW, Outcome.ALLOW_WITH_CAVEAT}
    assert real_verdict.comparable_window is not None
    assert real_verdict.comparable_window.chosen_because
    assert real_verdict.comparable_window.sources


def test_002s_reader_converts_the_real_verdict(real_verdict: CatalogDecision) -> None:
    """The seam that refused before ADR 0016, exercised through `003`'s own module."""
    window = window_for_comparison(real_verdict)
    stated = real_verdict.comparable_window
    assert stated is not None
    assert (window.start, window.end) == (stated.start, stated.end)
    assert window.sources == stated.sources
    assert window.reason == stated.chosen_because


# --- the route completes -------------------------------------------------------------


def test_the_two_execution_route_completes_on_a_real_verdict(
    authorized_pair: tuple[AuthorizedContext, str], real_verdict: CatalogDecision
) -> None:
    """End to end: `001` evaluates, `002` converts, `003` releases."""
    authorized, fingerprint = authorized_pair
    primary, baseline = _sides(real_verdict)

    comparison = govern_comparison(
        real_verdict,
        formula_id="absolute_difference",
        primary_side=primary,
        baseline_side=baseline,
        caveats=NO_CAVEATS,
        authorized=authorized,
        auth_fingerprint=fingerprint,
        on=CATALOG_ON,
        vocabulary_version=FIXTURE_VERSION,
        derived_from=("claim-a", "claim-b"),
        instances=FIXTURE_SET,
    )

    assert isinstance(comparison, GovernedComparison)
    assert comparison.difference.value == Decimal(50)
    assert comparison.verdict is real_verdict or comparison.verdict == real_verdict
    assert len(comparison.sides) == 2


def test_the_released_window_is_the_catalog_owned_evidence(
    authorized_pair: tuple[AuthorizedContext, str], real_verdict: CatalogDecision
) -> None:
    """Byte-equivalence against what `001` stated, not merely a window's presence."""
    authorized, fingerprint = authorized_pair
    primary, baseline = _sides(real_verdict)

    comparison = govern_comparison(
        real_verdict,
        formula_id="absolute_difference",
        primary_side=primary,
        baseline_side=baseline,
        caveats=NO_CAVEATS,
        authorized=authorized,
        auth_fingerprint=fingerprint,
        on=CATALOG_ON,
        vocabulary_version=FIXTURE_VERSION,
        derived_from=("claim-a", "claim-b"),
        instances=FIXTURE_SET,
    )

    stated = real_verdict.comparable_window
    assert stated is not None
    assert (comparison.window.start, comparison.window.end) == (stated.start, stated.end)
    assert comparison.window.sources == stated.sources
    assert comparison.window.reason == stated.chosen_because
    assert comparison.difference.basis == stated.chosen_because


def test_the_window_is_narrower_than_or_equal_to_what_was_requested(
    real_verdict: CatalogDecision,
) -> None:
    """Observed coverage, not the requested range.

    A recomputation from the request would return July exactly. The catalog's
    window comes from what the sources were observed to cover.
    """
    window = window_for_comparison(real_verdict)
    stated = real_verdict.comparable_window
    assert stated is not None
    assert (window.start, window.end) == (stated.start, stated.end)


# --- and still refuses everything it should ------------------------------------------


def test_the_shipped_d18_still_refuses_on_a_real_verdict(
    authorized_pair: tuple[AuthorizedContext, str], real_verdict: CatalogDecision
) -> None:
    """A real verdict does not make an ungoverned formula computable.

    `D-18` ships empty, so the production path refuses before either side runs —
    the repair changed transport and publication, not what may be computed.
    """
    from analytics_interaction.governance.resolve import ContentUnresolvable

    authorized, fingerprint = authorized_pair
    primary, baseline = _sides(real_verdict)

    with pytest.raises(ContentUnresolvable):
        govern_comparison(
            real_verdict,
            formula_id="absolute_difference",
            primary_side=primary,
            baseline_side=baseline,
            caveats=NO_CAVEATS,
            authorized=authorized,
            auth_fingerprint=fingerprint,
            on=CATALOG_ON,
            vocabulary_version=FIXTURE_VERSION,
            derived_from=("a", "b"),
            instances=(),
        )


def test_a_fingerprint_mismatch_still_refuses_on_a_real_verdict(
    authorized_pair: tuple[AuthorizedContext, str], real_verdict: CatalogDecision
) -> None:
    authorized, fingerprint = authorized_pair
    primary, baseline = _sides(real_verdict)

    with pytest.raises(ContractViolation):
        govern_comparison(
            real_verdict,
            formula_id="absolute_difference",
            primary_side=primary,
            baseline_side=baseline,
            caveats=NO_CAVEATS,
            authorized=authorized,
            auth_fingerprint=fingerprint[::-1],
            on=CATALOG_ON,
            vocabulary_version=FIXTURE_VERSION,
            derived_from=("a", "b"),
            instances=FIXTURE_SET,
        )


def test_a_real_single_source_verdict_states_no_window_and_refuses(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """A non-comparison answer has nothing for the two-execution route to use."""
    request = CatalogValidationRequest(
        metrics=("app_sessions",),
        sources=("app_a",),
        date_range=DateRange(start=JULY[0], end=JULY[1]),
        requester_access=("standard",),
    )
    decision = evaluate(
        request,
        bundle,
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        on=CATALOG_ON,
        snapshot=snapshot,
    )

    assert decision.comparable_window is None
    with pytest.raises(ContractViolation) as refusal:
        window_for_comparison(decision)
    assert "not a substitute" in refusal.value.detail
