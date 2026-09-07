"""Decision-matrix regression — T059 (FR-011; quickstart Scenario 4).

Runs the curated matrix in ``tests/fixtures/decision_matrix/matrix.yaml`` through
the real pipeline. Each row asserts the outcome, the **stable reason code** and,
for denials, the **subject the refusal names** — because a row that asserted only
``DENY`` would pass on a generic refusal, which is the thing SC-004 forbids.

The matrix runs against the fixture catalog rather than the production one. The
production catalog is unpublishable by design while D-1 and D-8 are open, so
every request there stops at Gate 2 and Gates 3 to 5 are unreachable. Faking an
approval in production to make them reachable would be inventing governance
history; a self-contained fixture with its own approvals is the honest way to
exercise them.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

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

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "decision_matrix"
CATALOG = FIXTURES / "catalog"
MATRIX = FIXTURES / "matrix.yaml"
FRESHNESS = FIXTURES.parent / "freshness"

COMMIT = "fixture0"
ON = date(2026, 8, 11)
WINDOW = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))


def _matrix() -> dict[str, Any]:
    return yaml.safe_load(MATRIX.read_text(encoding="utf-8"))


ROWS: list[dict[str, Any]] = _matrix()["rows"]


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
        source_commits={"app_a": COMMIT, "store_a": COMMIT},
    )


def _window(row: dict[str, Any]) -> DateRange:
    """The row's own range, or the shared default.

    Deprecation is dated, so its rows need ranges of their own: one before the
    boundary, one on it, one after it, one crossing it. A single shared window
    could only ever assert one of the four.
    """
    if "from" not in row and "to" not in row:
        return WINDOW
    return DateRange(start=row["from"], end=row["to"])


def _run(row: dict[str, Any], bundle: Bundle) -> CatalogDecision:
    request = CatalogValidationRequest(
        metrics=tuple(row["metrics"]),
        dimensions=tuple(row.get("dimensions", ())),
        sources=tuple(row.get("sources", ())),
        date_range=_window(row),
        requester_access=tuple(row.get("access", ())),
        aggregate=row.get("aggregate"),
    )
    fixture = row.get("freshness")
    return evaluate(
        request,
        bundle,
        principal_type=PrincipalType.USER,
        authorization_scope=row.get("scope", "default"),
        on=ON,
        snapshot=load_snapshot(FRESHNESS / fixture) if fixture else None,
    )


def test_the_matrix_is_not_empty() -> None:
    assert len(ROWS) >= 30
    assert len({row["id"] for row in ROWS}) == len(ROWS), "row ids must be unique"


@pytest.mark.parametrize("row", ROWS, ids=[r["id"] for r in ROWS])
def test_every_row_matches_its_expected_outcome_and_reason(
    row: dict[str, Any], bundle: Bundle
) -> None:
    expected = row["expect"]
    decision = _run(row, bundle)

    assert decision.outcome is Outcome(expected["outcome"]), row["id"]

    if expected["reason_code"] is None:
        assert decision.reason_code is None, row["id"]
        assert decision.message_pt_br is None, row["id"]
    else:
        assert decision.reason_code is ReasonCode(expected["reason_code"]), row["id"]
        assert decision.message_pt_br, row["id"]

    assert decision.subject.kind.value == expected["subject_kind"], row["id"]
    if "subject_id" in expected:
        assert decision.subject.id == expected["subject_id"], row["id"]

    # Disclosure on a denial, never a substitute payload (T070).
    assert list(decision.answerable_subset) == list(row.get("answerable_subset", [])), row["id"]
    if decision.answerable_subset:
        assert decision.outcome is Outcome.DENY, row["id"]


@pytest.mark.parametrize(
    "row", [r for r in ROWS if r["expect"]["outcome"] == "DENY"], ids=lambda r: r["id"]
)
def test_no_denial_is_generic(row: dict[str, Any], bundle: Bundle) -> None:
    """Every refusal names a specific subject and carries a governed message."""
    decision = _run(row, bundle)
    assert decision.reason_code is not None
    assert decision.subject.id, row["id"]
    assert decision.message_pt_br, row["id"]
    assert "{" not in (decision.message_pt_br or ""), "message left a placeholder unrendered"
    assert not (decision.message_pt_br or "").startswith("["), "fell back instead of rendering"


@pytest.mark.parametrize("row", ROWS, ids=[r["id"] for r in ROWS])
def test_every_decision_carries_policy_release_and_evidence(
    row: dict[str, Any], bundle: Bundle
) -> None:
    decision = _run(row, bundle)
    assert decision.policy_version == "fixture_policy@1"
    assert decision.catalog_release_id == bundle.release_id
    assert decision.evidence_refs
    assert decision.decision_id.startswith("sha256:")


def test_authorisation_precedes_combination(bundle: Bundle) -> None:
    """The ordering assertion, stated directly rather than inferred from a row.

    The request is invalid two different ways: the requester lacks the scope,
    *and* the combination is impossible. It must refuse on authorisation, because
    refusing on combination would tell someone who may not see the metric that it
    exists and what shape it has.
    """
    row = next(r for r in ROWS if r["id"] == "restricted_metric_denies_before_combination")
    decision = _run(row, bundle)
    assert decision.reason_code is ReasonCode.ACCESS_TAG_SCOPE_MISMATCH
    assert decision.reason_code not in {
        ReasonCode.METRIC_NOT_AVAILABLE_FOR_SOURCE,
        ReasonCode.DIMENSION_NOT_APPLICABLE_TO_SOURCE,
        ReasonCode.DIMENSION_NOT_ALLOWED_FOR_METRIC,
    }


def test_a_deprecated_tag_never_auto_grants_its_replacement(bundle: Bundle) -> None:
    row = next(r for r in ROWS if r["id"] == "deprecated_tag_denies_and_replacement_is_not_granted")
    decision = _run(row, bundle)
    assert decision.reason_code is ReasonCode.ACCESS_TAG_DEPRECATED
    assert decision.outcome is Outcome.DENY
    assert "standard" not in (decision.message_pt_br or "")


def test_decisions_are_reproducible_for_an_identical_request(bundle: Bundle) -> None:
    row = ROWS[0]
    first, second = _run(row, bundle), _run(row, bundle)
    assert first.decision_id == second.decision_id


def test_no_decision_exposes_a_draft_definition_or_a_value(bundle: Bundle) -> None:
    """A refusal may name identifiers. It may never quote a definition."""
    drafts: list[str] = []
    for metric in bundle.internal.metrics.values():
        for version in metric.versions:
            drafts += [version.calculation_basis, version.grain, str(version.source_view)]
            drafts.append(version.content.description)
    for row in ROWS:
        text = str(_run(row, bundle).model_dump(mode="json"))
        leaked = [d for d in drafts if d and d in text]
        assert not leaked, f"{row['id']}: leaked {leaked[:2]}"
