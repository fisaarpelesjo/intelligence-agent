"""Every refusal path of `figures_port` raised `AttributeError` instead of refusing.

**Found by the strict type gate on 2026-08-27, in production code, after 362 nodes had been
green for days.** `figures_port` read `violation.reason_code` in five places. The attribute
does not exist: `ContractViolation` carries `code`, and `ExecutionRefused` carries both
`code` and `violation.code`. (There are TWO classes with that name, one per package, and this
file uses `analytics_query`'s -- the one `ExecutionRefused` actually declares.)

Measured at runtime before the fix:

    'ContractViolation' object has no attribute 'reason_code'

So every one of those branches — the branches that exist SO THAT a governed refusal reaches
the caller intact — would have raised an `AttributeError` out of the port instead. The
refusal machinery was the part that was broken.

## Why nothing caught it

Nothing drove them. `resolve_movement` had integration coverage of the paths where
everything works, and **not one node made an upstream layer refuse**. A branch that is never
executed is a branch whose type is never checked either, at runtime — which is exactly why a
type checker is a different instrument from a suite, and why running only one of them let
this sit.

## What this file drives, and what it does NOT -- corrected 2026-08-27

**An earlier version of this docstring said "every refusal path", and that was false.** It
was measured, not argued: reverting the four `upstream_code=violation.code.value` sites to
the broken attribute left this file at **3 passed** and the whole `005` suite at **366
passed**, both green. The nodes here reached only the two `_execute` branches, where no
attribute is read at all. **Prose asserting more coverage than the nodes have is the same
defect class as a measurement written without its scope.**

`resolve_movement` has five sites that read a code off a caught exception, plus the two
`_execute` branches that read one off a refusal object. **Two of the five are driven here**,
each by making a real upstream layer refuse:

* **the formula is not governed** -- an id `D-18` does not declare;
* **the baseline is zero** -- for a dividing formula, where the governed rule refuses.

**Three are NOT reachable through this port, and each reason is measured rather than
asserted:**

* the `ContentUnresolvable` branch fires when no single complete formula set is in force.
  `comparison-formulas.yaml` has held one since 2026-08-26, and `resolve_movement` passes no
  fixture instances -- deliberately, because the fixture-containment scan asserts that no
  `src/` module supplies one. So it cannot be entered from here without reaching around a
  boundary this repository refuses to reach around;
* the `to_exact` branch refuses a `float`, and **two things stand between a `float` and
  it**: `ResultCell.value` is DECLARED `Decimal | int | None`, so a `float` is a type error
  at the boundary; and the model **coerces one to `Decimal` on construction** anyway --
  measured, `1.5` comes back as `Decimal('1.5')`. A node below asserts the coercion, so the
  day it stops being true is a red node rather than a silent gap;
* the `derive_figure` branch is defence in depth: it refuses an unknown formula id, and the
  id reaching it has already been validated by `resolve_formula` one step earlier.

**What holds those three is `pyright`, in the push gate, on every push since 2026-08-27** --
and that is a real guard rather than a consolation: reverting either one to `.reason_code`
is 16 strict errors and a blocked push. It is named here so nobody reads this file as
covering them.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, cast

import pytest
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode
from analytics_query.contracts._base import ContractViolation
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.contracts.request import AnalyticsQuery, DateRange
from analytics_query.contracts.result import (
    AnalyticsResult,
    Completeness,
    ResultCell,
    ResultColumn,
    ResultRow,
)
from analytics_query.contracts.result_provenance import (
    CostProvenance,
    ResultProvenance,
    SourceUpdate,
)
from analytics_query.execute import ExecutionRefused

from anomaly_investigation.contracts import AnomalyReasonCode
from anomaly_investigation.ports.figures_port import MovementResolution, resolve_movement

if TYPE_CHECKING:  # pragma: no cover - imported for the type only
    from analytics_query.execute import ExecutedAnswer

pytestmark = pytest.mark.integration

METRIC = "new_trials"
RULE_ID = "r-refusal-travels"
FORMULA = "percentage_change"
BASIS = "the governed window this rule was evaluated over"

PRIMARY_RANGE = DateRange(start=date(2026, 8, 11), end=date(2026, 8, 20))
BASELINE_RANGE = DateRange(start=date(2026, 8, 1), end=date(2026, 8, 10))


#: One provenance, shared by both doubles: `SideFigure` requires one, and a double that
#: skipped it would test this file's shortcut instead of the port's contract.
_PROVENANCE = ResultProvenance(
    contributing_sources=("subscription_daily",),
    resolved_metric_versions=("new_trials@1",),
    data_revisions=(),
    data_as_of=datetime(2026, 8, 26, 6, 0, tzinfo=UTC),
    source_updates=(
        SourceUpdate(
            source_id="subscription_daily",
            last_updated_at=datetime(2026, 8, 26, 6, 0, tzinfo=UTC),
        ),
    ),
    dimensional_coverage=(),
    limitations=("the figure was supplied by a node; 002 did not run",),
    cost=CostProvenance(dry_run_bytes=1, actual_bytes=1, maximum_bytes_billed=2),
    execution_identifiers=("node",),
    policy_version="not-run",
    catalog_release_id="not-run",
)


def _refusing_executor(request: AnalyticsQuery) -> ExecutedAnswer:
    """An upstream layer that refuses, the way `002` refuses: with a governed code."""
    raise ExecutionRefused(
        ContractViolation(AnalyticsReasonCode.REQUEST_MALFORMED, "the demonstration refusal"),
        stage="execute",
    )


def _resolve(execute: object) -> MovementResolution:
    """One call through the port, with the executor supplied by the caller."""
    return resolve_movement(
        RULE_ID,
        formula_id=FORMULA,
        primary_request=AnalyticsQuery(metrics=(METRIC,), date_range=PRIMARY_RANGE),
        baseline_request=AnalyticsQuery(metrics=(METRIC,), date_range=BASELINE_RANGE),
        execute=execute,  # type: ignore[arg-type] - the double is the port's shape, not 002's
        basis=BASIS,
        on=date(2026, 8, 26),
    )


def test_an_upstream_execution_refusal_comes_back_as_a_refusal() -> None:
    """**The site that was broken, driven.**

    Before the fix this raised `AttributeError: 'ContractViolation' object has no attribute
    'reason_code'` — out of the port, past the caller, with no governed code anywhere in it.
    """
    resolution = _resolve(_refusing_executor)

    assert resolution.derived is False, "a refused execution must not derive a movement"
    assert resolution.reason_code is AnomalyReasonCode.ANOMALY_FIGURE_UNAVAILABLE
    assert resolution.upstream_code == AnalyticsReasonCode.REQUEST_MALFORMED.value, (
        "the upstream word did not travel; a refusal that loses the code it refused for is "
        "a refusal nobody can act on"
    )


def test_the_refusal_carries_a_governed_word_and_never_a_python_name() -> None:
    """**The shape of the failure this file was written for.**

    `AttributeError` names an attribute of a Python object. A governed refusal names a
    decision. Asserting the code is a member of a governed enum is what separates the two,
    and it would have failed on the old code by never getting here at all.
    """
    resolution = _resolve(_refusing_executor)
    assert resolution.upstream_code is not None
    assert resolution.upstream_code in {code.value for code in AnalyticsReasonCode}, (
        f"{resolution.upstream_code!r} is not a governed analytics code"
    )


def _answer(value: Decimal) -> ExecutedAnswer:
    """One figure in the shape `002` produces, carrying the value the caller asked for."""

    class _Executed:
        result = AnalyticsResult(
            columns=(ResultColumn(identifier=METRIC, unit="users", is_metric=True),),
            rows=(ResultRow(labels=(), cells=(ResultCell(value=value),)),),
            completeness=Completeness.COMPLETE,
        )
        # A real provenance rather than `None`: `SideFigure` requires one, and a double that
        # skipped it would be testing this file's shortcut instead of the port's contract.
        provenance = _PROVENANCE
        decision = None
        disposition = None

    return _Executed()  # type: ignore[return-value] - the double is the port's shape


def test_the_baseline_side_refuses_on_its_own_word() -> None:
    """**The second execute call has its own branch, and it was broken the same way.**

    Driven separately because the two sites are separate code: a fix applied to one and not
    the other would leave this red, which is the whole reason they are not one node.
    """

    def _primary_answers_baseline_refuses(request: AnalyticsQuery) -> ExecutedAnswer:
        if request.date_range.start == PRIMARY_RANGE.start:
            return _answer(Decimal("100"))
        raise ExecutionRefused(
            ContractViolation(AnalyticsReasonCode.REQUEST_MALFORMED, "the baseline refusal"),
            stage="execute",
        )

    resolution = _resolve(_primary_answers_baseline_refuses)
    assert resolution.derived is False
    assert resolution.reason_code is AnomalyReasonCode.ANOMALY_FIGURE_UNAVAILABLE
    assert resolution.upstream_code == AnalyticsReasonCode.REQUEST_MALFORMED.value
    assert resolution.primary is not None, (
        "the side that ANSWERED was dropped along with the side that refused; the caller "
        "loses evidence it already paid a query for"
    )


def _answering_executor(value: Decimal | int) -> object:
    """An upstream layer that ANSWERS, carrying whatever the caller wants in the cell.

    Both sides answer the same figure. That is enough for every node below: what is under
    test is which refusal a later step raises, not the arithmetic between two windows.
    """

    def execute(request: AnalyticsQuery) -> ExecutedAnswer:
        return _answer_of(value)

    return execute


def _answer_of(value: Decimal | int) -> ExecutedAnswer:
    """One figure in the shape `002` produces, carrying a value chosen by the caller.

    The parameter is typed the way `ResultCell` declares its own: `Decimal | int`. That is
    the second reason the `to_exact` site cannot be reached from here -- see the node below.
    """

    class _Executed:
        result = AnalyticsResult(
            columns=(ResultColumn(identifier=METRIC, unit="users", is_metric=True),),
            rows=(ResultRow(labels=(), cells=(ResultCell(value=value),)),),
            completeness=Completeness.COMPLETE,
        )
        provenance = _PROVENANCE
        decision = None
        disposition = None

    return cast("ExecutedAnswer", _Executed())


def test_a_formula_the_catalog_does_not_declare_refuses_with_its_word() -> None:
    """**Site one of the three drivable, and it was one of the four that were broken.**

    `resolve_formula` raises before a single query is submitted -- there is no reason to
    read a warehouse for a comparison that cannot be made -- so this node needs no executor
    that answers.
    """
    resolution = resolve_movement(
        RULE_ID,
        formula_id="a_formula_nobody_governed",
        primary_request=AnalyticsQuery(metrics=(METRIC,), date_range=PRIMARY_RANGE),
        baseline_request=AnalyticsQuery(metrics=(METRIC,), date_range=BASELINE_RANGE),
        execute=_refusing_executor,
        basis=BASIS,
        on=date(2026, 8, 26),
    )
    assert resolution.derived is False
    assert resolution.reason_code is AnomalyReasonCode.ANOMALY_BASELINE_NOT_USABLE
    assert resolution.upstream_code == InterpretationReasonCode.CALCULATION_NOT_SUPPORTED.value, (
        "the formula refusal did not carry the interpretation layer's own word"
    )


def test_the_cell_normalises_before_the_lift_can_refuse() -> None:
    """**Why the `to_exact` site is NOT driven here, measured instead of assumed.**

    A first draft of this file drove it by putting a `float` in the cell, on the ground that
    `ResultCell` accepts one. It does accept one -- and it **coerces it to `Decimal` on
    construction**, measured: `1.5` comes back as `Decimal('1.5')`, `True` as `1`. So a
    `float` never reaches `to_exact` through this port, and the node that claimed to drive
    that site derived a movement instead of refusing.

    That is recorded rather than deleted, because it is the same mistake this file exists to
    correct: **believing a branch is covered because it looks reachable.** The assertion here
    is the reason the branch cannot be reached from here, so a cell that stops normalising
    turns this red and the site becomes drivable again.
    """
    # The cast is deliberate and is the point of the node: `ResultCell.value` is DECLARED
    # `Decimal | int | None`, so a `float` is already a type error at the boundary -- and
    # this reaches past the declaration to measure what the model does at runtime with one.
    cell = ResultCell(value=cast("Decimal", 1.5))
    assert isinstance(cell.value, Decimal), (
        "the cell no longer normalises a float, so `to_exact` is now reachable through this "
        "port and its refusal must be driven by a node rather than held by the type gate"
    )


def test_a_zero_baseline_refuses_with_the_governed_rule_s_word() -> None:
    """**Site three**, and the one whose ORDER the port's docstring calls binding.

    The zero-baseline rule is applied BEFORE anything is derived. Reversed, the division has
    already happened and the only choices left are bad ones -- so this node also fails if
    somebody moves step three after step four.
    """
    resolution = _resolve(_answering_executor(0))
    assert resolution.derived is False
    assert resolution.reason_code is AnomalyReasonCode.ANOMALY_BASELINE_NOT_USABLE
    assert resolution.upstream_code == InterpretationReasonCode.CALCULATION_NOT_SUPPORTED.value


def test_the_unreachable_sites_are_named_and_not_claimed() -> None:
    """**The prose above must keep saying which instrument holds what this file cannot.**

    A module docstring that stopped naming the type checker would leave a reader believing
    these nodes cover every site, which is exactly the false claim this file was corrected
    for. It is checked rather than trusted, because that correction is one edit away from
    being lost.

    ## And the first version of this guard could not fail

    It read the WHOLE FILE with `Path(__file__).read_text()` and looked for a literal that
    **its own assertion writes**. Emptying every line of prose left one occurrence -- the
    assertion itself -- and the node stayed green: **7 passed** with the docstring gutted.
    That is the same shape named one file over in the same cycle, about `assert REBASES`
    over a tuple literal: a guard whose subject includes the guard cannot fail.

    So it reads `__doc__` instead. The module's docstring and this function's own are the
    prose being guarded, and **the assertion's literals live outside both** -- an assertion
    body is not part of any docstring. Emptying the prose now removes the only occurrences
    there are.
    """
    guarded = (__doc__, test_the_unreachable_sites_are_named_and_not_claimed.__doc__)
    prose = " ".join(part for part in guarded if part)
    assert "pyright" in prose, (
        "the prose no longer names the instrument that holds the sites these nodes cannot "
        "reach, so this file reads as covering every one of them"
    )
    assert "reachable through this port" in prose, (
        "the prose no longer says which sites are out of reach, so a reader cannot tell "
        "what is driven here from what is held elsewhere"
    )
