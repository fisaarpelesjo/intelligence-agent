"""Fail-closed tests — T060 (FR-040, FR-072, FR-073; quickstart Scenario 20).

Unknown identifiers, unresolvable policies and unusable access tags all DENY.
None of them falls through, defaults, or proceeds on the assumption that a later
gate will catch it.

The two policy cases are the ones worth stating plainly, because both look like
they have an obvious answer and neither may take it:

* **no effective policy** — there is no default to assume, and a decision
  evaluated under a policy nobody approved is unauditable;
* **more than one effective policy** — preferring the newest or the
  higher-numbered one would be code inventing the tie-break that governance is
  supposed to make impossible.

Both return ``POLICY_UNRESOLVABLE`` / DENY.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest
import yaml

from semantic_catalog.contracts.access_tag import AccessTagRegistry, PrincipalType, TagDenial
from semantic_catalog.contracts.policy import CatalogPolicy
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode
from semantic_catalog.freshness.external import FreshnessSnapshot, load_snapshot
from semantic_catalog.loader.bundle import Bundle, build_bundle
from semantic_catalog.loader.load import LoadedCatalog
from semantic_catalog.validation.decision import (
    CatalogDecision,
    CatalogValidationRequest,
    DateRange,
    Subject,
    SubjectKind,
)
from semantic_catalog.validation.gates.authorization import DENIAL_TO_REASON
from semantic_catalog.validation.pipeline import evaluate
from semantic_catalog.validation.policy_runtime import resolve_policy

pytestmark = pytest.mark.unit

from pathlib import Path  # noqa: E402  (kept next to the paths it defines)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "decision_matrix"
CATALOG = FIXTURES / "catalog"
FRESHNESS = Path(__file__).resolve().parents[1] / "fixtures" / "freshness"
COMMIT = "fixture0"
ON = date(2026, 8, 11)
WINDOW = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))


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


def _decide(
    bundle: Bundle,
    *,
    scope: str = "default",
    access: tuple[str, ...] = (),
    snapshot: FreshnessSnapshot | None = None,
    **kwargs: object,
) -> CatalogDecision:
    request = CatalogValidationRequest(
        date_range=WINDOW,
        requester_access=access,
        **kwargs,  # type: ignore[arg-type]
    )
    return evaluate(
        request,
        bundle,
        principal_type=PrincipalType.USER,
        authorization_scope=scope,
        on=ON,
        snapshot=snapshot,
    )


# --- unknown identifiers ---------------------------------------------------


@pytest.mark.parametrize(
    "metrics, dimensions, sources, code, kind",
    [
        (("nao_existe",), (), (), ReasonCode.METRIC_NOT_GOVERNED, SubjectKind.METRIC),
        (
            ("app_sessions",),
            ("nao_existe",),
            (),
            ReasonCode.DIMENSION_NOT_GOVERNED,
            SubjectKind.DIMENSION,
        ),
        (
            ("app_sessions",),
            (),
            ("nao_existe",),
            ReasonCode.SOURCE_NOT_GOVERNED,
            SubjectKind.SOURCE,
        ),
    ],
)
def test_unknown_identifiers_deny_and_name_the_offender(
    bundle: Bundle,
    metrics: tuple[str, ...],
    dimensions: tuple[str, ...],
    sources: tuple[str, ...],
    code: ReasonCode,
    kind: SubjectKind,
) -> None:
    decision = _decide(
        bundle,
        access=("standard",),
        metrics=metrics,
        dimensions=dimensions,
        sources=sources,
    )
    assert decision.outcome is Outcome.DENY
    assert decision.reason_code is code
    assert decision.subject.kind is kind
    assert decision.subject.id == "nao_existe"


def test_an_unknown_metric_denies_before_authorisation_is_consulted(bundle: Bundle) -> None:
    """Existence first — an unknown name is not an authorisation question."""
    decision = _decide(bundle, metrics=("nao_existe",), access=())
    assert decision.reason_code is ReasonCode.METRIC_NOT_GOVERNED


# --- policy ---------------------------------------------------------------


def _policy_variant(catalog: LoadedCatalog, **overrides: object) -> CatalogPolicy:
    payload = catalog.policies[0].model_dump(mode="json")
    payload.update(overrides)
    return CatalogPolicy.model_validate(payload)


def test_no_effective_policy_denies(bundle: Bundle) -> None:
    empty = replace(bundle.internal, policies=())
    resolution = resolve_policy(empty, on=ON)
    assert not resolution.resolved
    assert resolution.reason_code is ReasonCode.POLICY_UNRESOLVABLE

    decision = evaluate(
        CatalogValidationRequest(metrics=("app_sessions",), date_range=WINDOW),
        replace(bundle, internal=empty),
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        on=ON,
    )
    assert decision.outcome is Outcome.DENY
    assert decision.reason_code is ReasonCode.POLICY_UNRESOLVABLE
    assert decision.subject.kind is SubjectKind.POLICY


def test_a_policy_not_yet_effective_denies(bundle: Bundle) -> None:
    """Before any policy exists is the same as no policy: refuse."""
    resolution = resolve_policy(bundle.internal, on=date(2025, 12, 31))
    assert not resolution.resolved
    assert resolution.reason_code is ReasonCode.POLICY_UNRESOLVABLE


def test_two_effective_policies_deny_rather_than_picking_one(bundle: Bundle) -> None:
    """Ambiguity is never resolved by preference — not by version, not by order."""
    rival = _policy_variant(bundle.internal, policy_id="rival_policy", policy_version=9)
    ambiguous = replace(bundle.internal, policies=(bundle.internal.policies[0], rival))

    resolution = resolve_policy(ambiguous, on=ON)
    assert not resolution.resolved
    assert resolution.reason_code is ReasonCode.POLICY_UNRESOLVABLE
    assert "2 catalog policies" in resolution.detail

    decision = evaluate(
        CatalogValidationRequest(metrics=("app_sessions",), date_range=WINDOW),
        replace(bundle, internal=ambiguous),
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        on=ON,
    )
    assert decision.reason_code is ReasonCode.POLICY_UNRESOLVABLE
    assert decision.policy_version == "unresolved"


def test_every_decision_records_its_resolved_policy_version(bundle: Bundle) -> None:
    decision = _decide(
        bundle,
        metrics=("app_sessions",),
        sources=("app_a",),
        access=("standard",),
        snapshot=load_snapshot(FRESHNESS / "complete.yaml"),
    )
    assert decision.policy_version == "fixture_policy@1"
    assert decision.outcome is Outcome.ALLOW


# --- access tags -----------------------------------------------------------


def test_a_tag_absent_from_the_registry_denies() -> None:
    registry = AccessTagRegistry.model_validate(
        yaml.safe_load((CATALOG / "governance" / "access-tags.yaml").read_text(encoding="utf-8"))
    )
    assert (
        registry.authorize(
            "not_in_registry",
            principal_type=PrincipalType.USER,
            authorization_scope="default",
            on=ON,
        )
        is TagDenial.UNKNOWN
    )


def test_a_deprecated_tag_denies_even_with_a_valid_replacement(bundle: Bundle) -> None:
    decision = _decide(
        bundle, metrics=("retired_metric",), sources=("app_a",), access=("retired_tag",)
    )
    assert decision.outcome is Outcome.DENY
    assert decision.reason_code is ReasonCode.ACCESS_TAG_DEPRECATED
    assert decision.subject.id == "retired_tag"


def test_a_scope_mismatch_denies(bundle: Bundle) -> None:
    decision = _decide(
        bundle, metrics=("restricted_metric",), sources=("app_a",), access=("restricted",)
    )
    assert decision.reason_code is ReasonCode.ACCESS_TAG_SCOPE_MISMATCH


def test_holding_no_tag_denies(bundle: Bundle) -> None:
    decision = _decide(bundle, metrics=("app_sessions",), sources=("app_a",), access=())
    assert decision.reason_code is ReasonCode.ACCESS_DENIED
    assert decision.subject.id == "app_sessions"


def test_an_absent_registry_denies_rather_than_authorising(bundle: Bundle) -> None:
    stripped = replace(bundle.internal, access_tags=None)
    decision = evaluate(
        CatalogValidationRequest(metrics=("app_sessions",), sources=("app_a",), date_range=WINDOW),
        replace(bundle, internal=stripped),
        principal_type=PrincipalType.USER,
        authorization_scope="default",
        on=ON,
    )
    assert decision.outcome is Outcome.DENY
    assert decision.reason_code is ReasonCode.ACCESS_TAG_UNKNOWN


def test_every_registry_denial_maps_to_a_stable_reason_code() -> None:
    """No denial path may fall off the map into an unhandled branch."""
    assert set(DENIAL_TO_REASON) == set(TagDenial)
    for code in DENIAL_TO_REASON.values():
        assert code in ReasonCode


# --- the decision itself ---------------------------------------------------


def test_a_decision_cannot_be_constructed_without_a_reason_code() -> None:
    from pydantic import ValidationError

    from semantic_catalog.contracts.audit_event import EvidenceKind, EvidenceRef

    with pytest.raises(ValidationError):
        CatalogDecision(  # type: ignore[call-arg]
            decision_id="d",
            policy_version="p@1",
            catalog_release_id="r",
            evaluated_at=date(2026, 8, 11),  # type: ignore[arg-type]
            outcome=Outcome.DENY,
            subject=Subject(kind=SubjectKind.METRIC, id="x"),
            evidence_refs=(EvidenceRef(kind=EvidenceKind.CATALOG_RELEASE, id="r"),),
        )


def test_an_allow_audit_event_is_constructible() -> None:
    """P1's real point: without an ALLOW-classified code this was impossible."""
    from semantic_catalog.contracts.audit_event import (
        CatalogDecisionAuditEvent,
        RequestedOperation,
    )

    event = CatalogDecisionAuditEvent(
        correlation_id="corr-1",
        occurred_at=datetime(2026, 8, 11, tzinfo=UTC),
        decision_id="sha256:abc",
        principal_id="prn_" + "a" * 20,
        principal_type=PrincipalType.USER,
        requested_operation=RequestedOperation.VALIDATE,
        outcome=Outcome.ALLOW,
        reason_code=ReasonCode.REQUEST_ALLOWED,
        policy_version="fixture_policy@1",
        catalog_release_id="sha256:rel",
    )
    assert event.outcome is Outcome.ALLOW
    assert event.reason_code is ReasonCode.REQUEST_ALLOWED


def test_an_outcome_may_not_disagree_with_its_reason_code() -> None:
    from pydantic import ValidationError

    from semantic_catalog.contracts.audit_event import EvidenceKind, EvidenceRef

    with pytest.raises(ValidationError, match="classified DENY"):
        CatalogDecision(
            decision_id="d",
            policy_version="p@1",
            catalog_release_id="r",
            evaluated_at=date(2026, 8, 11),  # type: ignore[arg-type]
            outcome=Outcome.ALLOW_WITH_CAVEAT,
            reason_code=ReasonCode.METRIC_PENDING,
            message_pt_br="qualquer",
            subject=Subject(kind=SubjectKind.METRIC, id="x"),
            evidence_refs=(EvidenceRef(kind=EvidenceKind.CATALOG_RELEASE, id="r"),),
        )


# --- the production catalog stays refused ---------------------------------


def test_the_production_catalog_refuses_every_metric_as_pending() -> None:
    """The fail-closed state, asserted through the gates rather than the models."""
    repo = Path(__file__).resolve().parents[4]
    production = build_bundle(
        repo / "semantic",
        current_commit="0" * 7,
        on=ON,
        source_commits={"subscription_daily": "0" * 7},
    )
    for metric_id in sorted(production.internal.metrics):
        decision = evaluate(
            CatalogValidationRequest(
                metrics=(metric_id,), date_range=WINDOW, requester_access=("standard",)
            ),
            production,
            principal_type=PrincipalType.USER,
            authorization_scope="default",
            on=ON,
        )
        assert decision.outcome is Outcome.DENY, metric_id
        assert decision.reason_code is ReasonCode.METRIC_PENDING, metric_id
