"""The breakdown's cut and words are DATA, not literals — `T1302`, `D-1302` (`OD-111`).

The report is about to show a breakdown, and a breakdown needs three things that are
decisions rather than mechanics: how many lines before the tail, what each axis is called,
and what the tail is called. **All three are his**, and the point of this file is that none of
them can quietly become the package's.

## The cut cannot be written in the package, and that is measured

`test_the_loop_enumerates_nothing.py:41` carries `ENUMERATED_TOTALS = (20, 5, 19)` and sweeps
the package for those integers. A `TOP_N = 5` would go red on the first run. So the five
arrives as data, the way `declared_order` already does — and the node below drives that by
reading the governed file and the module together, rather than by trusting the arrangement.

## The words are his, and they are not authored here either

`por pais`, `por jogo` and `demais` are in the example contract he approved, word for word.
They reach the package through the same governed file, so `AUTHORED_WORDS` does not grow and
the node asserting its size does not move. If he wants a different word, the file changes and
no code does — which is the property the last node drives.

## Absence is refused, never defaulted

The `S-41` lesson one feature over: a governed file that fails to state something must not be
answered for. Every missing key, every out-of-range cut and every empty label refuses, and
each refusal is driven separately — one node for "malformed is refused" would go green the day
four of the five checks were deleted.
"""

from __future__ import annotations

import ast
import re
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
import yaml

from daily_reporting.report import breakdown as module
from daily_reporting.report.breakdown import (
    MAXIMUM_LINES,
    Breakdown,
    BreakdownGovernance,
    BreakdownGovernanceError,
    breakdowns_of,
    cut_to_top,
)
from daily_reporting.report.snapshot import SnapshotMarkGovernance
from daily_reporting.view.shape import ViewRow

pytestmark = pytest.mark.contract

#: `tests/contract/` -> `tests/` -> package -> `packages/` -> repository.
REPO = Path(__file__).resolve().parents[4]
GOVERNED = REPO / "report_governance" / "breakdown.yaml"


def _document() -> dict[str, object]:
    if not GOVERNED.is_file():  # pragma: no cover - a checkout without the governed file
        pytest.skip(f"{GOVERNED} is not in this checkout; nothing was measured")
    return yaml.safe_load(GOVERNED.read_text(encoding="utf-8"))


def test_the_governed_file_states_the_cut_and_the_words() -> None:
    """Non-vacuity: if the file said nothing, every node here would assert nothing."""
    governance = BreakdownGovernance.from_document(_document())
    assert 1 <= governance.top_n <= MAXIMUM_LINES
    assert governance.columns, "no axis is declared; the report could break down by nothing"
    assert governance.tail_label.strip()


def test_the_cut_is_written_in_no_python_file_of_this_package() -> None:
    """**The defect this exists to prevent, driven over the source rather than described.**

    Parsed with `ast` rather than grepped, so a number inside a docstring or a comment — where
    it is documentation and not behaviour — does not count, and a number in a default argument
    or a constant does.
    """
    cut = BreakdownGovernance.from_document(_document()).top_n
    offenders: list[str] = []
    for path in (REPO / "packages" / "daily_reporting" / "src").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value is cut:
                offenders.append(f"{path.relative_to(REPO)}:{node.lineno}")
    assert not offenders, (
        f"the cut {cut} is written into the package at {offenders}; it has to arrive as data"
    )


def test_the_words_are_written_in_no_python_file_of_this_package() -> None:
    """His words live in the governed file. A copy in the package is a second source.

    **Covers every governed word the report prints**, not just the breakdown's: `F2` added
    the second reference's `label` and `against` from `references.yaml`, and a mutation
    proved they were unguarded — turning them into default arguments inside the package went
    green. A node that watches one governed file while the report reads two is a node whose
    scope stopped matching its name.

    **Driven again on 2026-09-05** when the third file arrived (`SC-1306`): his phrase
    written as a constant in `report/snapshot.py` → `1 failed, 29 passed`. A widening that
    was not seen to bite is a widening nobody measured.
    """
    governance = BreakdownGovernance.from_document(_document())
    words = [label for _column, label in governance.axis_labels] + [
        governance.tail_label,
        governance.tail_noun,
    ]
    #: `OD-144`, 2026-09-06: the split tail's three words and the per-axis plural it borrows.
    #: They reach the reader, so they are watched — **the same reasoning that added the
    #: snapshot mark below, applied on the day the file grew.** A node watching fewer keys
    #: than the report renders is a node that stops guarding without failing.
    for key in ("sampled_qualifier", "withheld_label", "withheld_value"):
        stated_word = _document().get(key)
        if isinstance(stated_word, str) and stated_word.strip():
            words.append(stated_word)
    #: **`axis_plural` is NOT watched, and that is measured rather than forgotten.** Adding it
    #: turns two docstrings of this package red, and both are TRANSCRIPTIONS OF HIS OWN
    #: MESSAGES — the plural sits inside the sentence he wrote asking for the split. The same
    #: is true of `references.yaml`'s `was`, a common verb that stands inside his quoted
    #: *"0,01 / nao era para ter %?"* in `report/summary.py`. This is the false-positive class
    #: the comment below already records about `OD-7` containing `D-7`: a guard that forbids
    #: quoting him in a comment is guarding the wrong thing. `contribution.yaml`'s own
    #: `axis_plural` has never been watched here for the same reason.
    references = REPO / "report_governance" / "references.yaml"
    if references.is_file():
        stated = cast("dict[str, object]", yaml.safe_load(references.read_text(encoding="utf-8")))
        words += [str(stated["label"]), str(stated["against"])]
        #: `OD-147`'s `was` is deliberately not appended — see the note above `references`.
    #: `SC-1306`, 2026-09-05: the report now reads a THIRD governed file, and this node's own
    #: docstring says what happens when it watches fewer files than the report reads. The whole
    #: PHRASE is the word here — `snapshot` on its own is the view's name for the class and is
    #: legitimately written in this package; what may not be copied is his sentence.
    marked = REPO / "report_governance" / "snapshot_mark.yaml"
    if marked.is_file():
        stated = cast("dict[str, object]", yaml.safe_load(marked.read_text(encoding="utf-8")))
        words += [str(stated["mark"])]
    offenders: list[str] = []
    for path in (REPO / "packages" / "daily_reporting" / "src").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for word in words:
                    #: **Whole word, not substring** — measured: a substring test reported
                    #: eight offenders that were all `OD-7`, the owner decision, which
                    #: contains `D-7`. A guard that cries wolf on a decision id is a guard
                    #: somebody switches off.
                    if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", node.value):
                        offenders.append(f"{path.relative_to(REPO)}:{node.lineno} {word!r}")
    assert not offenders, f"his words are copied into the package at {offenders}"


def test_changing_the_file_changes_the_cut_with_no_code_change() -> None:
    """The whole point of governed data: he moves the number, nobody edits Python."""
    document = _document()
    document["top_n"] = 3
    assert BreakdownGovernance.from_document(document).top_n == 3


def test_a_missing_key_refuses_rather_than_defaulting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`S-41`, one feature over: silence is not a value."""
    for key in ("top_n", "axis_labels", "tail_label"):
        document = _document()
        del document[key]
        with pytest.raises(BreakdownGovernanceError, match=key):
            BreakdownGovernance.from_document(document)


@pytest.mark.parametrize("cut", [0, -1, MAXIMUM_LINES + 1])
def test_a_cut_outside_the_ceiling_refuses(cut: int) -> None:
    """`SC-1304` caps a breakdown at ten lines, and zero shows nothing at all."""
    document = _document()
    document["top_n"] = cut
    with pytest.raises(BreakdownGovernanceError, match="top_n"):
        BreakdownGovernance.from_document(document)


def test_a_non_integer_cut_refuses_because_truthiness_is_not_a_number() -> None:
    """The same shape as `S-41`'s string boolean: a value of the wrong type is not an answer."""
    document = _document()
    document["top_n"] = "5"
    with pytest.raises(BreakdownGovernanceError, match="not an integer"):
        BreakdownGovernance.from_document(document)


def test_an_empty_label_refuses() -> None:
    """A tail nobody can name is a truncation that hides."""
    document = _document()
    document["tail_label"] = "   "
    with pytest.raises(BreakdownGovernanceError, match="tail_label"):
        BreakdownGovernance.from_document(document)


def test_the_ceiling_is_the_specifications_and_the_cut_is_his() -> None:
    """Two numbers with two owners, and the module says which is which.

    `MAXIMUM_LINES` is `SC-1304` — a rule of the specification, so it lives in the package.
    The cut is a decision, so it does not. Reversing that is how a rule becomes negotiable and
    a decision becomes frozen.
    """
    assert MAXIMUM_LINES == 10
    assert BreakdownGovernance.from_document(_document()).top_n <= MAXIMUM_LINES
    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    assigned = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    assert "MAXIMUM_LINES" in assigned
    assert "TOP_N" not in assigned, "the cut acquired a home in the package"


# --- the cut applied: top-N and a NAMED tail — `T1305`, `FR-1303`, `SC-1304` -------------
#
# Truncation is only honest when the reader can tell it happened and how much it hid. So the
# tail carries BOTH numbers: how many values were cut and what they summed to. One without
# the other is a half-truth that reads like a whole one.


def _governance(**overrides: object) -> BreakdownGovernance:
    document = _document()
    document.update(overrides)
    return BreakdownGovernance.from_document(document)


def _partitions(
    *pairs: tuple[str, int],
) -> tuple[tuple[str, tuple[ViewRow, ...]], ...]:
    """One COUNT row per value — the shape `cut_to_top` reads after the tail became aggregated.

    The signature changed on 2026-09-04 and these nodes changed with it: the tail is now
    computed from the ROWS it cut rather than from their numbers, because summing a rate's
    parts printed a percentage of nothing against the real warehouse.
    """
    return tuple(
        (value, ({"aggregation_class": "COUNT", "value": number},)) for value, number in pairs
    )


def _cut(partitions: tuple[tuple[str, tuple[ViewRow, ...]], ...], top_n: int) -> Breakdown:
    found = cut_to_top(partitions, _governance(top_n=top_n), "country", "value")
    assert found is not None
    return found


_TWELVE = _partitions(*((f"v{index:02d}", 100 - index * 5) for index in range(12)))


def test_a_breakdown_longer_than_the_cut_keeps_the_cut_and_names_the_rest() -> None:
    breakdown = _cut(_TWELVE, top_n=5)
    assert len(breakdown.lines) == 5
    assert breakdown.tail_count == 7
    assert breakdown.tail_total == Decimal(sum(100 - index * 5 for index in range(5, 12)))
    assert breakdown.has_tail


def test_a_breakdown_at_or_under_the_cut_has_no_tail_at_all() -> None:
    """A tail that is always there teaches a reader to skip tails."""
    breakdown = _cut(_TWELVE[:4], top_n=5)
    assert len(breakdown.lines) == 4
    assert breakdown.tail_count == 0
    assert breakdown.tail_total == Decimal(0)
    assert not breakdown.has_tail


def test_the_ranking_is_by_magnitude_so_a_big_fall_is_not_hidden() -> None:
    """A breakdown exists to show what MOVED. A large negative part is not less interesting."""
    breakdown = _cut(_partitions(("up", 10), ("down", -99), ("flat", 1)), top_n=2)
    assert [value for value, _n in breakdown.lines] == ["down", "up"]


def test_the_order_is_stable_for_the_same_data() -> None:
    """Two runs of the same day must not render two different reports."""
    values = _partitions(("b", 5), ("a", 5), ("c", 5))
    assert _cut(values, top_n=2).lines == _cut(tuple(reversed(values)), top_n=2).lines


def test_the_cut_loses_no_number_and_invents_none() -> None:
    """What is shown plus what the tail names equals everything that was handed in.

    **This replaced a node that asserted a distinction which does not exist here**, and the
    mutation that survived is what exposed it: inside this function, "sum the cut parts" and
    "everything minus what is shown" are the same number by construction, so a node preferring
    one over the other tested nothing. The property that IS real is conservation — a cut that
    dropped a value or double-counted one would break this and could not break the other.
    """
    values = _partitions(("a", 10), ("b", 6), ("c", 4), ("d", -8))
    breakdown = _cut(values, top_n=1)
    shown = sum((number for _value, number in breakdown.lines), Decimal(0))
    assert shown + breakdown.tail_total == Decimal(10 + 6 + 4 - 8)
    assert len(breakdown.lines) + breakdown.tail_count == len(values)


def test_the_label_of_the_axis_is_his_word_from_the_governed_file() -> None:
    breakdown = _cut(_TWELVE, top_n=5)
    assert breakdown.label == dict(_governance().axis_labels)["country"]


def test_the_exclusions_come_from_the_governed_file_and_not_from_a_default() -> None:
    """**Added after a mutation survived**: `excluded_for` returning `()` unconditionally
    passed every node in this repository, because the only nodes that read exclusions were
    handed the values directly.

    So this one reads the FILE and the object together: what the governed document declares
    for a column is what the object answers for it, and a column that declares nothing gets
    nothing. The measurement that justifies the exclusion existing at all lives in the node
    beside it, in the partition tests.
    """
    document = _document()
    stated: object = document.get("excluded_values") or {}
    assert isinstance(stated, dict), "the governed exclusions are not a mapping"
    declared = cast("dict[str, list[str]]", stated)
    assert declared, "the governed file declares no exclusion; this node would assert nothing"
    governance = BreakdownGovernance.from_document(document)
    for column, values in declared.items():
        assert governance.excluded_for(column) == tuple(values)
    assert governance.excluded_for("a_column_that_declares_none") == ()


def test_a_malformed_exclusion_block_refuses_rather_than_being_ignored() -> None:
    """Silence is not a value, and neither is a shape nobody can read (`S-41`)."""
    document = _document()
    document["excluded_values"] = ["(Total)"]
    with pytest.raises(BreakdownGovernanceError, match="excluded_values"):
        BreakdownGovernance.from_document(document)


# --- deny-by-default survives the change — `T1307`, `FR-1304` ----------------------------
#
# `allowed_dimensions` is deny-by-default by the catalogue's own design: an axis not listed is
# FORBIDDEN, not merely undocumented. The report must not widen that by accident, and the way
# it would widen is the easy one — showing every axis the DATA happens to carry.

_KPI_ROWS: tuple[ViewRow, ...] = (
    {"country": "Brasil", "game": "Valorant", "aggregation_class": "COUNT", "value": 10},
    {"country": "Mexico", "game": "Fortnite", "aggregation_class": "COUNT", "value": 4},
)


def test_a_kpi_shows_only_the_axes_its_contract_allows() -> None:
    only_country = breakdowns_of(_KPI_ROWS, "value", ("country", "date"), _governance())
    assert [breakdown.column for breakdown in only_country] == ["country"]


def test_a_kpi_that_allows_both_shows_both_in_the_governed_order() -> None:
    """Two KPIs allowing the same axes must render them the same way round."""
    both = breakdowns_of(_KPI_ROWS, "value", ("game", "country"), _governance())
    assert [breakdown.column for breakdown in both] == list(_governance().columns)


def test_an_axis_the_report_does_not_govern_is_not_shown_even_if_allowed() -> None:
    """Deny-by-default in BOTH directions: the two lists must agree for a line to exist."""
    shown = breakdowns_of(_KPI_ROWS, "value", ("country", "platform"), _governance())
    assert all(breakdown.column != "platform" for breakdown in shown)


def test_a_kpi_allowing_nothing_shows_nothing() -> None:
    assert breakdowns_of(_KPI_ROWS, "value", (), _governance()) == ()


def test_an_axis_with_no_measurable_partition_produces_no_empty_heading() -> None:
    """A heading with nothing under it is a line claiming a measurement happened."""
    blank = ({"aggregation_class": "COUNT", "value": 5},)
    assert breakdowns_of(blank, "value", ("country", "game"), _governance()) == ()


def test_the_governed_words_are_the_words_the_approved_artefacts_use() -> None:
    """**The node that would have caught `S-44`, and did not exist when it happened.**

    The render went out saying `por pais` while the contract he approved says it WITH the
    accent — measured on the two artefacts: 8 occurrences in the example contract, 11 in his
    own examples, ZERO without. And the tail dropped the noun that `FR-1303` and `SC-1304`
    both spell out, for the worst reason available: the origination gate would have refused a
    word nobody governed, so the word was dropped instead of being governed.

    Removing the accent is not caught by any behavioural node — the report renders happily
    with a wrong word, and every other node here reads the file rather than the artefact. So
    this one asserts the words THEMSELVES.

    **When he changes a word, this node goes red on purpose.** That is the point: a word in
    the message he reads is his, and changing it should require re-measuring the artefacts
    rather than editing a file quietly. The fix is to update this node WITH the new
    measurement beside it, never to loosen it.
    """
    governance = BreakdownGovernance.from_document(_document())
    labels = dict(governance.axis_labels)
    assert labels["country"] == "por país", (
        "the country label lost its accent; the approved artefacts carry it 19 times between "
        "them and never once without"
    )
    assert labels["game"] == "por jogo"
    assert governance.tail_label == "demais"
    assert governance.tail_noun == "valores", (
        "the tail lost the noun that FR-1303 and SC-1304 both spell out"
    )


# --- `OD-153`, 2026-09-06: the three words the governance was missing --------------------
#
# `jogos`, `país`, `jogo`. They arrive as DATA in the two governed files, which is why the
# authored-word ledger does not move: `AUTHORED_WORDS` counts what `template.py` holds, and
# these are held by no Python file at all.
#
# The refusal that stood until he spoke was correct and is recorded rather than tidied away:
# with no plural of his for the game axis, the tail fell back to the governed generic noun.
# That is the behaviour a missing word is supposed to produce. What was a real defect is the
# other line — a plural over a count of one — and it was a defect of the AGREEMENT, because
# the file carried exactly one word per axis and a count of one has no word to reach for.


def test_the_governed_file_states_his_three_new_words() -> None:
    """**The words themselves, asserted here for the reason the labels above are.**

    No behavioural node catches a word changed to a near neighbour: the report renders happily
    with the wrong one. When he changes a word this goes red on purpose, and the fix is to
    update it WITH the new decision beside it rather than to loosen it.
    """
    governance = BreakdownGovernance.from_document(_document())
    plural = dict(governance.axis_plural)
    singular = dict(governance.axis_singular)

    assert plural["country"] == "países"
    assert plural["game"] == "jogos", "the axis fell back for want of a word he has now given"
    assert singular["country"] == "país"
    assert singular["game"] == "jogo"


def test_the_two_number_maps_name_the_same_axes_and_a_gap_refuses() -> None:
    """**An axis named in one number and not the other renders the wrong word for the other.**

    That is the defect `OD-153` closed, seen from the loader's side: the file used to carry a
    plural for `country` and nothing else, so a tail of one had only the word for many. A file
    that grows a plural and forgets the singular reintroduces it silently, and silence is not a
    value (`S-41`).

    **Mutation** (2026-09-06): drop `game` from `axis_singular` in the real file — this node
    red, and the loader refuses rather than falling back with a word that reads wrong.
    """
    document = _document()
    governance = BreakdownGovernance.from_document(document)
    assert dict(governance.axis_plural).keys() == dict(governance.axis_singular).keys()

    without = _document()
    del cast("dict[str, object]", without["axis_singular"])["game"]
    with pytest.raises(BreakdownGovernanceError, match="game"):
        BreakdownGovernance.from_document(without)

    other_way = _document()
    del cast("dict[str, object]", other_way["axis_plural"])["country"]
    with pytest.raises(BreakdownGovernanceError, match="country"):
        BreakdownGovernance.from_document(other_way)


def test_an_axis_singular_listed_with_nothing_beside_it_refuses() -> None:
    """The same refusal `axis_plural` already makes, and for the same reason."""
    for stated in ("   ", None, 7):
        document = _document()
        cast("dict[str, object]", document["axis_singular"])["game"] = stated
        with pytest.raises(BreakdownGovernanceError, match="game"):
            BreakdownGovernance.from_document(document)


def test_an_axis_singular_that_is_not_a_mapping_refuses() -> None:
    """A shape nobody can read is not a value either."""
    document = _document()
    document["axis_singular"] = ["país", "jogo"]
    with pytest.raises(BreakdownGovernanceError, match="axis_singular"):
        BreakdownGovernance.from_document(document)


def test_the_noun_agrees_with_the_count_on_the_real_governed_file() -> None:
    """Read off the file the report actually loads, not off a fixture built to agree with it."""
    governance = BreakdownGovernance.from_document(_document())

    for column, word in governance.axis_singular:
        assert governance.noun_for(column, 1) == word, column
    for column, word in governance.axis_plural:
        for count in (0, 2, 43):
            assert governance.noun_for(column, count) == word, (column, count)
    #: An axis his file names in neither map keeps the governed generic noun for every count —
    #: the fallback `OD-144` established, unchanged by `OD-153`.
    for count in (1, 5):
        assert governance.noun_for("a_column_he_named_no_word_for", count) == governance.tail_noun


# --- `F5`: the axis he asked for that the source lacks is DECLARED unavailable, in his words ----


def test_the_governed_file_declares_plan_unavailable_under_the_indicators_his_contract_names() -> (
    None
):
    """`T1323` (`FR-1314`, `FR-1316`, `OD-127`): the refusal is declared as data, not coded.

    Every word of the declaration has an origin outside this package, and the yaml comment names
    it line by line: the label is his (`contrato-013-exemplos.md` :50, :56, :91, :175), the two
    indicators are his (:37 — *"Sales e Conversion: pais, jogo, plano e gateway"*), and the reason
    is not written in the file at all — it is a CODE into `001`'s registry.
    """
    governance = BreakdownGovernance.from_document(_document())
    (plan,) = [axis for axis in governance.unavailable_axes if axis.column == "plan"]
    assert plan.label == "por plano"
    assert plan.reason_code == "DIMENSION_NOT_APPLICABLE_TO_SOURCE"
    assert plan.source == "subscription_daily"
    assert plan.kpis == ("Sales (qty)", "Trial conversion (%)")
    # And the two are indicators this report shows breakdowns for at all.
    assert set(plan.kpis) <= set(governance.kpis)
    # `New trials` is NOT named: his contract says trial has no plan (:37).
    assert governance.unavailable_for("New trials") == ()


def test_the_governed_file_declares_gateway_unavailable_under_the_same_two_indicators() -> None:
    """`T1325` (`FR-1315`, `FR-1316`, `OD-128`): gateway refuses BY NAME while the view is absent.

    Same shape as plan, same provenance discipline: the label is his (`contrato-013-exemplos.md`
    :51, :57, :88, :175), the indicators are his (:37 — *"trial nao tem plano nem gateway"*), the
    reason is a CODE. Remeasured 2026-09-05 13:02 -03: no governed source carries a gateway column
    and the `semantic` dataset holds no join view.

    **Mutation** (`T1325`): the `gateway` block removed from `unavailable_axes` → this node red,
    and the report would go silent about an axis he asked for by name. Measured 2026-09-05:
    `1 failed, 28 passed` here and `2 failed, 3 passed` in the bot file.
    """
    governance = BreakdownGovernance.from_document(_document())
    (gateway,) = [axis for axis in governance.unavailable_axes if axis.column == "gateway"]
    assert gateway.label == "por gateway"
    assert gateway.reason_code == "DIMENSION_NOT_APPLICABLE_TO_SOURCE"
    assert gateway.source == "subscription_daily"
    assert gateway.kpis == ("Sales (qty)", "Trial conversion (%)")
    assert set(gateway.kpis) <= set(governance.kpis)
    assert governance.unavailable_for("New trials") == ()
    # Both refusals stand under each of the two indicators, plan first as declared.
    for kpi in gateway.kpis:
        assert [axis.column for axis in governance.unavailable_for(kpi)] == ["plan", "gateway"]


def test_the_declared_reason_code_and_source_exist_in_the_catalogue() -> None:
    """A code the registry lacks, or a source the catalogue does not govern, is not a reason."""
    governance = BreakdownGovernance.from_document(_document())
    registry = yaml.safe_load(
        (REPO / "semantic" / "content" / "reason-messages.pt-BR.yaml").read_text(encoding="utf-8")
    )
    codes = {entry["reason_code"] for entry in registry["messages"]}
    sources = {path.stem for path in (REPO / "semantic" / "sources").glob("*.yaml")}
    for axis in governance.unavailable_axes:
        assert axis.reason_code in codes, axis
        assert axis.source in sources, axis
        assert (REPO / "semantic" / "dimensions" / f"{axis.column}.yaml").is_file(), axis


def test_an_unavailable_axis_is_not_also_a_measured_one() -> None:
    """Declared unavailable AND listed in `axis_labels` would be two claims about one axis."""
    governance = BreakdownGovernance.from_document(_document())
    assert not {axis.column for axis in governance.unavailable_axes} & set(governance.columns)


def test_the_level_mark_is_a_governed_file_the_package_can_read() -> None:
    """`SC-1306`, `T1330`: the phrase that marks a level, on the real file the report loads.

    The unit nodes drive the rendering with a phrase of their own, deliberately not this one,
    so nothing there passes by echoing a literal. **This node is the other question**: does the
    file the deliverer actually opens exist, say which kind it is, and hand over a phrase.

    A `kind` that drifted is what sent the section order into `semantic/` for one commit and
    came back with 131 `UnknownKindError` — the same header, checked here before it can happen
    a second time.
    """
    stated = cast(
        "dict[str, object]",
        yaml.safe_load(
            (REPO / "report_governance" / "snapshot_mark.yaml").read_text(encoding="utf-8")
        ),
    )
    assert stated["kind"] == "report_snapshot_mark", stated["kind"]
    for key in ("schema_version", "decided_by", "decided_on"):
        assert stated[key], key
    governance = SnapshotMarkGovernance.from_document(stated)
    assert governance.words == (governance.mark,)
    #: Punctuation is the renderer's — the file states the words and nothing else. A phrase
    #: arriving with its own parentheses would print them twice.
    assert not set(governance.mark) & set("()·*")
