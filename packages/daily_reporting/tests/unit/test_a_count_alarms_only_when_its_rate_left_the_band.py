"""`SC-1303` — rate before count. Volume up with a stable rate is growth — `T1333`.

## The defect this node exists to catch, measured in production

Before this file existed, `apps/telegram-bot/deliver_daily_report.py` decided the alert one
KPI at a time: `evaluate` (`daily_reporting/alert/rule.py`) takes ONE KPI's own history and
answers whether that KPI moved outside its own noise, and the caller appended the answer to
`crossed` with no second question asked. Nothing on that path could see another KPI, so
nothing on it could apply `SC-1303`.

The 08:00 alert of 2026-09-05 carried, verbatim:

    New trials: 688 · 579 · +18,83 % · +15,63 % vs D-7 (595) (18,61 % · 90 d)

A COUNT alarming on its own, with no rate beside it. That is the case `SC-1303` says must
not alarm, and it went out.

## What is asserted, and what is deliberately NOT

The node drives :func:`apply_rate_before_count`, the function the run really calls. It does
not stub the class of a KPI: the class is the VIEW's own word — `COUNT`, `RATIO`, `SNAPSHOT`
out of `daily_reporting/view/reading.py` — so a count is a count because the source says so
and never because this repository matched a name.

**No pairing is invented here.** Which rate governs which count is his to declare; the node
hands the map in as an argument, exactly as the run does, and asserts what the function does
with a map — not what any particular map contains.
"""

from __future__ import annotations

import pytest

from daily_reporting.alert.rate_before_count import (
    RateBeforeCountGovernanceError,
    apply_rate_before_count,
    governing_rates_from_document,
)
from daily_reporting.view.reading import COUNT, RATIO, SNAPSHOT

pytestmark = pytest.mark.unit

#: One count, the rate that governs it, and the spelling both take from the view. The names
#: are transcribed from `report_governance/daily_scope.yaml`; no name is authored here, and
#: the PAIR between them is an argument this node supplies, never a declaration it makes.
COUNT_KPI = "New trials"
RATE_KPI = "Trial conversion (%)"

CLASSES = {COUNT_KPI: COUNT, RATE_KPI: RATIO}
PAIRS = {COUNT_KPI: RATE_KPI}


def test_a_count_that_crossed_with_its_rate_inside_the_band_does_not_alarm() -> None:
    """Growth does not alarm — the sentence of `SC-1303`, driven end to end.

    The rate was MEASURED and stayed inside its band, so the count's move is volume, and
    volume with a stable rate is the business working.
    """
    decision = apply_rate_before_count(
        [COUNT_KPI],
        classes=CLASSES,
        governing_rate=PAIRS,
        bands_measured={COUNT_KPI, RATE_KPI},
    )

    assert COUNT_KPI not in decision.alerted
    assert decision.withheld == (COUNT_KPI,)
    assert decision.unresolved == ()


def test_a_count_alarms_when_its_rate_left_the_band_too() -> None:
    """The converse, and it is half the criterion: the rule must still let an alert out."""
    decision = apply_rate_before_count(
        [COUNT_KPI, RATE_KPI],
        classes=CLASSES,
        governing_rate=PAIRS,
        bands_measured={COUNT_KPI, RATE_KPI},
    )

    assert decision.alerted == (COUNT_KPI, RATE_KPI)
    assert decision.withheld == ()
    assert decision.unresolved == ()


def test_a_count_whose_governing_rate_was_never_measured_alarms_and_is_named() -> None:
    """Fail-closed on the ANSWER, not on the alert — the count is kept and it is NAMED.

    The rate is declared but its band was never computed (too short a series, no movement,
    a refusal caught upstream). Nothing measured says the rate stayed put, so nothing may
    withhold on that ground. The count therefore does not vanish; it also does not pass
    unremarked, because a suppression rule that cannot say whether it ran is not a rule.
    """
    decision = apply_rate_before_count(
        [COUNT_KPI],
        classes=CLASSES,
        governing_rate=PAIRS,
        bands_measured={COUNT_KPI},
    )

    assert decision.alerted == (COUNT_KPI,)
    assert decision.unresolved == (COUNT_KPI,)
    assert decision.withheld == ()


def test_a_count_no_declaration_pairs_is_named_rather_than_silently_judged() -> None:
    """An undeclared pairing is an ABSENCE, and absence is said — never answered for.

    This is the state the repository is actually in on 2026-09-06: no file anywhere pairs a
    count with its rate. The function does not guess one from a name, and it does not
    quietly behave as though every count were governed.
    """
    decision = apply_rate_before_count(
        [COUNT_KPI],
        classes=CLASSES,
        governing_rate={},
        bands_measured={COUNT_KPI, RATE_KPI},
    )

    assert decision.alerted == (COUNT_KPI,)
    assert decision.unresolved == (COUNT_KPI,)
    assert decision.withheld == ()


def test_a_rate_is_never_withheld_by_this_rule() -> None:
    """`SC-1303` governs a COUNT deviation. A rate is the thing it defers to."""
    decision = apply_rate_before_count(
        [RATE_KPI],
        classes=CLASSES,
        governing_rate=PAIRS,
        bands_measured={RATE_KPI},
    )

    assert decision.alerted == (RATE_KPI,)
    assert decision.withheld == ()
    assert decision.unresolved == ()


def test_a_snapshot_is_a_level_and_this_rule_does_not_reach_it() -> None:
    """A `SNAPSHOT` is not a count of anything that happened — see the module docstring.

    `MAU`, `MRR (US$)` and `Paid subscribers` are the size of the base on the last day the
    rows cover (`daily_reporting/view/reading.py`, `SC-1306`). There is no denominator that
    grew alongside them, so *volume up with a stable rate* is not a sentence about them.
    """
    level = "MAU"
    decision = apply_rate_before_count(
        [level],
        classes={level: SNAPSHOT},
        governing_rate={},
        bands_measured={level},
    )

    assert decision.alerted == (level,)
    assert decision.withheld == ()
    assert decision.unresolved == ()


def test_a_class_the_view_did_not_state_is_unresolved_rather_than_waved_through() -> None:
    """Not knowing whether a KPI is a count is not the same as knowing it is not one."""
    decision = apply_rate_before_count(
        ["Whatever"],
        classes={},
        governing_rate={},
        bands_measured={"Whatever"},
    )

    assert decision.alerted == ("Whatever",)
    assert decision.unresolved == ("Whatever",)
    assert decision.withheld == ()


def test_the_order_the_run_handed_in_is_the_order_that_comes_back() -> None:
    """The alert's block is built from this list, and a reordering would reorder the message."""
    decision = apply_rate_before_count(
        [RATE_KPI, COUNT_KPI],
        classes=CLASSES,
        governing_rate=PAIRS,
        bands_measured={COUNT_KPI, RATE_KPI},
    )

    assert decision.alerted == (RATE_KPI, COUNT_KPI)


def test_an_empty_declaration_is_read_as_a_statement_and_not_as_an_absence() -> None:
    """`pairs: {}` is him saying *not yet*, and it is the file's state on 2026-09-06."""
    assert governing_rates_from_document({"pairs": {}}) == {}
    assert governing_rates_from_document({"pairs": {COUNT_KPI: RATE_KPI}}) == PAIRS


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"pairs": None},
        {"pairs": [COUNT_KPI, RATE_KPI]},
        {"pairs": {COUNT_KPI: ""}},
        {"pairs": {COUNT_KPI: 7}},
        "pairs",
    ],
    ids=["no key", "typed but empty", "a list", "an empty rate", "not a name", "not a mapping"],
)
def test_a_pairing_that_cannot_be_read_refuses_rather_than_defaulting(document: object) -> None:
    """A suppression rule nobody can audit is worse than no suppression rule — `S-41`.

    `pairs:` written alone parses to ``None``, which is the typo `pairs: {}` must never be
    mistaken for: one is a decision, the other is a finger slip, and they would suppress and
    not-suppress the same KPIs while looking the same in the file.
    """
    with pytest.raises(RateBeforeCountGovernanceError):
        governing_rates_from_document(document)
