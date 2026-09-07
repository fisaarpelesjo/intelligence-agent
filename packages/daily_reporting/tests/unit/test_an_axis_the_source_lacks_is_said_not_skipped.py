"""An axis he asked for that the source lacks is SAID under its indicator, not skipped — `T1323`.

## The shape this replaces

`breakdowns_of` keeps deny-by-default in both directions: an axis the contract does not allow, or
the report does not govern, produces no line at all (`FR-1304`). That is right for an axis nobody
asked for. It is the **silent total** for one he did: his contract names plan under Sales and
Trial conversion, the view carries no plan column (`T1322`, remeasured 2026-09-05), and a report
that simply shows the other two axes reads as if plan had been considered and found empty.

`FR-1316` asks for the other behaviour — *the breakdown says it is unavailable and why* — and this
file drives it: the governed file declares the axis unavailable with a reason code; the caller
renders the governed reason sentence; the package positions the sentence under the axis label and
renders nothing else for it. **Every word is his or the catalogue's**: the label comes from the
governed file, the sentence from the reason-message registry, and this package adds the marker.

## Mutations (`tasks.md`, `T1323`)

* the `is_unavailable` branch of `_breakdown_lines` removed (back to `continue`-shaped silence) →
  `test_the_unavailable_axis_is_said_with_its_reason_and_nothing_else` red;
* `unavailable_breakdowns_of` rendering without a supplied sentence → the refusal node red;
* a word of the package's own in the line → `test_no_word_of_the_line_is_the_packages` red.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import pytest

from daily_reporting.numbers.variation import VariationUnit
from daily_reporting.report.breakdown import (
    Breakdown,
    BreakdownGovernance,
    BreakdownGovernanceError,
    UnavailableAxis,
    breakdowns_of,
    unavailable_breakdowns_of,
)
from daily_reporting.report.summary import Line, Summary, render

pytestmark = pytest.mark.unit

#: The governed shape with one unavailable axis declared, as `report_governance/breakdown.yaml`
#: declares it since 2026-09-05. The words here are the fixture's stand-ins; the node over the REAL
#: file lives in `tests/contract/test_the_cut_is_governed_data.py`.
PLAN = UnavailableAxis(
    column="plan",
    label="por plano",
    reason_code="DIMENSION_NOT_APPLICABLE_TO_SOURCE",
    source="subscription_daily",
    kpis=("Sales (qty)", "Trial conversion (%)"),
)
GOVERNANCE = BreakdownGovernance(
    top_n=5,
    axis_labels=(("country", "por pais"), ("game", "por jogo")),
    tail_label="demais",
    tail_noun="valores",
    axis_marker="-",
    value_marker="--",
    unavailable_axes=(PLAN,),
)
#: The sentence the registry renders for the code — handed in as DATA, the way the caller does.
SENTENCE = (
    "A dimensão plan não se aplica à fonte subscription_daily: essa fonte não registra esse "
    "atributo."
)
REASONS = {"plan": SENTENCE}

_BY_COUNTRY = Breakdown(
    column="country",
    label="por pais",
    lines=(("Brasil", Decimal(412)), ("Mexico", Decimal(133))),
    tail_count=0,
    tail_total=Decimal(0),
)


def _line(label: str, *breakdowns: Breakdown) -> Line:
    return Line(
        label=label,
        value=Decimal(763),
        previous_value=Decimal(691),
        variation=Decimal("10.4"),
        unit=VariationUnit.RELATIVE_PERCENT,
        footnoted=False,
        format_type="int",
        breakdowns=breakdowns,
    )


def _rendered(*lines: Line) -> list[str]:
    summary = Summary(day=date(2026, 9, 4), sections=(("Revenue", lines),), periods=None)
    return render(summary, breakdowns_governance=GOVERNANCE).splitlines()


# --- the governance names the axis, per KPI ------------------------------------------------


def test_the_unavailable_axis_is_named_for_the_kpis_his_file_lists_and_no_other() -> None:
    assert GOVERNANCE.unavailable_for("Sales (qty)") == (PLAN,)
    assert GOVERNANCE.unavailable_for("Trial conversion (%)") == (PLAN,)
    assert GOVERNANCE.unavailable_for("New trials") == ()


def test_an_unavailable_axis_becomes_a_breakdown_that_carries_the_reason_and_no_values() -> None:
    (said,) = unavailable_breakdowns_of("Sales (qty)", GOVERNANCE, REASONS)
    assert said.is_unavailable
    assert said.reason == SENTENCE
    assert said.column == "plan" and said.label == "por plano"
    assert said.lines == () and not said.has_tail


def test_a_kpi_his_file_does_not_name_gets_no_unavailable_breakdown() -> None:
    assert unavailable_breakdowns_of("New trials", GOVERNANCE, REASONS) == ()


def test_an_axis_without_its_sentence_refuses_rather_than_a_heading_over_nothing() -> None:
    """A heading that says nothing under it is the silent shape this slice replaces."""
    with pytest.raises(BreakdownGovernanceError, match="plan"):
        unavailable_breakdowns_of("Sales (qty)", GOVERNANCE, {})
    with pytest.raises(BreakdownGovernanceError, match="plan"):
        unavailable_breakdowns_of("Sales (qty)", GOVERNANCE, {"plan": "   "})


def test_the_measured_breakdowns_are_untouched_by_the_declaration() -> None:
    """`breakdowns_of` still answers only what was measured and permitted (`FR-1304`)."""
    rows = (
        {"aggregation_class": "COUNT", "value": 412, "country": "Brasil"},
        {"aggregation_class": "COUNT", "value": 133, "country": "Mexico"},
    )
    found = breakdowns_of(rows, "value", ("country", "game"), GOVERNANCE)
    assert [b.column for b in found] == ["country"]
    assert all(not b.is_unavailable for b in found)


# --- the rendering -------------------------------------------------------------------------


def test_the_unavailable_axis_is_said_with_its_reason_and_nothing_else() -> None:
    """Axis line, then ONE line with his marker and the governed sentence. No values, no tail."""
    (said,) = unavailable_breakdowns_of("Sales (qty)", GOVERNANCE, REASONS)
    lines = _rendered(_line("Sales (qty)", _BY_COUNTRY, said))
    start = lines.index("- por plano")
    assert lines[start + 1] == f"-- {SENTENCE}"
    # Nothing else under the axis: the block ends there. (`splitlines` drops the closing fence,
    # so what follows is either nothing or the fence before the next indicator.)
    assert lines[start + 2 :] in ([], [""]) or lines[start + 2] == ""
    assert not any("demais" in text for text in lines[start:])


def test_the_said_axis_sits_after_the_measured_ones_and_the_others_are_unchanged() -> None:
    """The same message, with one block more — `T1327`'s "no other line changed", in reverse."""
    (said,) = unavailable_breakdowns_of("Sales (qty)", GOVERNANCE, REASONS)
    without = _rendered(_line("Sales (qty)", _BY_COUNTRY))
    with_plan = _rendered(_line("Sales (qty)", _BY_COUNTRY, said))
    # Every line of the report without the declaration is still there, in order, and the said
    # block — its opening blank line, the axis and the sentence — is all that was added.
    assert with_plan == [*without, "", "- por plano", f"-- {SENTENCE}"]


def test_no_word_of_the_line_is_the_packages() -> None:
    """Every word came from the governed file or the registry sentence; this module adds markers."""
    (said,) = unavailable_breakdowns_of("Sales (qty)", GOVERNANCE, REASONS)
    lines = _rendered(_line("Sales (qty)", said))
    block = lines[lines.index("- por plano") : lines.index("- por plano") + 2]
    supplied = set(re.findall(r"[^\W\d_]+", f"{PLAN.label} {SENTENCE}", re.UNICODE))
    for text in block:
        for word in re.findall(r"[^\W\d_]+", text, re.UNICODE):
            assert word in supplied, f"{word!r} is a word nobody supplied"


def test_scaling_keeps_the_reason() -> None:
    """The caller scales every breakdown of a rate KPI; the said one must survive the pass."""
    (said,) = unavailable_breakdowns_of("Trial conversion (%)", GOVERNANCE, REASONS)
    assert said.scaled(lambda n: n * 100).reason == SENTENCE


# --- the governed file's declaration is validated, not trusted -------------------------------


def _document(**unavailable: object) -> dict[str, object]:
    return {
        "top_n": 5,
        "axis_labels": {"country": "por pais"},
        "tail_label": "demais",
        "tail_noun": "valores",
        "unavailable_axes": unavailable,
    }


def test_the_declaration_is_read_from_the_document() -> None:
    governance = BreakdownGovernance.from_document(
        _document(
            plan={
                "label": "por plano",
                "reason_code": "DIMENSION_NOT_APPLICABLE_TO_SOURCE",
                "source": "subscription_daily",
                "kpis": ["Sales (qty)"],
            }
        )
    )
    assert governance.unavailable_axes == (
        UnavailableAxis(
            "plan",
            "por plano",
            "DIMENSION_NOT_APPLICABLE_TO_SOURCE",
            "subscription_daily",
            ("Sales (qty)",),
        ),
    )


def test_a_document_that_declares_none_has_none() -> None:
    document = _document()
    del document["unavailable_axes"]
    assert BreakdownGovernance.from_document(document).unavailable_axes == ()


@pytest.mark.parametrize(
    "declaration",
    [
        pytest.param("not-a-mapping", id="not a mapping"),
        pytest.param({"reason_code": "X", "source": "s", "kpis": ["k"]}, id="no label"),
        pytest.param({"label": "por plano", "source": "s", "kpis": ["k"]}, id="no reason_code"),
        pytest.param({"label": "por plano", "reason_code": "X", "kpis": ["k"]}, id="no source"),
        pytest.param({"label": "por plano", "reason_code": "X", "source": "s"}, id="no kpis"),
        pytest.param(
            {"label": "por plano", "reason_code": "X", "source": "s", "kpis": []}, id="empty kpis"
        ),
        pytest.param(
            {"label": " ", "reason_code": "X", "source": "s", "kpis": ["k"]}, id="blank label"
        ),
    ],
)
def test_a_half_declared_unavailable_axis_refuses(declaration: object) -> None:
    """Silence is not a value (`S-41`): each missing half refuses on its own."""
    with pytest.raises(BreakdownGovernanceError, match="plan"):
        BreakdownGovernance.from_document(_document(plan=declaration))


def test_unavailable_axes_that_is_not_a_mapping_refuses() -> None:
    document = _document()
    document["unavailable_axes"] = ["plan"]
    with pytest.raises(BreakdownGovernanceError, match="unavailable_axes"):
        BreakdownGovernance.from_document(document)
