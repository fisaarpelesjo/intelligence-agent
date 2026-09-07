"""Adversarial coverage — T099 (FR-042; SC-003, SC-004).

Every case in ``tests/fixtures/adversarial/`` is a request built to get a wrong
answer out of the catalog. The suite asserts the outcome, the **stable reason
code**, and — where the case says so — that the refusal disclosed nothing about
a metric the requester may not see.

Asserting the code rather than just ``DENY`` is the point: a refusal that
refuses for the wrong reason sends the reader to fix the wrong thing, and a case
that checked only the outcome would pass on a generic one (SC-004).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.contracts.audit_event import EvidenceKind
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode
from semantic_catalog.freshness.external import load_snapshot
from semantic_catalog.loader.bundle import Bundle, build_bundle
from semantic_catalog.search.api import AccessContext, CatalogApi
from semantic_catalog.search.outcomes import NotGoverned, Resolved
from semantic_catalog.validation.decision import (
    CatalogDecision,
    CatalogValidationRequest,
    DateRange,
)
from semantic_catalog.validation.pipeline import evaluate

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
ADVERSARIAL = FIXTURES / "adversarial"
CATALOG = FIXTURES / "decision_matrix" / "catalog"
COMMIT = "fixture0"
ON = date(2026, 8, 11)


def _load(name: str) -> dict[str, Any]:
    return yaml.safe_load((ADVERSARIAL / name).read_text(encoding="utf-8"))


REQUESTS = _load("requests.yaml")
CASES: list[dict[str, Any]] = REQUESTS["cases"]
QUERIES: list[dict[str, Any]] = _load("queries.yaml")["cases"]


@pytest.fixture(scope="module")
def bundle() -> Bundle:
    return build_bundle(
        CATALOG,
        current_commit=COMMIT,
        on=ON,
        source_commits={"app_a": COMMIT, "store_a": COMMIT},
    )


def _run(case: dict[str, Any], bundle: Bundle) -> CatalogDecision:
    window = REQUESTS["window"]
    request = CatalogValidationRequest(
        metrics=tuple(case["metrics"]),
        dimensions=tuple(case.get("dimensions", ())),
        sources=tuple(case.get("sources", ())),
        date_range=DateRange(
            start=case.get("from", window["from"]),
            end=case.get("to", window["to"]),
        ),
        requester_access=tuple(case.get("access", ())),
        aggregate=case.get("aggregate"),
    )
    fixture = case.get("freshness")
    return evaluate(
        request,
        bundle,
        principal_type=PrincipalType(REQUESTS.get("principal_type", "user")),
        authorization_scope=case.get("scope", "default"),
        on=ON,
        snapshot=load_snapshot(FIXTURES / fixture) if fixture else None,
    )


def test_the_adversarial_set_covers_every_declared_attack_class() -> None:
    """A shrinking adversarial set is how coverage quietly disappears."""
    assert len(CASES) >= 12
    assert len({case["id"] for case in CASES}) == len(CASES), "case ids must be unique"
    codes = {case["expect"]["reason_code"] for case in CASES}
    for required in (
        "ACCESS_DENIED",
        "ACCESS_TAG_SCOPE_MISMATCH",
        "ACCESS_TAG_DEPRECATED",
        "COMPARABILITY_RULE_MISSING",
        "METRICS_NOT_COMPARABLE",
        "METRIC_NOT_AVAILABLE_FOR_SOURCE",
        "GRAIN_FAMILY_MISMATCH",
        "AGGREGATION_INVALID_FOR_ADDITIVITY",
        "SOURCE_BEYOND_TOLERANCE",
        "SOURCE_STATE_PARTIAL",
        "PERIOD_INCOMPLETE",
        "COVERAGE_ENDS_BEFORE_PERIOD",
    ):
        assert required in codes, f"no adversarial case covers {required}"


def test_every_case_states_the_attack_it_makes() -> None:
    """Reviewer-auditable: a fixture nobody can read is not evidence."""
    for case in CASES:
        assert case.get("attack", "").strip(), case["id"]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_the_catalog_refuses_the_attack(case: dict[str, Any], bundle: Bundle) -> None:
    decision = _run(case, bundle)
    expected = case["expect"]
    assert decision.outcome is Outcome(expected["outcome"]), case["id"]
    assert decision.reason_code is ReasonCode(expected["reason_code"]), case["id"]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_no_refusal_is_generic(case: dict[str, Any], bundle: Bundle) -> None:
    """SC-004. Every refusal names a subject and carries governed pt-BR wording."""
    decision = _run(case, bundle)
    assert decision.subject.id, case["id"]
    assert decision.message_pt_br, case["id"]
    assert "{" not in decision.message_pt_br, "a placeholder reached the reader"
    assert not decision.message_pt_br.startswith("["), "fell back instead of rendering"


@pytest.mark.parametrize(
    "case",
    [c for c in CASES if c.get("must_not_disclose")],
    ids=[c["id"] for c in CASES if c.get("must_not_disclose")],
)
def test_an_authorisation_refusal_discloses_nothing(case: dict[str, Any], bundle: Bundle) -> None:
    """The whole reason Gate 3 runs before Gate 4 (US2 scenario 5)."""
    decision = _run(case, bundle)
    forbidden = set(case["must_not_disclose"])
    if "freshness" in forbidden:
        assert decision.freshness == (), case["id"]
    if "segments" in forbidden:
        assert decision.segments == (), case["id"]
    if "limitations" in forbidden:
        assert decision.limitations == (), case["id"]
    if "coverage_window" in forbidden:
        assert decision.comparable_window is None, case["id"]
        assert all(
            ref.kind is not EvidenceKind.COVERAGE_WINDOW for ref in decision.evidence_refs
        ), case["id"]


# --- informal and misspelled pt-BR ------------------------------------------


@pytest.mark.parametrize("case", QUERIES, ids=[c["id"] for c in QUERIES])
def test_informal_pt_br_resolves_or_refuses_cleanly(case: dict[str, Any], bundle: Bundle) -> None:
    """Never a silent resolution to one of several plausible matches (FR-016)."""
    api = CatalogApi.from_bundle(bundle)
    outcome = api.resolve(
        case["query"],
        access=AccessContext(
            principal_type=PrincipalType.USER, authorization_scope="default", on=ON
        ),
    )
    if case["expect"] == "resolved":
        assert isinstance(outcome, Resolved), f"{case['id']}: {outcome}"
        assert outcome.candidate.metric_id == case["metric"]
    elif case["expect"] == "not_governed":
        assert isinstance(outcome, NotGoverned), f"{case['id']}: {outcome}"
    else:  # ambiguous
        assert not isinstance(outcome, Resolved | NotGoverned), f"{case['id']}: {outcome}"


def test_the_query_fixtures_do_not_claim_to_be_a_benchmark() -> None:
    """D-11 is the governed corpus. SC-002 is not claimed from hand-written cases."""
    text = (ADVERSARIAL / "queries.yaml").read_text(encoding="utf-8")
    assert "NOT a benchmark corpus" in text
    assert "SC-002" in text and "D-11" in text
