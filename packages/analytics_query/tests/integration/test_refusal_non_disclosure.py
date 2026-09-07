"""Refusal non-disclosure — T066 (FR-011, FR-012, FR-013; SC-009).

An `ACCESS_DENIED` response must reveal nothing about the metric the principal
may not see — not its dimensions, not its grain, not its source list, and
certainly not a value.

The threat is a probing caller: someone who cannot read a metric but can learn
its shape by reading refusals. "You may not see `revenue` broken down by
`country`" tells them `revenue` exists and is dimensioned by country. So the
refusal is asserted **field by field**, and the assertions are written as
denylists over the whole payload rather than checks on the one field someone
remembered.

`FR-013` is the quieter one: a deprecated tag must not be auto-replaced. Granting
a successor silently would hand out access nobody re-approved, and the caller
would never know their grant had changed.
"""

from __future__ import annotations

from datetime import date

import pytest
from semantic_catalog.contracts.audit_event import PrincipalType
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode

from analytics_query.authorization.classify import (
    AUTHORIZATION_DENIAL_CODES,
    PreflightOutcome,
    classify_preflight,
)
from analytics_query.contracts._base import build
from analytics_query.contracts.request import AnalyticsQuery, DateRange
from analytics_query.execution.ledger import AuthorizationContext
from analytics_query.execution.ledger_memory import InMemoryExecutionLedger
from analytics_query.pipeline import PipelineRefusal, run_until_evaluation

from ..fixtures.catalog.decisions import decision
from ..fixtures.observations.reader import FixtureObservationReader

pytestmark = pytest.mark.integration

ON = date(2026, 8, 12)
JULY = DateRange(start=date(2026, 7, 1), end=date(2026, 7, 31))

CONTEXT = AuthorizationContext(
    authorization_scope="tenant-a",
    granted_access_tags=frozenset({"installs:read"}),
    principal_type=PrincipalType.USER.value,
    authorization_policy_pin="authpol-1",
)

#: The four codes gate 3 can emit, ordered so parametrize ids are stable.
DENIAL_CODES: list[ReasonCode] = sorted(AUTHORIZATION_DENIAL_CODES, key=lambda c: c.value)

#: Everything a refusal must not leak about a metric the caller may not see.
STRUCTURAL_LEAKS = (
    "country",
    "platform",
    "store",
    "app_version",
    "product",
    "grain",
    "daily",
    "monthly",
    "google_play",
    "ios_app",
    "source_view",
    "semantic.",
    "sum",
    "count_distinct",
    "aggregation",
    "allowed_dimensions",
    "time_dimension",
)


def _refuse(code: ReasonCode) -> PipelineRefusal:
    request = build(AnalyticsQuery, metrics=("revenue",), date_range=JULY)

    def evaluate(_request: object, _bundle: object, **_kwargs: object) -> object:
        return decision(outcome=Outcome.DENY, reason_code=code, subject_id="revenue")

    with pytest.raises(PipelineRefusal) as caught:
        run_until_evaluation(
            request,
            evaluate=evaluate,  # type: ignore[arg-type]
            catalog_bundle=object(),  # type: ignore[arg-type]
            ledger=InMemoryExecutionLedger(),
            observations=FixtureObservationReader(),
            context=CONTEXT,
            correlation_id="c-1",
            principal_ref="p-1",
            on=ON,
            catalog_release_id="r-1",
            required_sources=frozenset({"google_play"}),
        )
    return caught.value


@pytest.mark.parametrize("code", DENIAL_CODES, ids=[c.value for c in DENIAL_CODES])
def test_an_authorization_refusal_reveals_no_metric_structure(code: ReasonCode) -> None:
    refusal = _refuse(code)
    text = str(refusal).lower()
    for leak in STRUCTURAL_LEAKS:
        assert leak not in text, f"{code.value} leaked {leak!r}"


@pytest.mark.parametrize("code", DENIAL_CODES, ids=[c.value for c in DENIAL_CODES])
def test_every_authorization_denial_stops_at_the_authorization_stage(code: ReasonCode) -> None:
    """All four codes are terminal, not just `ACCESS_DENIED`."""
    assert _refuse(code).stage == "authorization"


@pytest.mark.parametrize("code", DENIAL_CODES, ids=[c.value for c in DENIAL_CODES])
def test_every_authorization_denial_classifies_as_denied(code: ReasonCode) -> None:
    denied = decision(outcome=Outcome.DENY, reason_code=code)
    assert classify_preflight(denied) is PreflightOutcome.AUTHORIZATION_DENIED


def test_the_refusal_carries_the_upstream_code_not_a_restatement() -> None:
    """`002` does not re-code an authorisation decision it did not make."""
    refusal = _refuse(ReasonCode.ACCESS_DENIED)
    assert refusal.code is ReasonCode.ACCESS_DENIED


def test_a_deprecated_tag_is_not_silently_replaced() -> None:
    """`FR-013`: no successor is granted automatically.

    A deprecated tag refuses like any other authorisation failure. If a
    replacement were granted here, access nobody re-approved would flow, and the
    caller would have no way to notice.
    """
    refusal = _refuse(ReasonCode.ACCESS_TAG_DEPRECATED)
    assert refusal.stage == "authorization"
    assert refusal.code is ReasonCode.ACCESS_TAG_DEPRECATED
    text = str(refusal).lower()
    for word in ("successor", "replacement", "instead", "granted"):
        assert word not in text


def test_the_four_denial_codes_are_exactly_the_pinned_set() -> None:
    assert {c.value for c in AUTHORIZATION_DENIAL_CODES} == {
        "ACCESS_DENIED",
        "ACCESS_TAG_UNKNOWN",
        "ACCESS_TAG_DEPRECATED",
        "ACCESS_TAG_SCOPE_MISMATCH",
    }


def test_a_refusal_carries_no_value() -> None:
    text = str(_refuse(ReasonCode.ACCESS_DENIED))
    assert not any(character.isdigit() for character in text.replace("001", "").replace("002", ""))
