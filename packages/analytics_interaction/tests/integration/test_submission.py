"""One governed call per side — T099 (FR-031; SC-016).

    Evidence: call-count is exactly one per side, zero speculative.
    — `tasks.md` T099

**Counted, not inspected.** A source scan shows the port has one call site; it
cannot show that a retry, a widening or a fallback does not run it twice. So this
suite replaces `002`'s entry point in the port's own namespace and counts the
crossings, while the port's real code — its fingerprint check, its argument
construction, its single call — runs unchanged.

Three properties, and they fail in different ways:

* **exactly one per submission.** Not zero, which would mean the port stopped
  short; not two, which is a retry nobody asked for and a bill nobody expected;
* **two sides, two calls, distinct requests.** The two-execution route submits
  each side once — the count is 2 and the two date ranges differ. A port that
  submitted the same request twice would show the same count;
* **zero on refusal.** A submission whose fingerprint does not match the resolved
  context reaches the warehouse **not at all**. `FR-031` says nothing
  speculative, and a request executed before its authorization was confirmed is
  the most expensive kind of speculation.
"""

from __future__ import annotations

from datetime import date

import pytest
from analytics_query.contracts.request import AnalyticsQuery, DateRange

from analytics_interaction.authorization.context_preflight import (
    AuthorizedContext,
    resolve_authorization_context,
)
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.intent import ResolvedIntent
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode
from analytics_interaction.contracts.request_build import build_analytics_query
from analytics_interaction.identity.authorization_fingerprint import (
    derive_authorization_fingerprint,
)

from ..conftest import ON, RESOLVED_PRINCIPAL, SUPPLIED_PRINCIPAL
from ..fixtures.counters import CountingResolver, Surfaces
from ..fixtures.submissions import recorded_port

pytestmark = pytest.mark.integration

CORRELATION = "interp-1"


def _request(intent: ResolvedIntent, pair: tuple[AuthorizedContext, str]) -> AnalyticsQuery:
    authorized, fingerprint = pair
    return build_analytics_query(intent, authorized=authorized, auth_fingerprint=fingerprint)


# --- one call, per submission ---------------------------------------------------


def test_one_submission_crosses_the_boundary_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
    resolved_intent: ResolvedIntent,
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    authorized, fingerprint = authorized_pair
    port, recorder = recorded_port(monkeypatch, on=ON)

    port.submit(
        _request(resolved_intent, authorized_pair),
        authorized=authorized,
        auth_fingerprint=fingerprint,
        correlation_id=CORRELATION,
    )

    assert recorder.count == 1


def test_the_request_reaches_the_entry_point_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    resolved_intent: ResolvedIntent,
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """The port submits; it does not rewrite.

    A port that adjusted a range, dropped a filter or widened a source list on
    the way through would be constructing a different question from the one the
    interpretation resolved — and the answer would be about that other question.
    """
    authorized, fingerprint = authorized_pair
    request = _request(resolved_intent, authorized_pair)
    port, recorder = recorded_port(monkeypatch, on=ON)

    port.submit(
        request, authorized=authorized, auth_fingerprint=fingerprint, correlation_id=CORRELATION
    )

    assert recorder.calls[0].request == request


def test_the_correlation_id_is_the_one_supplied(
    monkeypatch: pytest.MonkeyPatch,
    resolved_intent: ResolvedIntent,
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """Never derived from the fingerprint.

    A correlation id derived from the authorization fingerprint would be constant
    across every request one principal ever made — it would correlate a *person*
    in `002`'s audit trail rather than an interaction, which is both the wrong
    grain and a disclosure nobody asked for.
    """
    authorized, fingerprint = authorized_pair
    port, recorder = recorded_port(monkeypatch, on=ON)

    port.submit(
        _request(resolved_intent, authorized_pair),
        authorized=authorized,
        auth_fingerprint=fingerprint,
        correlation_id=CORRELATION,
    )

    recorded = recorder.calls[0]
    assert recorded.correlation_id == CORRELATION
    assert not fingerprint.startswith(recorded.correlation_id)
    assert recorded.principal_ref == RESOLVED_PRINCIPAL.principal_ref


# --- two sides, two calls -------------------------------------------------------


def test_two_sides_are_two_calls_carrying_two_distinct_ranges(
    monkeypatch: pytest.MonkeyPatch,
    resolved_intent: ResolvedIntent,
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """`FR-031` at the grain the two-execution route actually uses.

    The two requests differ in their date range and in nothing else, which is
    what makes them the two sides of one comparison rather than two questions.
    """
    authorized, fingerprint = authorized_pair
    primary = _request(resolved_intent, authorized_pair)
    baseline = primary.model_copy(
        update={"date_range": DateRange(start=date(2026, 6, 1), end=date(2026, 6, 30))}
    )
    port, recorder = recorded_port(monkeypatch, on=ON)

    for side in (primary, baseline):
        port.submit(
            side, authorized=authorized, auth_fingerprint=fingerprint, correlation_id=CORRELATION
        )

    assert recorder.count == 2
    assert recorder.date_ranges() == [
        (date(2026, 7, 1), date(2026, 7, 31)),
        (date(2026, 6, 1), date(2026, 6, 30)),
    ]
    assert recorder.calls[0].correlation_id == recorder.calls[1].correlation_id


def test_the_port_never_submits_a_side_the_caller_did_not(
    monkeypatch: pytest.MonkeyPatch,
    resolved_intent: ResolvedIntent,
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """No speculative baseline, no prefetch, no warm-up.

    One submission is one crossing. A port that anticipated the second side would
    double the bill on every single-request comparison.
    """
    authorized, fingerprint = authorized_pair
    port, recorder = recorded_port(monkeypatch, on=ON)

    port.submit(
        _request(resolved_intent, authorized_pair),
        authorized=authorized,
        auth_fingerprint=fingerprint,
        correlation_id=CORRELATION,
    )

    assert recorder.count == 1
    assert len(recorder.date_ranges()) == 1


# --- zero on refusal ------------------------------------------------------------


def test_a_mismatched_fingerprint_costs_nothing(
    monkeypatch: pytest.MonkeyPatch,
    resolved_intent: ResolvedIntent,
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """Refused **before** the boundary, so the count is zero, not one-and-failed."""
    authorized, fingerprint = authorized_pair
    request = _request(resolved_intent, authorized_pair)
    port, recorder = recorded_port(monkeypatch, on=ON)

    with pytest.raises(ContractViolation) as refusal:
        port.submit(
            request,
            authorized=authorized,
            auth_fingerprint=fingerprint[::-1],
            correlation_id=CORRELATION,
        )

    assert refusal.value.code is InterpretationReasonCode.AUTHORIZATION_CONTEXT_UNRESOLVABLE
    assert recorder.count == 0


def test_a_request_presented_under_another_principals_context_costs_nothing(
    monkeypatch: pytest.MonkeyPatch,
    resolved_intent: ResolvedIntent,
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """The binding the Phase 8 security correction exists for.

    ``principal_ref`` is part of the fingerprint, so a second principal holding
    an identical grant set produces a different one — and a request resolved for
    the first is refused when presented under the second, before any cost.
    """
    _, fingerprint = authorized_pair
    request = _request(resolved_intent, authorized_pair)
    other = resolve_authorization_context(
        SUPPLIED_PRINCIPAL.model_copy(update={"principal_ref": "p-2"}),
        resolver=CountingResolver(
            Surfaces(), answer=RESOLVED_PRINCIPAL.model_copy(update={"principal_ref": "p-2"})
        ),
    )
    port, recorder = recorded_port(monkeypatch, on=ON)

    assert derive_authorization_fingerprint(other) != fingerprint

    with pytest.raises(ContractViolation):
        port.submit(
            request,
            authorized=other,
            auth_fingerprint=fingerprint,
            correlation_id=CORRELATION,
        )

    assert recorder.count == 0
