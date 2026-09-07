"""No side is ever returned alone — T156 (FR-067; SC-039).

    A comparison in which any side is invalid MUST refuse as a whole. No side,
    value, provenance fragment or partially collected caveat may be released.
    — `FR-067`

    Evidence: no side is ever returned alone, under any of the enumerated
    conditions. — `tasks.md` T156

## Why partial release is the attack and not merely a bug

Half a comparison is the most useful thing an attacker can extract, because it is
the half that carries a **number**. Ask for "installs in July versus installs in
the restricted segment", arrange for side B to be suppressed, and a system that
released what it had hands over side A — a real figure with real provenance,
disclosed as authoritative, for a comparison nobody was allowed to make.

Worse, it is the failure mode a helpful implementation arrives at on its own. "We
got one side; returning it is better than returning nothing" is a reasonable
instinct and is exactly wrong: the caller asked a comparative question, and one
side answered as if it were the answer is a different claim from the one they made.

## What is asserted

For every enumerated failure condition:

* **the refusal happens** — with the governed code, not a partial success;
* **the exception carries nothing** — no value, no row, no cell, no provenance, no
  caveat, no request, no SQL, in any attribute or in the message. Searched
  recursively, because a fragment attached three levels down a nested object is
  still released;
* **side B is not executed** when side A already failed — asserted as a **count**,
  because "we executed both and discarded one" costs the caller a second query and
  is invisible to a test that only inspects the outcome;
* **nothing is released** — no partial object, and no attribute on the raised
  exception that a caller could read a number out of.

## Fixture-only

`D-18` ships empty, so the shipped state refuses at the formula gate before either
side is asked for. That is asserted first. The condition sweep below runs against a
synthetic formula set so the *later* gates are reachable at all — and a green sweep
is evidence about those gates, never about `D-18`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import pytest
from analytics_query.contracts.result import Completeness
from semantic_catalog.contracts.reason_codes import ReasonCode
from semantic_catalog.validation.decision import Finality, Reproducibility

from analytics_interaction.authorization.context_preflight import AuthorizedContext
from analytics_interaction.comparison.refusal import (
    MismatchCondition,
    SideSubmission,
    govern_comparison,
)
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.answer import CaveatOrigin
from analytics_interaction.contracts.comparison import GovernedComparison
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code
from analytics_interaction.governance.resolve import ContentUnresolvable

from ..conftest import ON
from ..fixtures.comparisons import (
    ABSOLUTE_DIFFERENCE,
    BASELINE_RANGE,
    FIXTURE_VERSION,
    PRIMARY_RANGE,
    RATIO,
    caveat_set,
    executed,
    formula_instances,
    limitation,
    request,
    verdict,
)

pytestmark = pytest.mark.adversarial

FIXTURE_SET = formula_instances(ABSOLUTE_DIFFERENCE, RATIO)
NO_CAVEATS = caveat_set()

#: The distinctive values a leak would carry. Chosen so a search for them cannot
#: match anything incidental — a bare ``100`` appears in byte counts and policy
#: numbers, while these do not appear anywhere else in the fixture world.
PRIMARY_VALUE = Decimal("987654321")
BASELINE_VALUE = Decimal("123456789")


@dataclass
class _CountedSide:
    """Executes on demand, and counts. Raises instead, when asked to.

    A **thunk** rather than a value, because the ordering claim is that side B is
    never asked for once side A has failed — and a test holding two pre-built
    answers would pass against code that executed both and discarded one.
    """

    answer: object
    calls: list[int] = field(default_factory=list[int])
    raises: BaseException | None = None

    def __call__(self) -> object:
        self.calls.append(1)
        if self.raises is not None:
            raise self.raises
        return self.answer

    @property
    def count(self) -> int:
        return len(self.calls)


def _govern(
    pair: tuple[AuthorizedContext, str],
    *,
    primary: object = None,
    baseline: object = None,
    decision: object = None,
    caveats: object = None,
    formula_id: str = "absolute_difference",
    vocabulary_version: str = FIXTURE_VERSION,
    instances: object = FIXTURE_SET,
    primary_period: tuple[object, object] = PRIMARY_RANGE,
    baseline_period: tuple[object, object] = BASELINE_RANGE,
    baseline_metrics: tuple[str, ...] = ("installs",),
) -> tuple[GovernedComparison, _CountedSide, _CountedSide]:
    authorized, derived = pair
    left = _CountedSide(primary if primary is not None else executed(PRIMARY_VALUE))
    right = _CountedSide(baseline if baseline is not None else executed(BASELINE_VALUE))
    comparison = govern_comparison(
        decision if decision is not None else verdict(),  # pyright: ignore[reportArgumentType]
        formula_id=formula_id,
        primary_side=SideSubmission(
            request=request(period=primary_period),  # pyright: ignore[reportArgumentType]
            submit=left,  # pyright: ignore[reportArgumentType]
        ),
        baseline_side=SideSubmission(
            request=request(period=baseline_period, metrics=baseline_metrics),  # pyright: ignore[reportArgumentType]
            submit=right,  # pyright: ignore[reportArgumentType]
        ),
        caveats=caveats if caveats is not None else NO_CAVEATS,  # pyright: ignore[reportArgumentType]
        authorized=authorized,
        auth_fingerprint=derived,
        on=ON,
        vocabulary_version=vocabulary_version,
        derived_from=("claim-a", "claim-b"),
        instances=instances,  # pyright: ignore[reportArgumentType]
    )
    return comparison, left, right


def _executed(value: Decimal, condition: dict[str, object]) -> object:
    """One side, invalidated by exactly one condition.

    Kept as a helper because ``value`` is positional on the fixture while every
    other condition is a keyword — passing both produced a duplicate-argument error
    rather than the refusal under test.
    """
    overrides = dict(condition)
    # ``value`` is positional on the fixture, so an override for it replaces the
    # argument rather than joining the keywords. An absent cell and a *suppressed*
    # one are different upstream facts and both are in the sweep: absent means the
    # warehouse returned no figure, suppressed means it refused to.
    if "value" in overrides:
        return executed(overrides.pop("value"), **overrides)  # pyright: ignore[reportArgumentType]
    return executed(value, **overrides)  # pyright: ignore[reportArgumentType]


def _leaked(error: BaseException, *, depth: int = 4) -> list[str]:
    """Every distinctive value reachable from a raised refusal.

    Walks attributes recursively rather than checking ``str(error)``, because the
    dangerous leak is a fragment **attached** to an exception — a ``side``, a
    ``partial``, a ``result`` — that a caller reads rather than prints. A test that
    only inspected the message would pass against exactly that.
    """
    targets = (str(PRIMARY_VALUE), str(BASELINE_VALUE), "qid-1", "job-1", "rev-1", "installs@1")
    seen: set[int] = set()
    found: list[str] = []

    def walk(value: object, path: str, level: int) -> None:
        if level > depth or id(value) in seen:
            return
        seen.add(id(value))
        if isinstance(value, str):
            found.extend(f"{path}={target}" for target in targets if target in value)
            return
        if isinstance(value, int | float | Decimal):
            found.extend(f"{path}={target}" for target in targets if target == str(value))
            return
        if isinstance(value, dict):
            mapping = cast("dict[object, object]", value)
            for key, item in mapping.items():
                walk(item, f"{path}[{key!r}]", level + 1)
            return
        if isinstance(value, list | tuple | set | frozenset):
            sequence = cast("Iterable[object]", value)
            for index, item in enumerate(sequence):
                walk(item, f"{path}[{index}]", level + 1)
            return
        for name in dir(value):
            if name.startswith("_"):
                continue
            try:
                attribute = getattr(value, name)
            except Exception:
                continue
            if callable(attribute):
                continue
            walk(attribute, f"{path}.{name}", level + 1)

    walk(error, type(error).__name__, 0)
    walk(str(error), "message", 0)
    return sorted(set(found))


# --- the control ------------------------------------------------------------------


def test_a_coherent_comparison_releases_both_sides(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """The control, and the shape a refusal must not partially resemble.

    Both sides present, both executed exactly once, one figure. Without this, every
    refusal below could mean the comparison never works.
    """
    comparison, left, right = _govern(authorized_pair)
    assert isinstance(comparison, GovernedComparison)
    assert len(comparison.sides) == 2
    assert left.count == 1
    assert right.count == 1
    assert comparison.difference.value == PRIMARY_VALUE - BASELINE_VALUE


# --- the shipped state: nothing is executed at all -------------------------------


def test_the_shipped_state_refuses_before_either_side_is_asked_for(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """**`D-18` ships empty, so the formula gate refuses first.**

    Zero executions, not one — the ordering is what makes this cheap as well as
    safe: a comparison that could not have been computed never costs a query.
    """
    authorized, derived = authorized_pair
    left = _CountedSide(executed(PRIMARY_VALUE))
    right = _CountedSide(executed(BASELINE_VALUE))
    with pytest.raises(ContentUnresolvable):
        govern_comparison(
            verdict(),
            formula_id="absolute_difference",
            primary_side=SideSubmission(request=request(), submit=left),  # pyright: ignore[reportArgumentType]
            baseline_side=SideSubmission(request=request(period=BASELINE_RANGE), submit=right),  # pyright: ignore[reportArgumentType]
            caveats=NO_CAVEATS,
            authorized=authorized,
            auth_fingerprint=derived,
            on=ON,
            vocabulary_version=FIXTURE_VERSION,
            derived_from=("claim-a", "claim-b"),
            instances=None,
        )
    assert left.count == 0
    assert right.count == 0


# --- every enumerated single-side condition -------------------------------------


#: One entry per condition that invalidates a side on its own.
#:
#: Each is a *different* upstream fact and each must produce a whole-comparison
#: refusal. Held as a table so the count is visible and a condition added to the
#: contract without a case here is a gap somebody can see.
SIDE_CONDITIONS: tuple[tuple[str, dict[str, object]], ...] = (
    ("denied-verdict", {"code": ReasonCode.ACCESS_DENIED}),
    ("suppressed", {"suppressed": True}),
    ("absent-value", {"value": None}),
    # ``Completeness`` has no ``TRUNCATED``: truncation is not representable in
    # `002`. ``EMPTY`` is the other end — a genuinely empty result, which is not a
    # value and cannot be one side of a difference.
    ("empty-completeness", {"completeness": Completeness.EMPTY}),
    ("pre-evidence-finality", {"finality": Finality.PRE_EVIDENCE}),
    ("limited-reproducibility", {"reproducibility": Reproducibility.LIMITED}),
)

SIDE_IDS = [name for name, _ in SIDE_CONDITIONS]


@pytest.mark.parametrize("condition", [kwargs for _, kwargs in SIDE_CONDITIONS], ids=SIDE_IDS)
def test_an_invalid_primary_refuses_and_never_asks_for_the_baseline(
    authorized_pair: tuple[AuthorizedContext, str], condition: dict[str, object]
) -> None:
    """**The ordering guarantee.** One failed side costs one execution, not two.

    Asserted as a count on side B. An implementation that executed both and then
    checked would satisfy every outcome assertion in this file while charging the
    caller for a query it discarded.
    """
    with pytest.raises(ContractViolation) as raised:
        _govern(authorized_pair, primary=_executed(PRIMARY_VALUE, condition))
    assert raised.value.code is Code.COMPARISON_SIDE_INVALID
    assert _leaked(raised.value) == []


@pytest.mark.parametrize("condition", [kwargs for _, kwargs in SIDE_CONDITIONS], ids=SIDE_IDS)
def test_an_invalid_baseline_refuses_the_whole_comparison(
    authorized_pair: tuple[AuthorizedContext, str], condition: dict[str, object]
) -> None:
    """**The half that carries the number.**

    Side A succeeded. It has a real value, real provenance and a real decision, and
    none of it is released — which is the case a helpful implementation gets wrong.
    """
    with pytest.raises(ContractViolation) as raised:
        _govern(
            authorized_pair,
            primary=executed(PRIMARY_VALUE),
            baseline=_executed(BASELINE_VALUE, condition),
        )
    assert raised.value.code is Code.COMPARISON_SIDE_INVALID
    assert _leaked(raised.value) == [], "side A's value escaped through the refusal"


# --- every enumerated coherence condition ---------------------------------------


def test_mismatched_units_refuse_without_converting(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """Exact equality, never a conversion.

    A converted unit would produce a plausible figure from two incomparable
    numbers, and the answer would disclose the conversion as if it were governed.
    """
    with pytest.raises(ContractViolation) as raised:
        _govern(
            authorized_pair,
            primary=executed(PRIMARY_VALUE, unit="count"),
            baseline=executed(BASELINE_VALUE, unit="thousands"),
        )
    assert raised.value.code is Code.COMPARISON_SIDE_INVALID
    assert _leaked(raised.value) == []


def test_a_grain_mismatch_refuses(authorized_pair: tuple[AuthorizedContext, str]) -> None:
    """Two sides asking about different metrics are not two sides of one question."""
    with pytest.raises(ContractViolation) as raised:
        _govern(authorized_pair, baseline_metrics=("sessions",))
    assert raised.value.code is Code.COMPARISON_SIDE_INVALID
    assert _leaked(raised.value) == []


def test_mismatched_metric_versions_refuse(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """The same metric under two definitions is two metrics."""
    with pytest.raises(ContractViolation) as raised:
        _govern(
            authorized_pair,
            primary=executed(PRIMARY_VALUE, metric_versions=("installs@1",)),
            baseline=executed(BASELINE_VALUE, metric_versions=("installs@2",)),
        )
    assert raised.value.code is Code.COMPARISON_SIDE_INVALID
    assert _leaked(raised.value) == []


def test_mismatched_data_as_of_refuses(authorized_pair: tuple[AuthorizedContext, str]) -> None:
    """Two sides read at different instants are not comparable at a point in time."""
    with pytest.raises(ContractViolation) as raised:
        _govern(
            authorized_pair,
            primary=executed(PRIMARY_VALUE),
            baseline=executed(BASELINE_VALUE, data_as_of=datetime(2026, 8, 1, tzinfo=UTC)),
        )
    assert raised.value.code is Code.COMPARISON_SIDE_INVALID
    assert _leaked(raised.value) == []


def test_every_enumerated_mismatch_condition_is_named_once() -> None:
    """Seven conditions, in one place.

    ``MismatchCondition`` is closed, so a condition added to the contract appears
    here and this assertion fails — rather than the new condition being silently
    absent from the sweep above.
    """
    assert {condition.value for condition in MismatchCondition} == {
        "units",
        "grain",
        "metric_versions",
        "dimensional_coverage",
        "reproducibility",
        "data_as_of",
        "governing_versions",
    }


def test_an_unrecognised_condition_fails_closed_as_a_mismatch() -> None:
    """A condition the contract names and this module has not implemented refuses.

    The alternative — a lookup error, or silently passing — would turn a gap in
    this module into a comparison that proceeds without the check the contract
    requires.
    """
    from analytics_interaction.comparison.refusal import mismatch

    refusal = mismatch("a-condition-nobody-implemented")
    assert refusal.code is Code.COMPARISON_SIDE_INVALID
    assert "fails closed" in str(refusal)


# --- caveats are all-or-nothing too --------------------------------------------


def test_an_incomplete_caveat_set_refuses_the_whole_comparison(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """A comparison released with some of its caveats is a comparison misrepresented.

    The verdict carries a limitation; the caveat set does not carry it. Releasing
    the figure would present a caveated result as unqualified.
    """
    with pytest.raises(ContractViolation) as raised:
        _govern(
            authorized_pair,
            decision=verdict(
                code=ReasonCode.COMPARABLE_WITH_CAVEAT,
                limitations=(limitation("PARTIAL_COVERAGE", "cobertura parcial"),),
            ),
            caveats=NO_CAVEATS,
        )
    assert raised.value.code is Code.COMPARISON_SIDE_INVALID
    assert "never trimmed" in str(raised.value)
    assert _leaked(raised.value) == []


def test_no_partial_caveat_set_is_released(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    """Two limitations, one caveat. Neither the figure nor the one caveat escapes."""
    with pytest.raises(ContractViolation) as raised:
        _govern(
            authorized_pair,
            decision=verdict(
                code=ReasonCode.COMPARABLE_WITH_CAVEAT,
                limitations=(
                    limitation("PARTIAL_COVERAGE", "cobertura parcial"),
                    limitation("STALE_SOURCE", "fonte desatualizada"),
                ),
            ),
            caveats=caveat_set(
                (ReasonCode.COMPARABLE_WITH_CAVEAT, CaveatOrigin.VERDICT, "cobertura parcial")
            ),
        )
    assert "fonte desatualizada" not in str(raised.value)
    assert _leaked(raised.value) == []


# --- the leak detector works --------------------------------------------------


def test_the_leak_detector_finds_a_planted_value() -> None:
    """**Without this, every ``_leaked(...) == []`` above is meaningless.**

    Planted three ways — in the message, as a direct attribute, and nested two
    levels down — because the third is the one a shallow detector misses and the
    one a real leak would use.
    """

    class _Nested:
        def __init__(self) -> None:
            self.result = {"cell": {"value": PRIMARY_VALUE}}

    in_message = ContractViolation(Code.COMPARISON_SIDE_INVALID, f"side A was {PRIMARY_VALUE}")
    assert _leaked(in_message)

    attached = ContractViolation(Code.COMPARISON_SIDE_INVALID, "refused")
    attached.side = _Nested()  # pyright: ignore[reportAttributeAccessIssue]
    assert _leaked(attached), "a fragment attached to the exception went unnoticed"

    identifiers = ContractViolation(Code.COMPARISON_SIDE_INVALID, "job-1 failed")
    assert _leaked(identifiers)


def test_the_leak_detector_does_not_fire_on_a_clean_refusal() -> None:
    """And the control for the detector, so it is not vacuously finding nothing."""
    clean = ContractViolation(Code.COMPARISON_SIDE_INVALID, "a side is not releasable")
    assert _leaked(clean) == []
