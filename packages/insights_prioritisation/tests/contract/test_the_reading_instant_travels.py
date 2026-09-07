"""Every figure carries the instant it was read — T022 (`FR-012`, `SC-009`).

The source is rebuilt at 06:00 UTC and the current day does not exist in it. So two
figures read at different moments are two answers about two different states of the
warehouse, and putting them in one order **as if they were simultaneous** is a
comparison nobody can check.

## Where the guarantee lives, and it is not a check

**No emitted container declares an instant for a group of findings.** `Ordering` has no
datetime field at all; `PrioritisedFinding` and `NotPrioritisable` each carry their own.
That is what makes a difference of instants *visible*: there is nowhere in the output to
write "these were read together", so a reader who wants to know when a figure was read
reads it off the figure.

A run-level list of instants was NOT added for the same reason. A second place to state
when things were read is a second place to disagree with the findings, and the
disagreement would be invisible — `spec.md`'s *"the reading instants involved"* is
satisfied by the instants that are actually on the figures.

## And every instant is aware

A naive instant is refused on both finding types and on the run. Two naive instants from
different zones compare as though they were the same clock, which is the same defect one
layer down.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from anomaly_investigation.contracts import AggregationClass
from pydantic import ValidationError

from insights_prioritisation.contracts import (
    ComponentAbsence,
    NotPrioritisable,
    Ordering,
    PrioritisationRun,
    PrioritisedFinding,
    PriorityComponent,
    PriorityReasonCode,
    RunOutcome,
)
from insights_prioritisation.order import one_ordering_per_class

pytestmark = pytest.mark.contract

CONTRACTS = Path(__file__).resolve().parents[2] / "src" / "insights_prioritisation" / "contracts"

YESTERDAY = datetime(2026, 8, 25, 6, 0, tzinfo=UTC)
TODAY = datetime(2026, 8, 26, 6, 0, tzinfo=UTC)


def _finding(identifier: str, instant: datetime) -> PrioritisedFinding:
    return PrioritisedFinding(
        finding_id=identifier,
        components=(
            PriorityComponent(
                name="magnitude", read_from="candidate_finding", value=Decimal("0.5")
            ),
        ),
        reading_instant=instant,
    )


def _unplaced(identifier: str, instant: datetime) -> NotPrioritisable:
    return NotPrioritisable(
        finding_id=identifier,
        components=(
            PriorityComponent(
                name="reach",
                read_from="investigation",
                absence=ComponentAbsence(reason=PriorityReasonCode.PRIORITY_COMPONENT_UNAVAILABLE),
            ),
        ),
        reading_instant=instant,
    )


def test_every_figure_in_an_emitted_output_carries_its_instant() -> None:
    """`SC-009` over each figure, placed and unplaced, through the ordering path."""
    orderings = one_ordering_per_class(
        {
            AggregationClass.COUNT: [(_finding("a", TODAY),)],
            AggregationClass.SNAPSHOT: [(_finding("c", YESTERDAY),)],
        },
        not_prioritisable=[_unplaced("d", YESTERDAY)],
    )
    carried = {
        finding.finding_id: finding.reading_instant
        for ordering in orderings
        for group in ordering.positions
        for finding in group
    } | {
        unplaced.finding_id: unplaced.reading_instant
        for ordering in orderings
        for unplaced in ordering.not_prioritisable
    }
    assert carried == {"a": TODAY, "c": YESTERDAY, "d": YESTERDAY}


def test_two_instants_in_one_ordering_stay_two_instants() -> None:
    """**The difference survives the ordering**, which is what makes it visible.

    Both findings are in one ordering, and the output still says they were read a day
    apart. Nothing collapsed them onto one moment, because there is no field to collapse
    them into.
    """
    ordering = one_ordering_per_class(
        {AggregationClass.COUNT: [(_finding("a", TODAY),), (_finding("b", YESTERDAY),)]}
    )[0]
    instants = {f.reading_instant for group in ordering.positions for f in group}
    assert instants == {TODAY, YESTERDAY}
    assert max(instants) - min(instants) == timedelta(days=1)


def test_no_emitted_container_declares_an_instant_for_a_group() -> None:
    """**The structural half, and the load-bearing one.**

    `Ordering` declares no datetime field. A `read_at` on an ordering would be a claim
    that its members were read together, made by the container over findings that each
    carry their own answer — and a reader trusting the container would compare figures
    of different instants as simultaneous without anything in the output saying so.
    """
    tree = ast.parse((CONTRACTS / "ordering.py").read_text(encoding="utf-8"))
    dated = [
        f"{klass.name}.{node.target.id}"
        for klass in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
        for node in klass.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and "datetime" in ast.unparse(node.annotation)
    ]
    assert not dated, (
        f"an emitted container declares an instant of its own: {dated}. That states the "
        "members were read together, over findings that each carry their own instant"
    )
    runtime_dated = [
        name for name, field in Ordering.model_fields.items() if "datetime" in str(field.annotation)
    ]
    assert not runtime_dated, (
        f"the resolved model carries an instant the source scan missed: {runtime_dated}"
    )


def test_the_run_s_instant_does_not_overwrite_the_figures() -> None:
    """`PrioritisationRun.read_at` dates the RUN, and the figures keep their own.

    A run read today can carry a figure read yesterday — that is the ordinary case, not
    an anomaly, because the source's newest day is the day before. The output says both.
    """
    run = PrioritisationRun(
        outcome=RunOutcome.COMPLETED,
        orderings=one_ordering_per_class({AggregationClass.COUNT: [(_finding("a", YESTERDAY),)]}),
        read_at=TODAY,
    )
    assert run.read_at == TODAY
    figure = run.orderings[0].positions[0][0]
    assert figure.reading_instant == YESTERDAY, "the run's instant replaced the figure's"


def test_a_naive_instant_is_refused_everywhere_it_could_enter() -> None:
    """Three doors, and a naive instant is refused at each.

    Two naive instants from different zones compare as though they were one clock, which
    turns "read a day apart" into "read together" with nothing visible in the output.
    """
    naive = datetime(2026, 8, 26, 6, 0)  # a naive instant on purpose: it is the subject

    with pytest.raises(ValidationError):
        _finding("a", naive)
    with pytest.raises(ValidationError):
        _unplaced("d", naive)
    with pytest.raises(ValidationError):
        PrioritisationRun(outcome=RunOutcome.COMPLETED, read_at=naive)


def test_the_container_scan_would_catch_an_instant_added_later() -> None:
    """**Proof the structural node bites**, on the field it exists to forbid."""
    declared = "class Ordering:\n    positions: tuple\n    read_at: datetime\n"
    tree = ast.parse(declared)
    dated = [
        node.target.id
        for klass in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
        for node in klass.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and "datetime" in ast.unparse(node.annotation)
    ]
    assert dated == ["read_at"], "the scan would not notice an instant added to a container"
