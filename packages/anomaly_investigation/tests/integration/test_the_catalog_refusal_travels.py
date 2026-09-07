"""The catalog's word reaches the run intact — T016 (`FR-001`).

**This is the measurement the review asked for, and it is the one that could have
sunk the design.** The carrier `ANOMALY_RULE_METRIC_NOT_BOUND` reads as *"there is
no binding"*, and the metric **has** a binding — what it lacks is publication. The
only thing keeping that from being a false word is the upstream code travelling
verbatim beside it. **If the upstream code were lost, the carrier would be
asserting more than it measured, and the design would be wrong.**

So this runs against the **production catalog** rather than a fixture. Measured in
cycle 314:

```
build_bundle("semantic")               -> 11 metrics, 6 sources
evaluate(active_users, ...)            -> DENY / METRIC_PENDING
```

Both principal types, same answer. `D-1` is open, `approvals: []`, every source is
unpublishable, and `001`'s existence gate denies a `PENDING` metric.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.contracts.reason_codes import ReasonCode
from semantic_catalog.loader.bundle import build_bundle
from semantic_catalog.validation.pipeline import evaluate

from anomaly_investigation.contracts import AnomalyReasonCode, Run, RunOutcome, Withholding
from anomaly_investigation.ports import resolve_metric

pytestmark = pytest.mark.integration

#: `tests/integration/` -> `tests/` -> package -> `packages/` -> repository.
REPO = Path(__file__).resolve().parents[4]
ON = date(2026, 8, 25)


def _bundle():
    return build_bundle(REPO / "semantic", current_commit="0" * 40, on=ON)


def test_the_production_catalog_is_reachable_and_not_empty() -> None:
    """A refusal measured over an empty catalog would prove nothing.

    The same rule the structural node applies: assert the instrument reached
    something before asserting anything about what it found.
    """
    bundle = _bundle()
    assert len(bundle.public) >= 1


@pytest.mark.parametrize("principal", list(PrincipalType))
def test_the_catalog_refuses_and_our_carrier_brings_its_word(principal: PrincipalType) -> None:
    """The whole claim, in one assertion: **refused, and the reason is legible.**"""
    resolution = resolve_metric(
        "trials_drop",
        "active_users",
        evaluate=evaluate,
        bundle=_bundle(),
        start=date(2026, 7, 1),
        end=date(2026, 7, 31),
        baseline_start=date(2026, 6, 1),
        baseline_end=date(2026, 6, 30),
        comparison_kind="period_over_period",
        principal_type=principal,
        authorization_scope="analytics",
        requester_access=("public",),
        on=ON,
    )

    assert not resolution.permitted
    assert resolution.reason_code is AnomalyReasonCode.ANOMALY_RULE_METRIC_NOT_BOUND

    # The measurement that decides whether the carrier is honest.
    assert resolution.upstream_code == ReasonCode.METRIC_PENDING.value
    assert resolution.upstream_code is not None


def test_the_refusal_is_traceable_back_to_a_governed_decision() -> None:
    """A refusal nobody can audit is a refusal nobody can dispute."""
    resolution = resolve_metric(
        "trials_drop",
        "active_users",
        evaluate=evaluate,
        bundle=_bundle(),
        start=date(2026, 7, 1),
        end=date(2026, 7, 31),
        baseline_start=date(2026, 6, 1),
        baseline_end=date(2026, 6, 30),
        comparison_kind="period_over_period",
        principal_type=PrincipalType.USER,
        authorization_scope="analytics",
        requester_access=("public",),
        on=ON,
    )
    assert resolution.is_traceable
    assert resolution.decision_id


def test_the_run_reports_asked_and_denied_rather_than_nothing_moved() -> None:
    """**The point of the whole cycle, stated as a test.**

    A detector that reports *"I asked and was refused, and the catalog's word is
    this"* is a detector working. One that reported zero candidates and stayed
    quiet would be claiming the KPI was calm while never having looked.
    """
    resolution = resolve_metric(
        "trials_drop",
        "active_users",
        evaluate=evaluate,
        bundle=_bundle(),
        start=date(2026, 7, 1),
        end=date(2026, 7, 31),
        baseline_start=date(2026, 6, 1),
        baseline_end=date(2026, 6, 30),
        comparison_kind="period_over_period",
        principal_type=PrincipalType.USER,
        authorization_scope="analytics",
        requester_access=("public",),
        on=ON,
    )
    assert resolution.reason_code is not None

    run = Run(
        run_id="r",
        instant=datetime(2026, 8, 25, 8, 0, tzinfo=UTC),
        rules_considered=("trials_drop",),
        withholdings=(
            Withholding(
                rule_id="trials_drop",
                reason_code=resolution.reason_code,
                upstream_code=resolution.upstream_code,
            ),
        ),
        outcome=RunOutcome.COMPLETED,
    )

    assert run.candidates == ()
    assert run.quiet == ()
    assert run.withholdings[0].upstream_code == "METRIC_PENDING"


def test_an_allow_would_be_required_for_a_window_and_none_is_reachable_today() -> None:
    """Named rather than left implicit: **`T023` cannot be marked.**

    `SC-001` demands a candidate against the real warehouse over a bound KPI. No
    KPI is publishable while `D-1` is open, so the end-to-end proof is not
    reachable — and substituting a fixture would be the exact thing
    `observed_from_fixture` exists to prevent.
    """
    bundle = _bundle()
    outcomes: set[bool] = set()
    for metric in sorted(bundle.public):
        resolution = resolve_metric(
            "probe",
            metric,
            evaluate=evaluate,
            bundle=bundle,
            start=date(2026, 7, 1),
            end=date(2026, 7, 31),
            baseline_start=date(2026, 6, 1),
            baseline_end=date(2026, 6, 30),
            comparison_kind="period_over_period",
            principal_type=PrincipalType.USER,
            authorization_scope="analytics",
            requester_access=("public",),
            on=ON,
        )
        outcomes.add(resolution.permitted)

    assert outcomes == {False}, "a metric became permitted; T023 may now be reachable"
