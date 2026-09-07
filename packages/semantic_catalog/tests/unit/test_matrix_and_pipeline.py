"""Completion-evidence tests for T050, T051, T056, T057.

T050: no decision constructible without outcome, reason code and evidence refs.
T051: none-effective and more-than-one-effective both DENY (covered in T060's
      suite; the resolution shape is asserted here).
T056: a test asserts authorisation precedes combination.
T057: access-filtered enumeration of the answerable surface.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from semantic_catalog.contracts.access_tag import PrincipalType
from semantic_catalog.contracts.audit_event import EvidenceKind, EvidenceRef
from semantic_catalog.contracts.reason_codes import (
    Outcome,
    ReasonCode,
    codes_with_outcome,
    outcome_for,
)
from semantic_catalog.freshness.external import FreshnessSnapshot, load_snapshot
from semantic_catalog.loader.bundle import Bundle, build_bundle
from semantic_catalog.validation.decision import (
    CatalogDecision,
    CatalogValidationRequest,
    DateRange,
    Finality,
    Reproducibility,
    Subject,
    SubjectKind,
    derive_decision_id,
)
from semantic_catalog.validation.matrix import allowed_combinations
from semantic_catalog.validation.pipeline import GATES, evaluate, gate_order

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[4]
CATALOG = Path(__file__).resolve().parents[1] / "fixtures" / "decision_matrix" / "catalog"
ON = date(2026, 8, 11)
WINDOW = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))
STAMP = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


FRESHNESS = Path(__file__).resolve().parents[1] / "fixtures" / "freshness"


@pytest.fixture(scope="module")
def bundle() -> Bundle:
    return build_bundle(
        CATALOG,
        current_commit="fixture0",
        on=ON,
        source_commits={"app_a": "fixture0", "store_a": "fixture0"},
    )


@pytest.fixture(scope="module")
def snapshot() -> FreshnessSnapshot:
    return load_snapshot(FRESHNESS / "complete.yaml")


def _base(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "decision_id": "sha256:abc",
        "policy_version": "fixture_policy@1",
        "catalog_release_id": "sha256:rel",
        "evaluated_at": STAMP,
        "outcome": Outcome.DENY,
        "reason_code": ReasonCode.METRIC_PENDING,
        "message_pt_br": "Mensagem governada.",
        "subject": Subject(kind=SubjectKind.METRIC, id="x"),
        "evidence_refs": (EvidenceRef(kind=EvidenceKind.CATALOG_RELEASE, id="sha256:rel"),),
    }
    payload.update(overrides)
    return payload


# --- T050 ------------------------------------------------------------------


@pytest.mark.parametrize("missing", ["outcome", "subject", "evidence_refs"])
def test_a_decision_is_not_constructible_without_its_required_parts(missing: str) -> None:
    payload = _base()
    del payload[missing]
    with pytest.raises(ValidationError):
        CatalogDecision.model_validate(payload)


def test_empty_evidence_refs_are_refused() -> None:
    with pytest.raises(ValidationError, match=r"too_short|at least 1"):
        CatalogDecision.model_validate(_base(evidence_refs=()))


@pytest.mark.parametrize("missing", ["reason_code", "message_pt_br"])
def test_no_outcome_may_omit_its_code_or_its_message(missing: str) -> None:
    """Every outcome is explained, a clean allow included (P1)."""
    with pytest.raises(ValidationError):
        CatalogDecision.model_validate(_base(**{missing: None}))


def test_a_clean_allow_carries_request_allowed() -> None:
    """The governed ALLOW-classified code. Without it an allow is unauditable."""
    decision = CatalogDecision.model_validate(
        _base(
            outcome=Outcome.ALLOW,
            reason_code=ReasonCode.REQUEST_ALLOWED,
            message_pt_br="Solicitação autorizada pelas políticas vigentes.",
        )
    )
    assert decision.reason_code is ReasonCode.REQUEST_ALLOWED
    assert outcome_for(decision.reason_code) is Outcome.ALLOW


def test_every_outcome_class_is_inhabited_by_a_governed_code() -> None:
    """A declared outcome no code can express is a state nothing may produce."""
    for outcome in Outcome:
        codes = codes_with_outcome(outcome)
        assert codes, f"no governed reason code is classified {outcome.value}"
        for code in codes:
            assert outcome_for(code) is outcome


def test_an_answerable_subset_may_only_ride_on_a_denial() -> None:
    with pytest.raises(ValidationError, match="never a substitute payload"):
        CatalogDecision.model_validate(
            _base(
                outcome=Outcome.ALLOW,
                reason_code=ReasonCode.REQUEST_ALLOWED,
                message_pt_br="Solicitação autorizada pelas políticas vigentes.",
                answerable_subset=("app_a",),
            )
        )


# --- P2 finality ------------------------------------------------------------


@pytest.mark.parametrize(
    "outcome, code",
    [
        (Outcome.ALLOW, ReasonCode.REQUEST_ALLOWED),
        (Outcome.ALLOW_WITH_CAVEAT, ReasonCode.DEPRECATED_METRIC),
    ],
)
def test_a_permissive_outcome_without_revisions_may_not_be_final(
    outcome: Outcome, code: ReasonCode
) -> None:
    with pytest.raises(ValidationError, match="is PRE_EVIDENCE"):
        CatalogDecision.model_validate(
            _base(outcome=outcome, reason_code=code, finality=Finality.FINAL)
        )


@pytest.mark.parametrize(
    "outcome, code",
    [
        (Outcome.ALLOW, ReasonCode.REQUEST_ALLOWED),
        (Outcome.ALLOW_WITH_CAVEAT, ReasonCode.DEPRECATED_METRIC),
        (Outcome.DENY, ReasonCode.METRIC_PENDING),
    ],
)
def test_full_reproducibility_always_requires_a_data_revision(
    outcome: Outcome, code: ReasonCode
) -> None:
    with pytest.raises(ValidationError, match="requires at least one data_revision_id"):
        CatalogDecision.model_validate(
            _base(outcome=outcome, reason_code=code, reproducibility=Reproducibility.FULL)
        )


def test_a_denial_may_be_final_without_a_revision() -> None:
    """Nothing was read, so no revision contributed to the refusal."""
    decision = CatalogDecision.model_validate(_base(finality=Finality.FINAL))
    assert decision.is_final
    assert decision.reproducibility is Reproducibility.LIMITED


def test_a_permissive_outcome_with_revisions_may_be_final_and_full() -> None:
    """The mechanism is not vacuous — supplying evidence unlocks the claim."""
    decision = CatalogDecision.model_validate(
        _base(
            outcome=Outcome.ALLOW,
            reason_code=ReasonCode.REQUEST_ALLOWED,
            message_pt_br="Solicitação autorizada pelas políticas vigentes.",
            data_revisions=("app_a@rev1",),
            reproducibility=Reproducibility.FULL,
            finality=Finality.FINAL,
        )
    )
    assert decision.is_final
    assert decision.reproducibility is Reproducibility.FULL


def test_the_defaults_are_the_safe_ones() -> None:
    decision = CatalogDecision.model_validate(_base())
    assert decision.finality is Finality.PRE_EVIDENCE
    assert decision.reproducibility is Reproducibility.LIMITED


def test_decision_id_is_order_independent_and_input_sensitive() -> None:
    a = CatalogValidationRequest(
        metrics=("b_metric", "a_metric"), date_range=WINDOW, sources=("s2", "s1")
    )
    b = CatalogValidationRequest(
        metrics=("a_metric", "b_metric"), date_range=WINDOW, sources=("s1", "s2")
    )
    kwargs = {
        "catalog_release_id": "sha256:rel",
        "metric_version_ids": ("a_metric@1",),
        "policy_version": "p@1",
    }
    assert derive_decision_id(a, **kwargs) == derive_decision_id(b, **kwargs)  # type: ignore[arg-type]
    assert derive_decision_id(a, **{**kwargs, "policy_version": "p@2"}) != derive_decision_id(  # type: ignore[arg-type]
        a,
        **kwargs,  # type: ignore[arg-type]
    )


def test_later_phase_inputs_are_parameters_not_lookups() -> None:
    """Freshness and data revisions change the id when supplied, and only then."""
    request = CatalogValidationRequest(metrics=("m",), date_range=WINDOW)
    kwargs = {
        "catalog_release_id": "r",
        "metric_version_ids": ("m@1",),
        "policy_version": "p@1",
    }
    bare = derive_decision_id(request, **kwargs)  # type: ignore[arg-type]
    with_revision = derive_decision_id(
        request,
        **kwargs,  # type: ignore[arg-type]
        data_revision_ids=("rev-1",),
    )
    assert bare != with_revision


# --- T056 ------------------------------------------------------------------


def test_the_gate_order_is_the_contracted_one() -> None:
    assert gate_order() == (
        "existence",
        "lifecycle",
        "authorization",
        "combination",
        "grain",
        "comparability",
        "coverage",
        "freshness",
        "period",
        "as_of",
    )
    assert len(GATES) == 10


def test_coverage_precedes_freshness_which_precedes_period() -> None:
    """Order is load-bearing: a stale source is refused before its period is
    reasoned about, and whether the days exist is settled before whether they
    are current."""
    order = gate_order()
    assert order.index("coverage") < order.index("freshness") < order.index("period")
    assert order.index("grain") < order.index("coverage")


def test_comparability_sits_between_grain_and_coverage() -> None:
    """Whether two things may be compared is settled before whether the days
    behind them exist — otherwise a refusal sends the reader to fix coverage
    when nobody authorised the comparison in the first place."""
    order = gate_order()
    assert order.index("grain") < order.index("comparability") < order.index("coverage")


def test_gate_10_is_absent_not_stubbed() -> None:
    """A stub that always passes is indistinguishable from a broken gate."""
    assert "retention" not in gate_order()


def test_as_of_segmentation_is_last_and_never_denies() -> None:
    """Gate 11 annotates an allowed decision; it does not gate one.

    Position and non-denial are both contracted (decision-contract §4). A
    segmentation gate that could deny would turn "this range crosses a
    definition change" — a legitimate question — into a refusal.
    """
    assert gate_order()[-1] == "as_of"
    assert outcome_for(ReasonCode.SPANS_DEFINITION_CHANGE) is Outcome.ALLOW_WITH_CAVEAT


def test_authorisation_precedes_combination_in_the_declared_order() -> None:
    order = gate_order()
    assert order.index("authorization") < order.index("combination")
    assert order.index("existence") < order.index("lifecycle") < order.index("authorization")


def test_the_first_denial_short_circuits(bundle: Bundle) -> None:
    """Existence fails first, so nothing downstream reports on the same request."""
    decision = evaluate(
        CatalogValidationRequest(
            metrics=("nao_existe",),
            dimensions=("app_version",),
            sources=("store_a",),
            date_range=WINDOW,
        ),
        bundle,
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        on=ON,
    )
    assert decision.reason_code is ReasonCode.METRIC_NOT_GOVERNED


# --- T057 ------------------------------------------------------------------


def test_the_matrix_enumerates_the_answerable_surface(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    matrix = allowed_combinations(
        bundle,
        access=("standard",),
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        on=ON,
        snapshot=snapshot,
        probe_range=DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31)),
    )
    assert not matrix.is_empty()
    assert set(matrix.metric_ids) == {
        "app_sessions",
        "cohort_retention",
        "cross_source_metric",
        "deprecated_metric",
        "store_downloads",
        "store_rating",
    }, "a deprecated metric is still answerable — with a caveat, not a refusal"
    row = next(r for r in matrix.rows if r.metric_id == "app_sessions" and r.dimension_id is None)
    assert (row.aggregation, row.unit, row.time_dimension) == ("sum", "sessions", "date")
    assert row.grain


def test_the_matrix_omits_what_the_requester_may_not_see(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    """Absent, not listed-and-refused — listing would disclose that it exists."""
    matrix = allowed_combinations(
        bundle,
        access=("standard",),
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        on=ON,
        snapshot=snapshot,
        probe_range=DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31)),
    )
    assert "restricted_metric" not in matrix.metric_ids
    assert "retired_metric" not in matrix.metric_ids


def test_the_matrix_never_lists_an_inapplicable_dimension(
    bundle: Bundle, snapshot: FreshnessSnapshot
) -> None:
    matrix = allowed_combinations(
        bundle,
        access=("standard",),
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        on=ON,
        snapshot=snapshot,
        probe_range=DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31)),
    )
    offenders = [
        r for r in matrix.rows if r.source_id == "store_a" and r.dimension_id == "app_version"
    ]
    assert not offenders


def test_the_matrix_is_empty_without_observed_evidence(bundle: Bundle) -> None:
    """No snapshot means no observed state, so nothing is answerable."""
    matrix = allowed_combinations(
        bundle,
        access=("standard",),
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        on=ON,
    )
    assert matrix.is_empty()


def test_the_production_matrix_is_empty_while_business_inputs_are_open() -> None:
    """An empty answerable surface is the correct report, not a failure."""
    production = build_bundle(
        REPO / "semantic",
        current_commit="0" * 7,
        on=ON,
        source_commits={"subscription_daily": "0" * 7},
    )
    matrix = allowed_combinations(
        production,
        access=("standard",),
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        on=ON,
    )
    assert matrix.is_empty()
    assert matrix.metric_ids == ()
