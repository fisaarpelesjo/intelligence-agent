"""*"Nothing moved"* and *"we could not tell"* stay apart in the run — T015 (`SC-002`).

This is the criterion stated as a test rather than as a hope. `SC-002` asserts
**zero candidates and one named withholding**, and that a reader can tell the two
silences apart *in the run*.

**Integration rather than unit**, because the claim is about the assembled `Run` —
the freshness verdict, the reason code and the run's three lists agreeing with each
other. Each piece can be right on its own while the assembly loses the distinction,
and losing it is exactly the failure.

No detector exists yet: Phase 2 precedes Phase 3. So the run is assembled here the
way Phase 3 will assemble it, which is also a check that the contracts *can* express
the outcome before anything is built to produce it.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from semantic_catalog.freshness.external import (
    CompletenessStatus,
    FreshnessRecord,
    FreshnessSnapshot,
)

from anomaly_investigation.contracts import AnomalyReasonCode, Run, RunOutcome, Withholding
from anomaly_investigation.freshness import FreshnessVerdict, assess_freshness

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)


def _snapshot(status: CompletenessStatus, *, source: str = "trials") -> FreshnessSnapshot:
    return FreshnessSnapshot(
        observed_at=NOW,
        records=(
            FreshnessRecord(
                source=source,
                status=status,
                observed_at=NOW,
                completeness_ratio=1.0 if status is CompletenessStatus.COMPLETE else 0.4,
                last_successful_update=NOW,
                last_error="load aborted" if status is CompletenessStatus.FAILED else None,
            ),
        ),
    )


def _run_from(rule_id: str, verdict: FreshnessVerdict, *, crossed: bool) -> Run:
    """Assemble a run the way Phase 3 will, from a verdict and a crossing.

    Deliberately mechanical: the point is that the **contract** keeps the three
    outcomes apart, not that this helper is clever.
    """
    if not verdict.permits_firing:
        assert verdict.reason_code is not None
        return Run(
            run_id="r",
            instant=NOW,
            rules_considered=(rule_id,),
            withholdings=(
                Withholding(
                    rule_id=rule_id,
                    reason_code=verdict.reason_code,
                    freshness=verdict.record,
                ),
            ),
            outcome=RunOutcome.COMPLETED,
        )
    if crossed:  # pragma: no cover - Phase 3 owns the crossing itself
        raise NotImplementedError("detection is Phase 3")
    return Run(
        run_id="r",
        instant=NOW,
        rules_considered=(rule_id,),
        quiet=(rule_id,),
        outcome=RunOutcome.COMPLETED,
    )


def test_a_withheld_rule_produces_zero_candidates_and_one_named_withholding() -> None:
    """`SC-002`, first half, literally."""
    verdict = assess_freshness(_snapshot(CompletenessStatus.PARTIAL), sources=("trials",), now=NOW)
    run = _run_from("trials_drop", verdict, crossed=False)

    assert run.candidates == ()
    assert len(run.withholdings) == 1
    assert run.withholdings[0].reason_code is AnomalyReasonCode.ANOMALY_PERIOD_INCOMPLETE
    assert run.outcome is RunOutcome.COMPLETED


def test_the_two_silences_are_distinguishable_in_the_run() -> None:
    """`SC-002`, second half — and this is the whole reason the run keeps three lists.

    Both runs below have **zero candidates**. If the only readable fact were that
    count, an operator could not tell a quiet KPI from a broken pipeline.
    """
    quiet = _run_from(
        "trials_drop",
        assess_freshness(_snapshot(CompletenessStatus.COMPLETE), sources=("trials",), now=NOW),
        crossed=False,
    )
    could_not_tell = _run_from(
        "trials_drop",
        assess_freshness(_snapshot(CompletenessStatus.FAILED), sources=("trials",), now=NOW),
        crossed=False,
    )

    assert quiet.candidates == could_not_tell.candidates == ()

    assert quiet.quiet == ("trials_drop",)
    assert quiet.withholdings == ()

    assert could_not_tell.quiet == ()
    assert could_not_tell.withholdings[0].reason_code is (
        AnomalyReasonCode.ANOMALY_SOURCE_INGESTION_FAILED
    )


def test_the_withholding_carries_the_evidence_that_produced_it() -> None:
    """The code is ours; the record is the source's. Both travel, neither mixes.

    A withholding that named a reason without carrying the observation would make
    an operator take our word for it — and `FR-014` is easiest to violate at a
    refusal path, where writing a helpful sentence feels harmless.
    """
    verdict = assess_freshness(_snapshot(CompletenessStatus.FAILED), sources=("trials",), now=NOW)
    run = _run_from("trials_drop", verdict, crossed=False)
    withholding = run.withholdings[0]

    assert withholding.freshness is not None
    assert withholding.freshness.status is CompletenessStatus.FAILED
    assert withholding.freshness.last_error == "load aborted"
    # The reason code is a governed word, not a sentence assembled about the error.
    assert withholding.reason_code.value.startswith("ANOMALY_")


def test_a_withheld_run_still_accounts_for_the_rule_it_considered() -> None:
    """Withholding is an outcome, not a disappearance.

    Without this, a withheld rule could be omitted from every list and its silence
    would read as *"nothing moved"* — the inference this feature must never let a
    reader make by accident.
    """
    verdict = assess_freshness(_snapshot(CompletenessStatus.UNKNOWN), sources=("trials",), now=NOW)
    run = _run_from("trials_drop", verdict, crossed=False)

    reported = (
        {c.rule_id for c in run.candidates}
        | {w.rule_id for w in run.withholdings}
        | set(run.quiet)
        | set(run.never_firable)
    )
    assert reported == set(run.rules_considered)
