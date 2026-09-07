"""The labels and the grouping are READ, and a correct literal fails — `T805` to `T807`.

## The shape this file is built in, and why the predicate is shared

**A derivation is held only when a CORRECT literal copy of it fails NOW.** This
repository has paid for that three times in one week, each time in a slightly different
disguise: `007`'s recipient, `006`'s method reader, and `006`'s method *binding* one
cycle later, where the reader had been made drivable and the constant production
actually reads had not.

The reviewer left one recommendation when that last one closed: the proof node was
**reimplementing the predicate inline** while its docstring said *"fed to the same
test"* — two functions carrying the same reasoning written twice, which is the mismatch
between a claim and a mechanism that this whole loop is about. **It is applied here
rather than relearned.** :func:`answers_the_document_it_is_handed` is defined once, the
real derivation goes through it, and the literal stand-ins go through *the same
function*, so the second node measures the first instead of measuring a copy of it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

import pytest

from daily_reporting.contracts import ReportReasonCode, ReportRefusal
from daily_reporting.view.shape import (
    Section,
    ViewRow,
    every_kpi_in,
    kpi_label_of,
    sections_from,
)

pytestmark = pytest.mark.contract

#: A derivation under test: rows in, sections out.
Deriver = Callable[[Iterable[ViewRow]], tuple[Section, ...]]

#: Two documents that share no name at all, so any answer that is the same for both is
#: an answer that did not read either. **Neither resembles the real view**, on purpose:
#: a fixture shaped like the twenty would be twenty correct strings in the one place
#: people forgive.
ONE_DOCUMENT: tuple[ViewRow, ...] = (
    {"section_name": "alpha", "kpi_name": "a_one"},
    {"section_name": "alpha", "kpi_name": "a_two"},
    {"section_name": "beta", "kpi_name": "b_one"},
)
ANOTHER_DOCUMENT: tuple[ViewRow, ...] = (
    {"section_name": "gamma", "kpi_name": "g_one"},
    {"section_name": "delta", "kpi_name": "d_one"},
    {"section_name": "delta", "kpi_name": "d_two"},
)


def answers_the_document_it_is_handed(deriver: Deriver) -> bool:
    """**The one predicate**, used by the real derivation and by every stand-in.

    Handed two documents sharing no name, a reader answers two different things and a
    literal answers the same to both. Defined once so the node below measures the node
    above rather than a second copy of its reasoning.
    """
    first = deriver(ONE_DOCUMENT)
    second = deriver(ANOTHER_DOCUMENT)
    if first == second:
        return False
    return every_kpi_in(first) != every_kpi_in(second)


def test_the_derivation_answers_the_document_it_is_handed() -> None:
    """The real one reads. Handed another view, it reports another view."""
    assert answers_the_document_it_is_handed(sections_from), (
        "sections_from answers the same shape for two documents that share no name, so "
        "it is not reading the document it was given"
    )


def test_a_correct_literal_copy_would_fail_this() -> None:
    """**Proof the predicate bites**, over the two shapes a literal copy really takes.

    The first is a literal that is CORRECT for one document — the dangerous kind,
    because every assertion about that document passes. The second ignores its input
    outright. Both go through the same function the node above used.
    """

    def correct_for_one_document(_rows: Iterable[ViewRow]) -> tuple[Section, ...]:
        return (
            Section(name="alpha", kpis=("a_one", "a_two")),
            Section(name="beta", kpis=("b_one",)),
        )

    def empty_whatever_it_is_given(_rows: Iterable[ViewRow]) -> tuple[Section, ...]:
        return ()

    for stand_in in (correct_for_one_document, empty_whatever_it_is_given):
        assert not answers_the_document_it_is_handed(stand_in), (
            "the predicate accepts a literal that answers the same to both documents"
        )


def _names_in(rows: tuple[ViewRow, ...]) -> set[str]:
    """The KPI names in the rows, read **without the derivation under test**.

    This is the whole correction below: an expectation computed by the thing being
    measured agrees with it whatever it does.
    """
    return {str(row["kpi_name"]) for row in rows}


@pytest.mark.parametrize("document", [ONE_DOCUMENT, ANOTHER_DOCUMENT])
def test_every_kpi_the_rows_declare_reaches_the_report(document: tuple[ViewRow, ...]) -> None:
    """`SC-801`. **Compared against the rows, not against another call.**

    The first version of this node compared ``sections_from(rows)`` with
    ``sections_from(rows[:-1])`` and asserted the count differed by one — and the
    acceptance mutation walked straight through it: **dropping a KPI inside the
    derivation dropped one from both sides**, so the difference held and 76 nodes
    stayed green. That is the `G-1` shape, a check comparing a derivation to itself,
    and it was caught by running the mutation rather than by reading the node.

    Nothing here counts to twenty either: a node asserting *twenty* goes red the day
    the business gains a KPI, which is the opposite of what it is for.
    """
    carried = set(every_kpi_in(sections_from(document)))
    declared = _names_in(document)
    assert carried == declared, (
        f"the report drops {sorted(declared - carried)} and invents "
        f"{sorted(carried - declared)}; a KPI missing from a summary is a claim nobody made"
    )


def test_the_completeness_check_would_catch_a_dropped_kpi() -> None:
    """**Proof it bites**, through the same comparison the node above uses."""

    def drops_the_last_one(rows: Iterable[ViewRow]) -> tuple[Section, ...]:
        built = list(sections_from(rows))
        built[-1] = Section(name=built[-1].name, kpis=built[-1].kpis[:-1])
        return tuple(built)

    carried = set(every_kpi_in(drops_the_last_one(ONE_DOCUMENT)))
    assert carried != _names_in(ONE_DOCUMENT), "the comparison accepts a dropped KPI"


def test_a_row_that_cannot_name_itself_refuses_rather_than_borrowing_a_label() -> None:
    """A borrowed label is a label this repository authored — `FR-803`."""
    for broken in ({"section_name": "alpha"}, {"kpi_name": "a_one"}, {"kpi_name": "  "}):
        with pytest.raises(ReportRefusal) as refused:
            sections_from([broken])
        assert refused.value.code is ReportReasonCode.REPORT_KPI_NOT_DERIVABLE


def test_the_label_is_the_views_own_name_and_nothing_else() -> None:
    """No translation table, no prettifier, no fallback."""
    assert kpi_label_of({"kpi_name": "  Chargeback (qty)  "}) == "Chargeback (qty)"


def test_the_view_order_is_kept_rather_than_sorted() -> None:
    """Sorting would impose an order this feature chose over the source's — `FR-805`."""
    reversed_document = tuple(reversed(ONE_DOCUMENT))
    assert [s.name for s in sections_from(reversed_document)] == ["beta", "alpha"]
