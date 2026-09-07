"""Preflight code-set pin — T034 (FR-011; SC-009).

`002` declares `AUTHORIZATION_DENIAL_CODES` itself because `001` publishes no
gate-scoped constant — its `codes_with_outcome` classifies by *outcome*, not by
gate. A locally declared set can drift from what the gate actually emits, and the
consequence of drift is severe in one direction: a new authorisation code that
`002` does not recognise would be classified as *authorization proved*, and an
unauthorized request would go on to read the warehouse.

So the set is pinned against **two** independent sources, both of which must
agree:

* the merged gate module — the real emitter, extracted from its source; and
* `001`'s `decision-contract.md`, the published contract.

Pinning against the module alone would miss an undocumented code; against the
document alone would miss an unimplemented one. Requiring both means either kind
of drift fails CI rather than silently mis-classifying.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode, outcome_for
from semantic_catalog.validation.decision import CatalogDecision

from analytics_query.authorization.classify import (
    AUTHORIZATION_DENIAL_CODES,
    SNAPSHOT_ABSENCE_SENTINEL,
    PreflightOutcome,
    classify_preflight,
)

pytestmark = pytest.mark.contract

REPO = Path(__file__).resolve().parents[4]
GATE = (
    REPO
    / "packages"
    / "semantic_catalog"
    / "src"
    / "semantic_catalog"
    / "validation"
    / "gates"
    / "authorization.py"
)
DECISION_CONTRACT = REPO / "specs" / "001-semantic-catalog" / "contracts" / "decision-contract.md"

EXPECTED = {
    ReasonCode.ACCESS_DENIED,
    ReasonCode.ACCESS_TAG_UNKNOWN,
    ReasonCode.ACCESS_TAG_DEPRECATED,
    ReasonCode.ACCESS_TAG_SCOPE_MISMATCH,
}


def _codes_emitted_by_the_gate() -> set[ReasonCode]:
    """Every `ReasonCode` the merged authorisation gate references."""
    source = GATE.read_text(encoding="utf-8")
    return {ReasonCode(name) for name in re.findall(r"ReasonCode\.([A-Z_]+)", source)}


def test_the_pinned_set_matches_the_merged_gate() -> None:
    """The gate is the real emitter; drift here is the dangerous direction."""
    assert GATE.is_file(), f"upstream gate module missing: {GATE}"
    assert _codes_emitted_by_the_gate() == AUTHORIZATION_DENIAL_CODES


def test_the_pinned_set_matches_the_published_contract() -> None:
    """Every pinned code is documented in `001`'s decision contract."""
    text = DECISION_CONTRACT.read_text(encoding="utf-8")
    for code in AUTHORIZATION_DENIAL_CODES:
        assert f"`{code.value}`" in text, f"{code.value} is not documented upstream"


def test_the_pinned_set_is_exactly_the_four_expected_codes() -> None:
    assert AUTHORIZATION_DENIAL_CODES == EXPECTED
    assert len(AUTHORIZATION_DENIAL_CODES) == 4


def test_every_pinned_code_denies() -> None:
    """A code that did not deny would make the classification meaningless."""
    for code in AUTHORIZATION_DENIAL_CODES:
        assert outcome_for(code) is Outcome.DENY


def test_an_unrecognised_authorisation_code_would_be_detected() -> None:
    """The guard must be capable of failing.

    Shown by constructing the drift the pin exists to catch: a code the gate
    emits but the local set omits is not silently tolerated.
    """
    drifted = AUTHORIZATION_DENIAL_CODES - {ReasonCode.ACCESS_DENIED}
    assert _codes_emitted_by_the_gate() != drifted


# --- classification ----------------------------------------------------------


def _decision(code: ReasonCode) -> CatalogDecision:
    from datetime import UTC, datetime

    from semantic_catalog.contracts.audit_event import EvidenceKind, EvidenceRef
    from semantic_catalog.validation.decision import Subject, SubjectKind

    return CatalogDecision(
        decision_id="d-1",
        policy_version="p-1",
        catalog_release_id="r-1",
        evaluated_at=datetime(2026, 8, 12, tzinfo=UTC),
        outcome=outcome_for(code),
        reason_code=code,
        message_pt_br="mensagem governada",
        subject=Subject(kind=SubjectKind.REQUEST, id="request"),
        evidence_refs=(EvidenceRef(kind=EvidenceKind.CATALOG_RELEASE, id="r-1"),),
    )


SORTED_EXPECTED: list[ReasonCode] = sorted(EXPECTED, key=lambda code: code.value)


@pytest.mark.parametrize("code", SORTED_EXPECTED, ids=[c.value for c in SORTED_EXPECTED])
def test_an_authorisation_code_classifies_as_denied(code: ReasonCode) -> None:
    assert classify_preflight(_decision(code)) is PreflightOutcome.AUTHORIZATION_DENIED


def test_the_snapshot_absence_sentinel_classifies_as_authorized() -> None:
    """Gates 1-6 all passed, including gate 3; gate 7 only lacked a snapshot."""
    assert SNAPSHOT_ABSENCE_SENTINEL is ReasonCode.SOURCE_STATE_UNKNOWN
    assert classify_preflight(_decision(SNAPSHOT_ABSENCE_SENTINEL)) is PreflightOutcome.AUTHORIZED


def test_another_gates_denial_is_passed_through_not_treated_as_authorized() -> None:
    assert (
        classify_preflight(_decision(ReasonCode.METRIC_PENDING))
        is PreflightOutcome.REFUSED_UPSTREAM
    )


def test_a_permissive_decision_classifies_as_authorized() -> None:
    """No required sources means gates 7-8 had nothing to evaluate."""
    assert classify_preflight(_decision(ReasonCode.REQUEST_ALLOWED)) is PreflightOutcome.AUTHORIZED
