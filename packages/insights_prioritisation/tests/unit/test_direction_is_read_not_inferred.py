"""Direction is read from a declaration, never inferred from a sign — T008 (`FR-003`, `US1`).

**The two things this proves are the two ways the rule gets broken.**

The first is treating a RISE as bad because it is a rise. A 12% fall in a metric whose
`lower_is_better` is false and a 12% rise in one whose `lower_is_better` is true are the
**same kind of bad**, and nothing about either number says so — only the declaration does.

The second is defaulting. A metric that declares no direction must come back **not
prioritisable, naming what was missing**, and never as "assume higher is better".

## And today every real metric still takes the second path — for a NEW reason

It used to be that nothing declared direction anywhere. `D-1303` changed that on
2026-09-04: `MetricVersion` carries `lower_is_better` and twenty of the catalog's metrics
state it. The production catalog nevertheless answers `PRIORITY_DIRECTION_NOT_DECLARED`
for every metric, because the declaration sits on the version and this reader is handed
the top-level `Metric`.

**The claim rotted, and the node watching it did not notice.** Its docstring said the day
`001` grew the field it would fail; the field grew and it stayed green, because it asked
the object that never carries the answer. Both halves are now asserted separately, and the
second one is red the day the reader descends into the version.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from insights_prioritisation.contracts import PriorityReasonCode
from insights_prioritisation.read import read_direction

pytestmark = pytest.mark.unit

#: `tests/unit/` -> `tests/` -> package -> `packages/` -> repository.
REPO = Path(__file__).resolve().parents[4]


class _Declares:
    """A metric that declares its polarity, under one of the governed names."""

    def __init__(self, name: str, field: str, value: bool) -> None:
        self.name = name
        setattr(self, field, value)


class _Silent:
    """A metric that declares nothing. Not a metric with `None` — a metric with no field."""

    def __init__(self, name: str) -> None:
        self.name = name


def test_a_rise_and_a_fall_are_the_same_kind_of_bad_because_the_metric_says_so() -> None:
    """**The first defect, and it cannot be reached through this module at all.**

    `read_direction` takes no figure, no difference and no sign — so there is no input a
    caller could pass that would make a rise read as bad *because it rose*. The assertion
    is over what it DOES return: the metric's own polarity, opposite for the two, which is
    what makes the two movements comparable in the first place.
    """
    cancellations = read_direction(_Declares("cancellations", "lower_is_better", True))
    trials = read_direction(_Declares("new_trials", "lower_is_better", False))

    assert cancellations.is_declared and trials.is_declared
    assert cancellations.lower_is_better is True
    assert trials.lower_is_better is False
    assert cancellations.lower_is_better is not trials.lower_is_better, (
        "the two metrics carry opposite polarity; if they ever read the same, a rise and a "
        "fall would stop being distinguishable by the metric that owns them"
    )


def test_the_reader_is_given_no_number_to_infer_from() -> None:
    """The structural half: inference is unreachable because there is nothing to infer from.

    Asserted on the signature rather than on behaviour, because behaviour can be right today
    and a parameter added tomorrow is how it stops being.
    """
    import inspect

    parameters = list(inspect.signature(read_direction).parameters)
    assert parameters == ["metric"], (
        f"read_direction takes {parameters}; a figure, difference or sign reaching it is how "
        "direction stops being read and starts being inferred"
    )


def test_a_metric_declaring_nothing_is_reported_and_never_defaulted() -> None:
    """**The second defect: a default is a decision nobody made, wearing a value's clothes.**

    The absence names itself with a governed code, so it can be counted and refused rather
    than read as "unimportant" — which is what a defaulted direction would silently mean.
    """
    resolved = read_direction(_Silent("no_declaration"))

    assert not resolved.is_declared
    assert resolved.lower_is_better is None
    assert resolved.read_from is None
    assert resolved.absence is not None
    assert resolved.absence.reason is PriorityReasonCode.PRIORITY_DIRECTION_NOT_DECLARED


def test_the_declaration_says_where_it_was_read_from() -> None:
    """`FR-002`: an ordering must be reconstructable from its output.

    A polarity with no field name behind it is a value this module asserts rather than
    carries, and the difference is exactly the one `006` § 3 is about.
    """
    for field in ("lower_is_better", "direction", "polarity"):
        resolved = read_direction(_Declares("m", field, True))
        assert resolved.read_from == field, field


def test_the_top_level_metric_declares_no_direction_and_this_reader_sees_none() -> None:
    """**What this node measures is the TOP-LEVEL `Metric`, and saying so is the point.**

    It used to claim more than it measured. Its own docstring said *the day `001` grows the
    field, this node fails* — `001` grew the field on 2026-09-04 (`D-1303`) and this node
    stayed green, because `catalog.metrics` hands back `Metric` and the declaration lives one
    level down, in `MetricVersion`. A node that cannot see the thing it watches for is not a
    watch; it is a sentence that happens to pass.

    So it now states its own reach, and :func:`test_the_catalog_does_declare_a_direction_and_
    this_reader_cannot_reach_it` measures the half it never covered.
    """
    from semantic_catalog.loader.bundle import load_catalog

    catalog = load_catalog(REPO / "semantic")
    assert catalog.metrics, "the catalog holds no metric; this node would assert nothing"

    declared = [
        name
        for name, metric in sorted(catalog.metrics.items())
        if read_direction(metric).is_declared
    ]
    assert not declared, (
        f"these top-level metrics now declare a direction: {declared}. The field moved up "
        "from the version -- re-derive this node to assert the reading"
    )


def test_the_catalog_does_declare_a_direction_and_this_reader_cannot_reach_it() -> None:
    """**The measured gap, standing where a vacuous node used to stand.**

    The catalogue DOES declare direction today, on the metric's VERSION, and this feature's
    reader does a flat `getattr` on whatever it is handed — so it reaches none of it. That is
    a real gap, and it is written down as a measurement rather than left to be discovered by
    whoever next trusts the node above.

    **This node is not the fix.** Making the reader descend into `.versions` decides which
    version answers when there are several, and that decision belongs to a slice of `006`
    with its own nodes, not to a sentence in a test file.
    """
    from semantic_catalog.loader.bundle import load_catalog

    catalog = load_catalog(REPO / "semantic")
    on_the_version = sorted(
        name
        for name, metric in catalog.metrics.items()
        if any(getattr(version, "lower_is_better", None) is not None for version in metric.versions)
    )
    assert on_the_version, (
        "no version declares a direction; if `D-1303` was reverted, this pair of nodes has "
        "to be re-derived together"
    )

    reachable = [
        name for name in on_the_version if read_direction(catalog.metrics[name]).is_declared
    ]
    assert not reachable, (
        f"the reader now reaches the version's declaration for {reachable}; the gap this node "
        "measures has closed, and the node above has to be re-derived with it"
    )
