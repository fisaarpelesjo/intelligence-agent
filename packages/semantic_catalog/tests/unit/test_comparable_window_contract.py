"""The comparable window survives the decision contract — ADR 0016.

This catalog computed a complete comparable window and then published two of its
four fields. The range travelled; the sources and the governed ``chosen_because``
did not. Nothing downstream could recover them, because nothing downstream is
allowed to: the reason a window was narrowed is governed wording, and a consumer
composing one would be telling a reader a basis nobody governed.

So the loss was not a formatting problem. It made the approved two-execution
comparison route impossible to complete end to end, and it did so silently —
every layer behaved correctly and the answer never arrived.

This file is the regression guard for the repair. Four claims:

* **transport** — all four parts survive construction and a JSON round-trip;
* **completeness** — an incomplete or contradictory window is not constructible,
  so the refusal happens where the value is authored;
* **denial** — a `DENY` may not carry a window, because a stated window is an
  instruction and a refusal must not ship one;
* **identity** — the type the coverage gate computes and the type the decision
  carries are the **same type**, which is what stopped them drifting apart in the
  first place.

The window's *calculation* is not under test here; `test_freshness_and_coverage`
owns that and is unchanged. What is under test is whether the value arrives.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from semantic_catalog.contracts.audit_event import EvidenceKind, EvidenceRef
from semantic_catalog.contracts.reason_codes import Outcome, ReasonCode
from semantic_catalog.validation.decision import (
    CatalogDecision,
    ComparableWindow,
    Subject,
    SubjectKind,
)
from semantic_catalog.validation.gates.coverage import ComparableWindow as GateWindow

pytestmark = pytest.mark.unit

JULY = (date(2026, 7, 1), date(2026, 7, 31))
REASON = (
    "janela comparável entre appstore, playstore: interseção das coberturas "
    "observadas, de 2026-07-01 a 2026-07-31 (FR-024)"
)


def _window(
    *,
    start: date = JULY[0],
    end: date = JULY[1],
    sources: tuple[str, ...] = ("appstore", "playstore"),
    chosen_because: str = REASON,
) -> ComparableWindow:
    return ComparableWindow(start=start, end=end, sources=sources, chosen_because=chosen_because)


def _decision(
    window: ComparableWindow | None = None, code: ReasonCode = ReasonCode.REQUEST_ALLOWED
) -> CatalogDecision:
    from semantic_catalog.contracts.reason_codes import outcome_for

    return CatalogDecision(
        decision_id="dec-1",
        policy_version="pol-1",
        catalog_release_id="r-1",
        evaluated_at=datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
        outcome=outcome_for(code),
        reason_code=code,
        message_pt_br="decisão de teste",
        subject=Subject(kind=SubjectKind.REQUEST, id="req-1"),
        evidence_refs=(EvidenceRef(kind=EvidenceKind.CATALOG_RELEASE, id="r-1"),),
        comparable_window=window,
    )


# --- transport ------------------------------------------------------------------


def test_all_four_parts_survive_decision_construction() -> None:
    """The defect, stated as its fix. Two of these used to be dropped."""
    decision = _decision(_window())
    carried = decision.comparable_window
    assert carried is not None
    assert (carried.start, carried.end) == JULY
    assert carried.sources == ("appstore", "playstore")
    assert carried.chosen_because == REASON


def test_all_four_parts_survive_a_json_round_trip() -> None:
    """Serialisation is where a nested value quietly becomes two fields."""
    decision = _decision(_window())
    restored = CatalogDecision.model_validate_json(decision.model_dump_json())

    assert restored.comparable_window == decision.comparable_window
    assert restored.model_dump_json() == decision.model_dump_json()


def test_the_serialised_window_names_every_field() -> None:
    """Read from the payload, not from the object, so nothing is lost in between."""
    payload = json.loads(_decision(_window()).model_dump_json())
    window = payload["comparable_window"]
    assert set(window) == {"start", "end", "sources", "chosen_because"}
    assert window["chosen_because"] == REASON
    assert window["sources"] == ["appstore", "playstore"]


def test_serialisation_is_deterministic() -> None:
    """`SC-005`: identical input, byte-identical output."""
    first = _decision(_window()).model_dump_json()
    second = _decision(_window()).model_dump_json()
    assert first == second


def test_a_decision_stating_no_window_is_unchanged() -> None:
    """Every decision this catalog produces today. Compatibility, asserted."""
    decision = _decision()
    assert decision.comparable_window is None
    assert "null" in decision.model_dump_json()


# --- completeness ---------------------------------------------------------------


@pytest.mark.parametrize(
    "missing",
    [
        pytest.param({"sources": ()}, id="no-sources"),
        pytest.param({"chosen_because": ""}, id="no-reason"),
        pytest.param({"chosen_because": "   "}, id="blank-reason"),
    ],
)
def test_an_incomplete_window_is_not_constructible(missing: dict[str, object]) -> None:
    """The refusal happens where the value is authored, not three layers down.

    A window missing its sources or its reason is exactly what the old transport
    produced — and the whole point of making it unconstructible is that the
    failure now surfaces at the catalog rather than at a consumer that cannot
    tell whether the loss was upstream or its own.
    """
    with pytest.raises(ValidationError):
        _window(**missing)  # type: ignore[arg-type]


def test_a_contradictory_window_refuses() -> None:
    """Ends before it starts. A window nobody could have read over."""
    with pytest.raises(ValidationError, match="ends"):
        _window(start=date(2026, 7, 31), end=date(2026, 7, 1))


def test_an_unknown_field_on_the_window_refuses() -> None:
    """``extra="forbid"``: a typo is an error, not silent data loss."""
    with pytest.raises(ValidationError):
        ComparableWindow(
            start=JULY[0],
            end=JULY[1],
            sources=("appstore",),
            chosen_because=REASON,
            rationale="something else",  # type: ignore[call-arg]
        )


def test_a_bare_range_is_no_longer_accepted_as_a_window() -> None:
    """The lossy shape itself. It cannot be assigned any more."""
    from semantic_catalog.validation.decision import DateRange

    with pytest.raises(ValidationError):
        _decision(DateRange(start=JULY[0], end=JULY[1]))  # type: ignore[arg-type]


def test_a_single_source_window_is_complete_and_not_cross_source() -> None:
    """`BD-1`'s single-source rule still produces a whole window."""
    window = _window(sources=("appstore",), chosen_because="cobertura completa de appstore")
    assert window.is_cross_source is False
    assert _decision(window).comparable_window == window


# --- a denial ships no executable evidence ---------------------------------------


@pytest.mark.parametrize(
    "denial",
    [
        ReasonCode.RANGE_OUTSIDE_COVERAGE,
        ReasonCode.METRICS_NOT_COMPARABLE,
        ReasonCode.PARTIAL_VS_COMPLETE_COMPARISON,
        ReasonCode.ACCESS_DENIED,
    ],
)
def test_a_denied_decision_may_not_carry_a_window(denial: ReasonCode) -> None:
    """A stated window is an instruction; a refusal must not issue one.

    The inference a downstream reader would draw from a window on a denial is
    precisely the wrong one — that the days are agreed, so the comparison may
    proceed.
    """
    with pytest.raises(ValidationError, match="denied decision"):
        _decision(_window(), denial)


def test_a_denial_may_still_carry_its_disclosure() -> None:
    """What a refusal *is* entitled to say is unchanged.

    ``limitations`` and ``answerable_subset`` are already governed as disclosure
    rather than as payload, and neither is affected.
    """
    decision = _decision(None, ReasonCode.METRICS_NOT_COMPARABLE)
    assert decision.outcome is Outcome.DENY
    assert decision.comparable_window is None
    assert decision.limitations == ()


@pytest.mark.parametrize(
    "permitted", [ReasonCode.REQUEST_ALLOWED, ReasonCode.EQUIVALENT_PARTIAL_COMPARISON]
)
def test_a_permitted_decision_may_carry_one(permitted: ReasonCode) -> None:
    """Both permissive outcomes. A caveated comparison still states its window."""
    decision = _decision(_window(), permitted)
    assert decision.comparable_window is not None


# --- one type, computed and carried -----------------------------------------------


def test_the_gate_and_the_contract_name_the_same_type() -> None:
    """The root cause, guarded directly.

    Two types for one concept is what let the published shape drift from the
    computed one. ``gates.coverage`` still exports the name — every existing
    import keeps working — and it is now an alias rather than a second
    definition.
    """
    assert GateWindow is ComparableWindow


def test_a_computed_window_is_directly_assignable() -> None:
    """What the gate produces goes onto the decision with no conversion.

    A conversion step is where the two fields went missing; removing the need for
    one is the repair.
    """
    from semantic_catalog.freshness.external import ObservedCoverage
    from semantic_catalog.validation.gates.coverage import comparable_window

    observed_at = datetime(2026, 8, 13, 6, 0, tzinfo=UTC)
    rows = (
        ObservedCoverage(
            metric="installs",
            source="appstore",
            min_date=JULY[0],
            max_date=JULY[1],
            observed_at=observed_at,
        ),
        ObservedCoverage(
            metric="installs",
            source="playstore",
            min_date=date(2026, 7, 5),
            max_date=date(2026, 7, 20),
            observed_at=observed_at,
        ),
    )
    computed = comparable_window(rows)
    assert computed is not None

    decision = _decision(computed)
    assert decision.comparable_window is computed or decision.comparable_window == computed
    assert decision.comparable_window is not None
    assert decision.comparable_window.chosen_because == computed.chosen_because
    assert decision.comparable_window.sources == computed.sources
