"""Withdrawn releases and rollback — T095 (FR-065, FR-075).

Quickstart Scenario 21. Correction is forward-only, and the four properties that
makes it are asserted here rather than described:

* a withdrawn release **denies new decisions** under ``RELEASE_WITHDRAWN``;
* it stays **resolvable**, and decisions issued under it keep their original
  release reference — nothing rewrites them;
* an identifier is **never reused**, and the active pointer moves **only after
  validation** succeeds;
* rollback is a **new audited activation event**, not a rewound log.

The bad release is never edited or deleted, because that is the difference
between correcting a mistake and hiding one.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode
from semantic_catalog.freshness.external import FreshnessSnapshot, load_snapshot
from semantic_catalog.loader.bundle import Bundle, build_bundle
from semantic_catalog.loader.release_state import (
    EventKind,
    ReleaseIdentifierReuseError,
    ReleaseLedger,
    ReleaseState,
    UnknownReleaseError,
    UnvalidatedReleaseError,
)
from semantic_catalog.validation.decision import (
    CatalogDecision,
    CatalogValidationRequest,
    DateRange,
)
from semantic_catalog.validation.pipeline import evaluate
from semantic_catalog.validation.release import ReleaseValidation, validate_release
from semantic_catalog.validation.result import (
    Severity,
    Subject,
    ValidationFinding,
    ValidationLayer,
    ValidationReport,
)

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "versioned_catalog"
CATALOG = FIXTURES / "catalog"
PRODUCTION = Path(__file__).resolve().parents[4] / "semantic"
COMMIT = "fixture0"
ON = date(2026, 8, 11)
T0 = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
T1 = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
T2 = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)

PASSED = ReleaseValidation(commit="validated-commit", report=ValidationReport())
FAILED = ReleaseValidation(
    commit="broken-commit",
    report=ValidationReport.from_findings(
        [
            ValidationFinding(
                layer=ValidationLayer.L4_POLICY,
                rule="deliberate_failure",
                severity=Severity.ERROR,
                subject=Subject(kind="metric", identifier="fixture_metric"),
                message="fixture_metric fails on purpose, so publication must refuse",
            )
        ]
    ),
)


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


def _decide(bundle: Bundle, snapshot: FreshnessSnapshot, release: object | None) -> CatalogDecision:
    return evaluate(
        CatalogValidationRequest(
            metrics=("fixture_metric",),
            sources=("fixture_source",),
            date_range=DateRange(start=date(2025, 2, 1), end=date(2025, 3, 31)),
            requester_access=("standard",),
        ),
        bundle,
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        on=ON,
        snapshot=snapshot,
        release=release,  # type: ignore[arg-type]
    )


def _ledger(bundle: Bundle) -> ReleaseLedger:
    ledger = ReleaseLedger()
    ledger.publish(
        bundle.release_id,
        PASSED,
        occurred_at=T0,
        reason="initial release",
        actor_role="fixture_governance",
    )
    return ledger


# --- publication ------------------------------------------------------------


def test_the_pointer_moves_only_after_validation_succeeds(bundle: Bundle) -> None:
    ledger = ReleaseLedger()
    with pytest.raises(UnvalidatedReleaseError, match="only after validation"):
        ledger.publish(
            bundle.release_id,
            FAILED,
            occurred_at=T0,
            reason="attempt",
            actor_role="fixture_governance",
        )
    assert ledger.active is None
    assert ledger.events == ()


def test_an_identifier_is_never_reused(bundle: Bundle) -> None:
    ledger = _ledger(bundle)
    with pytest.raises(ReleaseIdentifierReuseError, match="never reused"):
        ledger.publish(
            bundle.release_id,
            PASSED,
            occurred_at=T1,
            reason="again",
            actor_role="fixture_governance",
        )


def test_publishing_a_corrective_release_supersedes_the_previous_one(bundle: Bundle) -> None:
    ledger = _ledger(bundle)
    ledger.publish(
        "sha256:corrective",
        PASSED,
        occurred_at=T1,
        reason="corrective release",
        actor_role="fixture_governance",
    )
    assert ledger.active is not None
    assert ledger.active.release_id == "sha256:corrective"
    previous = ledger.resolve(bundle.release_id)
    assert previous is not None and previous.state is ReleaseState.SUPERSEDED


def test_a_real_release_validation_gates_publication() -> None:
    """Not a hand-built verdict: the production tree, validated for real."""
    validation = validate_release(PRODUCTION, commit="head", on=ON)
    assert validation.valid, validation.report.render()
    ledger = ReleaseLedger()
    release = ledger.publish(
        "sha256:production",
        validation,
        occurred_at=T0,
        reason="release",
        actor_role="data_governance",
    )
    assert release.state is ReleaseState.ACTIVE


# --- withdrawal -------------------------------------------------------------


def test_a_withdrawn_release_denies_new_decisions(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    ledger = _ledger(bundle)
    withdrawn = ledger.withdraw(
        bundle.release_id,
        occurred_at=T1,
        reason="incorrect aggregation on fixture_metric",
        actor_role="fixture_governance",
    )
    decision = _decide(bundle, snapshot, withdrawn)
    assert decision.outcome is Outcome.DENY
    assert decision.reason_code is ReasonCode.RELEASE_WITHDRAWN
    assert bundle.release_id in decision.message_pt_br


def test_the_same_request_allows_under_an_active_release(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """Proves the denial is about the release state, not the request."""
    ledger = _ledger(bundle)
    decision = _decide(bundle, snapshot, ledger.resolve(bundle.release_id))
    assert decision.outcome is Outcome.ALLOW


def test_a_withdrawn_release_is_neither_edited_nor_deleted(bundle: Bundle) -> None:
    ledger = _ledger(bundle)
    before = ledger.resolve(bundle.release_id)
    assert before is not None
    ledger.withdraw(
        bundle.release_id, occurred_at=T1, reason="wrong", actor_role="fixture_governance"
    )
    after = ledger.resolve(bundle.release_id)
    assert after is not None
    assert after.release_id == before.release_id
    assert after.activated_at == before.activated_at
    assert after.withdrawn_at == T1
    assert after.state is ReleaseState.WITHDRAWN


def test_a_historical_decision_keeps_its_original_release_reference(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """FR-065. The decision issued before withdrawal still resolves, unchanged."""
    ledger = _ledger(bundle)
    issued = _decide(bundle, snapshot, ledger.resolve(bundle.release_id))
    snapshot_of_decision = issued.model_dump(mode="json")

    ledger.withdraw(
        bundle.release_id, occurred_at=T1, reason="wrong", actor_role="fixture_governance"
    )

    assert issued.model_dump(mode="json") == snapshot_of_decision
    assert issued.catalog_release_id == bundle.release_id
    assert ledger.resolve(issued.catalog_release_id) is not None


def test_an_unknown_release_admits_nothing(bundle: Bundle) -> None:
    """Fails closed: unknown is not permission."""
    ledger = _ledger(bundle)
    assert not ledger.admits_new_decisions("sha256:never-seen")
    with pytest.raises(UnknownReleaseError):
        ledger.withdraw(
            "sha256:never-seen",
            occurred_at=T1,
            reason="x",
            actor_role="fixture_governance",
        )


# --- rollback ---------------------------------------------------------------


def test_rollback_is_a_new_audited_activation_event(bundle: Bundle) -> None:
    ledger = _ledger(bundle)
    ledger.publish(
        "sha256:corrective",
        PASSED,
        occurred_at=T1,
        reason="corrective release",
        actor_role="fixture_governance",
    )
    rolled_back = ledger.activate(
        bundle.release_id, occurred_at=T2, reason="rollback", actor_role="fixture_governance"
    )

    kinds = [event.kind for event in ledger.events]
    assert kinds == [EventKind.PUBLISH, EventKind.PUBLISH, EventKind.ACTIVATE]
    assert len({event.event_id for event in ledger.events}) == 3
    assert ledger.events[-1].reason == "rollback"
    assert rolled_back.state is ReleaseState.ACTIVE
    assert rolled_back.activation_event_id == ledger.events[-1].event_id
    assert rolled_back.activation_event_id != ledger.events[0].event_id

    superseded = ledger.resolve("sha256:corrective")
    assert superseded is not None and superseded.state is ReleaseState.SUPERSEDED


def test_rollback_never_rewrites_history(bundle: Bundle) -> None:
    ledger = _ledger(bundle)
    ledger.publish(
        "sha256:corrective",
        PASSED,
        occurred_at=T1,
        reason="corrective release",
        actor_role="fixture_governance",
    )
    before = ledger.events
    ledger.activate(
        bundle.release_id, occurred_at=T2, reason="rollback", actor_role="fixture_governance"
    )
    assert ledger.events[: len(before)] == before


def test_a_withdrawn_release_cannot_be_reactivated(bundle: Bundle) -> None:
    """It was withdrawn because it was wrong. Publishing a corrected release is
    the only way forward (FR-075)."""
    ledger = _ledger(bundle)
    ledger.withdraw(
        bundle.release_id, occurred_at=T1, reason="wrong", actor_role="fixture_governance"
    )
    with pytest.raises(UnvalidatedReleaseError, match="corrective release"):
        ledger.activate(
            bundle.release_id,
            occurred_at=T2,
            reason="rollback",
            actor_role="fixture_governance",
        )


def test_event_identifiers_are_deterministic_and_distinct(bundle: Bundle) -> None:
    """Derived from what happened, so a replayed ledger reproduces them, and
    including the sequence keeps two same-instant events apart."""
    first = _ledger(bundle).events[0].event_id
    second = _ledger(bundle).events[0].event_id
    assert first == second

    ledger = _ledger(bundle)
    ledger.withdraw(
        bundle.release_id, occurred_at=T0, reason="same instant", actor_role="fixture_governance"
    )
    assert len({event.event_id for event in ledger.events}) == 2
