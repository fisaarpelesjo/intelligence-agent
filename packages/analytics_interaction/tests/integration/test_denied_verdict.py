"""A denied verdict costs nothing — T102 (FR-065; SC-037).

    Evidence: counted zero execution-port calls. — `tasks.md` T102

The ordering claim is the whole point: **the complete governed comparison verdict
is obtained before either side executes.** A system that executed first and
checked afterwards would produce the same refusal to the caller and a very
different invoice — and, worse, would have run a query the catalog said must not
run.

So this suite runs the real sequence — verdict, then gate, then submission — and
counts what the warehouse boundary saw. Counted at **two** levels, because they
fail differently:

* the six-surface counter from `T046`, which shows nothing anywhere was touched;
* the ADR 0010 entry point itself, replaced in the port's own namespace, which
  shows the port never crossed the boundary.

**One evaluation, and it happens before anything else.** The counting evaluator
records each call, so "two single-side evaluations were combined into a verdict"
(`FR-065`, `SC-036`) is a countable failure rather than a design intention.

**Permitted verdicts still execute.** A suite that only asserted the denial would
pass against a gate that refused everything. ``ALLOW`` and ``ALLOW_WITH_CAVEAT``
are asserted through to a submission, and the caveated case is the one that
matters: a caveat qualifies an answer, it does not withhold one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import cast

import pytest
from analytics_query.contracts.request import AnalyticsQuery, DateRange
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode
from semantic_catalog.loader.bundle import Bundle
from semantic_catalog.validation.decision import CatalogDecision, CatalogValidationRequest

from analytics_interaction.authorization.context_preflight import AuthorizedContext
from analytics_interaction.comparison.permitted import (
    EXECUTABLE_OUTCOMES,
    ComparisonDenied,
    is_executable,
    permitted_verdict,
)
from analytics_interaction.comparison.verdict import comparison_verdict
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.comparison import ComparisonIntent, ComparisonRoute
from analytics_interaction.contracts.intent import ResolvedIntent, ResolvedPeriod
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode
from analytics_interaction.contracts.request_build import build_analytics_query
from analytics_interaction.execution.port import GovernedExecutionPort
from analytics_interaction.interpretation.period import resolve_explicit_period

from ..conftest import ON, REFERENCE
from ..fixtures.counters import Surfaces
from ..fixtures.decisions import ALLOWED, CAVEATED, DENIED, decision
from ..fixtures.submissions import recorded_port

pytestmark = pytest.mark.integration

CORRELATION = "interp-denied"
JUNE = (date(2026, 6, 1), date(2026, 6, 30))


@dataclass
class CountingEvaluator:
    """`001`'s ``evaluate``, counted, answering with a chosen verdict.

    Records the requests as well as the count: "evaluated once" and "evaluated
    once, about the comparison" are different claims, and only the recorded
    request distinguishes a comparison verdict from a single-side one.
    """

    surfaces: Surfaces
    answer: CatalogDecision
    requests: list[CatalogValidationRequest] = field(default_factory=list[CatalogValidationRequest])

    def __call__(
        self, request: CatalogValidationRequest, bundle: object, **_kwargs: object
    ) -> CatalogDecision:
        del bundle  # named to satisfy the port's Protocol; never read
        self.surfaces.catalog += 1
        self.requests.append(request)
        return self.answer


def _two_execution() -> ComparisonIntent:
    """July against June: the one shape that needs two governed executions."""
    start, end = JUNE
    return ComparisonIntent(
        kind="period_over_period",
        route=ComparisonRoute.TWO_EXECUTION,
        baseline_period=resolve_explicit_period(start, end, reference_date=REFERENCE, on=ON),
    )


def _verdict(
    intent: ResolvedIntent,
    pair: tuple[AuthorizedContext, str],
    code: ReasonCode,
    surfaces: Surfaces,
) -> tuple[CatalogDecision, CountingEvaluator]:
    authorized, fingerprint = pair
    evaluator = CountingEvaluator(surfaces, decision(code))
    verdict = comparison_verdict(
        intent,
        _two_execution(),
        authorized=authorized,
        auth_fingerprint=fingerprint,
        evaluate=evaluator,
        # Never read: the evaluator *is* the boundary in this suite, and a real
        # bundle would tie every verdict test to `001`'s fixture catalog.
        bundle=cast("Bundle", None),
        on=ON,
    )
    return verdict, evaluator


def _gate_then_submit(
    port: GovernedExecutionPort,
    verdict: CatalogDecision,
    request: AnalyticsQuery,
    pair: tuple[AuthorizedContext, str],
) -> None:
    """The real sequence, in the real order: gate, then submit.

    Written as one function so the ordering under test is the ordering the code
    performs. A test that called ``permitted_verdict`` inside a ``raises`` block
    and the port outside it would be asserting against its own arrangement rather
    than against the sequence.
    """
    authorized, fingerprint = pair
    permitted_verdict(verdict)
    port.submit(
        request, authorized=authorized, auth_fingerprint=fingerprint, correlation_id=CORRELATION
    )


# --- the denial costs nothing ---------------------------------------------------


def test_a_denied_verdict_reaches_no_execution_port(
    monkeypatch: pytest.MonkeyPatch,
    resolved_intent: ResolvedIntent,
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """`SC-037`, counted at the boundary itself."""
    authorized, fingerprint = authorized_pair
    surfaces = Surfaces()
    port, recorder = recorded_port(monkeypatch, on=ON)
    request = build_analytics_query(
        resolved_intent, authorized=authorized, auth_fingerprint=fingerprint
    )

    verdict, _ = _verdict(resolved_intent, authorized_pair, DENIED, surfaces)

    with pytest.raises(ComparisonDenied):
        _gate_then_submit(port, verdict, request, authorized_pair)

    assert recorder.count == 0
    assert surfaces.execution == 0


def test_neither_side_of_a_denied_comparison_executes(
    monkeypatch: pytest.MonkeyPatch,
    resolved_intent: ResolvedIntent,
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """Whole-comparison refusal: not "the valid side ran and the other did not"."""
    authorized, fingerprint = authorized_pair
    surfaces = Surfaces()
    port, recorder = recorded_port(monkeypatch, on=ON)
    primary = build_analytics_query(
        resolved_intent, authorized=authorized, auth_fingerprint=fingerprint
    )
    start, end = JUNE
    baseline = primary.model_copy(update={"date_range": DateRange(start=start, end=end)})
    verdict, _ = _verdict(resolved_intent, authorized_pair, DENIED, surfaces)

    for side in (primary, baseline):
        with pytest.raises(ComparisonDenied):
            _gate_then_submit(port, verdict, side, authorized_pair)

    assert recorder.count == 0


def test_the_denial_carries_001s_own_reason_code(
    resolved_intent: ResolvedIntent,
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """`FR-021`: the refusal names where it came from.

    Re-coding it into this feature's namespace would tell the caller the
    interaction layer refused when the catalog did.
    """
    surfaces = Surfaces()
    verdict, _ = _verdict(resolved_intent, authorized_pair, DENIED, surfaces)

    with pytest.raises(ComparisonDenied) as denial:
        permitted_verdict(verdict)

    assert denial.value.code is DENIED
    assert denial.value.decision.message_pt_br == verdict.message_pt_br
    assert denial.value.decision is verdict


# --- one evaluation, before anything else ---------------------------------------


def test_the_verdict_is_one_evaluation_over_the_comparison_as_presented(
    resolved_intent: ResolvedIntent,
    authorized_pair: tuple[AuthorizedContext, str],
    july_period: ResolvedPeriod,
) -> None:
    """`SC-036`: one call, carrying both ranges.

    Two independent single-side evaluations would show a count of two and two
    requests with no ``comparison`` on either.
    """
    surfaces = Surfaces()
    _, evaluator = _verdict(resolved_intent, authorized_pair, ALLOWED, surfaces)

    assert surfaces.catalog == 1
    assert len(evaluator.requests) == 1

    submitted = evaluator.requests[0]
    assert submitted.comparison is not None
    assert (
        submitted.comparison.baseline_range.start,
        submitted.comparison.baseline_range.end,
    ) == JUNE
    assert (submitted.date_range.start, submitted.date_range.end) == (
        july_period.start,
        july_period.end,
    )


def test_nothing_executes_while_the_verdict_is_being_obtained(
    monkeypatch: pytest.MonkeyPatch,
    resolved_intent: ResolvedIntent,
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """Ordering, counted: the boundary is untouched at the moment of the verdict."""
    surfaces = Surfaces()
    _, recorder = recorded_port(monkeypatch, on=ON)

    _verdict(resolved_intent, authorized_pair, ALLOWED, surfaces)

    assert recorder.count == 0
    assert surfaces.touched() == ["catalog"]


# --- permitted verdicts do execute ----------------------------------------------


@pytest.mark.parametrize("code", [ALLOWED, CAVEATED])
def test_a_permitted_verdict_executes(
    monkeypatch: pytest.MonkeyPatch,
    resolved_intent: ResolvedIntent,
    authorized_pair: tuple[AuthorizedContext, str],
    code: ReasonCode,
) -> None:
    """`SC-019`, `SC-020`: a caveat qualifies an answer, it does not withhold one."""
    authorized, fingerprint = authorized_pair
    surfaces = Surfaces()
    port, recorder = recorded_port(monkeypatch, on=ON)
    request = build_analytics_query(
        resolved_intent, authorized=authorized, auth_fingerprint=fingerprint
    )
    verdict, _ = _verdict(resolved_intent, authorized_pair, code, surfaces)

    permitted = permitted_verdict(verdict)
    port.submit(
        request, authorized=authorized, auth_fingerprint=fingerprint, correlation_id=CORRELATION
    )

    assert permitted is verdict
    assert recorder.count == 1


def test_the_permitted_verdict_is_returned_unchanged(
    resolved_intent: ResolvedIntent,
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """Everything `001` said survives the gate — the caveats especially."""
    surfaces = Surfaces()
    verdict, _ = _verdict(resolved_intent, authorized_pair, CAVEATED, surfaces)

    permitted = permitted_verdict(verdict)

    assert permitted is verdict
    assert permitted.reason_code is CAVEATED
    assert permitted.outcome is Outcome.ALLOW_WITH_CAVEAT
    assert permitted.limitations == verdict.limitations


# --- authorization comes first --------------------------------------------------


def test_a_fingerprint_mismatch_validates_nothing_and_executes_nothing(
    monkeypatch: pytest.MonkeyPatch,
    resolved_intent: ResolvedIntent,
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """Authorization precedes comparison validation, counted on both surfaces.

    The corrected Phase 8 fingerprint binds ``principal_ref``, so an intent
    resolved for one principal cannot be validated under another's context. The
    check runs **before** the evaluator, which is why the catalog count is zero
    rather than one-and-refused — a catalog read for a principal who never asked
    is work performed, and `FR-089` counts work.
    """
    authorized, fingerprint = authorized_pair
    surfaces = Surfaces()
    evaluator = CountingEvaluator(surfaces, decision(ALLOWED))
    _, recorder = recorded_port(monkeypatch, on=ON)

    with pytest.raises(ContractViolation) as refusal:
        comparison_verdict(
            resolved_intent,
            _two_execution(),
            authorized=authorized,
            auth_fingerprint=fingerprint[::-1],
            evaluate=evaluator,
            bundle=cast("Bundle", None),
            on=ON,
        )

    assert refusal.value.code is InterpretationReasonCode.AUTHORIZATION_CONTEXT_UNRESOLVABLE
    assert surfaces.catalog == 0
    assert evaluator.requests == []
    assert recorder.count == 0
    assert surfaces.all_zero()


# --- the closed set -------------------------------------------------------------


def test_exactly_two_outcomes_execute() -> None:
    """Written as a set so a third permissive outcome upstream fails here loudly."""
    assert set(EXECUTABLE_OUTCOMES) == {Outcome.ALLOW, Outcome.ALLOW_WITH_CAVEAT}
    assert Outcome.DENY not in EXECUTABLE_OUTCOMES


@pytest.mark.parametrize(
    ("code", "executable"),
    [
        (ReasonCode.REQUEST_ALLOWED, True),
        (ReasonCode.EQUIVALENT_PARTIAL_COMPARISON, True),
        (ReasonCode.COMPARABLE_WITH_CAVEAT, True),
        (ReasonCode.PARTIAL_VS_COMPLETE_COMPARISON, False),
        (ReasonCode.METRICS_NOT_COMPARABLE, False),
        (ReasonCode.ACCESS_DENIED, False),
    ],
)
def test_the_verdict_matrix(code: ReasonCode, executable: bool) -> None:
    """The named cases from `T101`'s evidence line, and the neighbours."""
    assert is_executable(decision(code)) is executable


# --- unknown, malformed, missing, contradictory ---------------------------------


def test_a_missing_verdict_refuses() -> None:
    """Absence is never permission — and this is the shape the defect takes."""
    with pytest.raises(ContractViolation) as refusal:
        permitted_verdict(None)
    assert refusal.value.code is InterpretationReasonCode.COMPARISON_SIDE_INVALID


@pytest.mark.parametrize(
    "impostor",
    [
        "ALLOW",
        {"outcome": Outcome.ALLOW},
        Outcome.ALLOW,
    ],
)
def test_a_malformed_verdict_refuses(impostor: object) -> None:
    """A duck-typed stand-in carries no evidence, no message and no reason code."""
    with pytest.raises(ContractViolation) as refusal:
        permitted_verdict(impostor)
    assert refusal.value.code is InterpretationReasonCode.COMPARISON_SIDE_INVALID


def test_an_outcome_that_disagrees_with_its_reason_code_cannot_even_be_built() -> None:
    """`001` refuses it at construction, so the contradiction never reaches the gate.

    Asserted rather than assumed: the redundant check in ``permitted_verdict``
    is only redundant while this holds.
    """
    with pytest.raises(ValueError, match="classified"):
        decision(DENIED, outcome=Outcome.ALLOW)
