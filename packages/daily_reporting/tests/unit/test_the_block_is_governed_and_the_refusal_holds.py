"""The block's words come from the governed file, and not closing refuses — `SC-1302`.

`T1315`. Two properties live here and they are the same property seen from two sides: what
the block SAYS is his, and whether the block is said at all is the reconciliation's answer.

**Absence refuses and never defaults**, the `S-41` rule: a governed file that fails to state
something must not be answered for by the package that reads it.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from daily_reporting.report.contribution import (
    ContributionGovernance,
    ContributionGovernanceError,
    Verdict,
    contributions_of,
)

REPO = Path(__file__).resolve().parents[4]
GOVERNED = REPO / "report_governance" / "contribution.yaml"

STATED = {
    "heading": "Quem puxou o desvio",
    "heading_emoji": "\N{BAR CHART}",
    "heading_alert": "Quem puxou",
    "deviation_noun": "do desvio",
    "approximately": "~",
    "became": "\N{RIGHTWARDS ARROW}",
    "unit_singular": "pt",
    "unit_plural": "pts",
    "others": "os demais",
    "others_noun": "valores",
    "compensated": "subiram e compensaram parte",
    "quiet_day": "Sem desvios relevantes",
    #: `T1334`: as quatro palavras da peça 6, exigidas desde que o bloco existe.
    "discarded_heading": "Descartado por medição",
    "inside_band": "dentro da banda",
    "none_of": "nenhum",
    "concentrated": "concentrado",
    "dash": "\N{EM DASH}",
    "tolerance": "0.01",
}


def _rate(value: str, numerator: int, denominator: int) -> dict[str, object]:
    return {
        "country": value,
        "aggregation_class": "RATIO",
        "numerator": numerator,
        "denominator": denominator,
    }


def test_the_production_file_states_every_word_the_block_needs() -> None:
    """Mutation: drop any key from the real file — this refuses, naming the key."""
    governance = ContributionGovernance.from_document(
        yaml.safe_load(GOVERNED.read_text(encoding="utf-8"))
    )

    # SEVENTEEN from the file plus one per axis for each NUMBER it carries his word in --
    # `OD-153` added the singular beside the plural, and `T1334` added the four of the DISCARDED
    # piece (`discarded_heading`, `inside_band`, `none_of`, `concentrated`), transcribed from
    # lines 140-141 of the approved contract. The count is written out so that adding a word to
    # the file without adding it to the vocabulary is a red node rather than a word that reaches
    # him unchecked -- and it did exactly that when the four went in: this node was the one that
    # caught them.
    assert len(governance.words) == 17 + len(governance.axis_plural) + len(governance.axis_singular)
    assert all(word.strip() for word in governance.words)
    assert governance.tolerance == Decimal("0.01")


def test_the_file_says_whose_decision_it_carries() -> None:
    """`OD-108` approved the contract these words are transcribed from, in seven rounds.

    Mutation: change the attribution — red. A governed word whose decision is unnamed is a
    word this repository authored with extra steps.
    """
    stated = yaml.safe_load(GOVERNED.read_text(encoding="utf-8"))

    assert stated["decided_by"] == "OD-108"
    assert stated["kind"] == "report_contribution"
    assert stated["schema_version"] == 1


@pytest.mark.parametrize("missing", sorted(STATED))
def test_a_key_the_file_fails_to_state_is_never_answered_for(missing: str) -> None:
    """`S-41`. Mutation: fall back to a default for any one of them — red on that key."""
    incomplete = {key: value for key, value in STATED.items() if key != missing}

    with pytest.raises(ContributionGovernanceError, match=missing):
        ContributionGovernance.from_document(incomplete)


@pytest.mark.parametrize("emptied", sorted(key for key in STATED if key != "tolerance"))
def test_a_word_that_is_present_but_empty_refuses_too(emptied: str) -> None:
    """A key stated as blank is silence wearing a key's name."""
    blank = {**STATED, emptied: "   "}

    with pytest.raises(ContributionGovernanceError, match=emptied):
        ContributionGovernance.from_document(blank)


@pytest.mark.parametrize("slack", ["-0.01", "1", "1.5"])
def test_a_slack_outside_its_range_refuses(slack: str) -> None:
    """Negative refuses a sum that closes exactly; one whole deviation accepts everything.

    A tolerance of 1 is the reconciliation not happening while a file claims it does, which
    is worse than no check at all.
    """
    with pytest.raises(ContributionGovernanceError, match="tolerance"):
        ContributionGovernance.from_document({**STATED, "tolerance": slack})


def test_a_tolerance_that_is_not_a_number_refuses_rather_than_rounding() -> None:
    with pytest.raises(ContributionGovernanceError, match="tolerance"):
        ContributionGovernance.from_document({**STATED, "tolerance": "quase"})


def test_a_word_stated_as_something_other_than_a_word_refuses() -> None:
    """A governed file states `true` and YAML hands back a `bool`, which is not a word."""
    with pytest.raises(ContributionGovernanceError, match="heading"):
        ContributionGovernance.from_document({**STATED, "heading": True})


def test_the_governed_slack_is_what_decides_whether_the_block_publishes() -> None:
    """**The reconciliation's answer moves with the FILE, not with a number in the package.**

    The same two days reconcile under a loose slack and refuse under the shipped one. Mutation:
    ignore the argument and read the default — red, and the governed file becomes decoration.
    """
    # The slack is RELATIVE to the deviation, so the gap has to be small beside it for the two
    # answers to differ. The gap is the SAMPLE FLOOR: Chile's four cases are below it, so its
    # rate is not described and the total still contains it.
    before = [_rate("Brasil", 100, 1000), _rate("Chile", 40, 4)]
    after = [_rate("Brasil", 150, 1000), _rate("Chile", 300, 4)]

    shipped = contributions_of(
        before, after, "value", "country", sample_floor=30, tolerance=Decimal("0.01")
    )
    loosened = contributions_of(
        before, after, "value", "country", sample_floor=30, tolerance=Decimal("0.99")
    )

    assert shipped.verdict is Verdict.DID_NOT_RECONCILE
    assert not shipped.may_publish
    assert loosened.verdict is Verdict.RECONCILED
    assert loosened.may_publish


def test_the_gap_is_carried_so_the_refusal_can_name_it() -> None:
    """A refusal that cannot say how far off it was is a refusal nobody can act on."""
    block = contributions_of(
        [_rate("Brasil", 100, 1000), _rate("Chile", 40, 4)],
        [_rate("Brasil", 200, 1000), _rate("Chile", 300, 4)],
        "value",
        "country",
        sample_floor=30,
    )

    assert block.verdict is Verdict.DID_NOT_RECONCILE
    assert block.residual != 0
    assert [part.value for part in block.parts] == ["Brasil"]


# --- `OD-153`, 2026-09-06: his singular beside his plural, in the block's own file --------


def test_the_block_file_states_both_numbers_for_both_axes() -> None:
    """The same three words `breakdown.yaml` gained, in the file the block reads.

    **Two files and not one**, and that is by design: the block and the breakdown are rendered
    by different code from different governance, and a word fixed in one of them alone is the
    shape of the defect `OD-119` left for a day — the flag drawn in the breakdown and a bare
    name four lines below it in the block.
    """
    governance = ContributionGovernance.from_document(
        yaml.safe_load(GOVERNED.read_text(encoding="utf-8"))
    )
    plural = dict(governance.axis_plural)
    singular = dict(governance.axis_singular)

    assert plural["country"] == "países"
    assert plural["game"] == "jogos"
    assert singular["country"] == "país"
    assert singular["game"] == "jogo"
    assert plural.keys() == singular.keys()


def test_an_axis_named_in_one_number_and_not_the_other_refuses() -> None:
    """`S-41` again: an axis with half its words is answered for by nobody.

    **Mutation** (2026-09-06): drop `game` from `axis_singular` in the real file — red here,
    and the loader refuses instead of quietly handing back the plural for a count of one.
    """
    with pytest.raises(ContributionGovernanceError, match="game"):
        ContributionGovernance.from_document(
            {**STATED, "axis_plural": {"game": "jogos"}, "axis_singular": {}}
        )
    with pytest.raises(ContributionGovernanceError, match="country"):
        ContributionGovernance.from_document(
            {**STATED, "axis_plural": {}, "axis_singular": {"country": "país"}}
        )


@pytest.mark.parametrize("stated", ["   ", None, 7])
def test_an_axis_singular_listed_with_nothing_beside_it_refuses(stated: object) -> None:
    with pytest.raises(ContributionGovernanceError, match="game"):
        ContributionGovernance.from_document(
            {**STATED, "axis_plural": {"game": "jogos"}, "axis_singular": {"game": stated}}
        )


def test_an_axis_singular_that_is_not_a_mapping_refuses() -> None:
    with pytest.raises(ContributionGovernanceError, match="axis_singular"):
        ContributionGovernance.from_document({**STATED, "axis_singular": ["país"]})


def test_the_block_noun_agrees_with_its_count() -> None:
    """One is the singular, everything else is the plural, and an unnamed axis keeps the noun.

    **Mutation**: always plural — red on the first loop; always singular — red on the second.
    """
    governance = ContributionGovernance.from_document(
        yaml.safe_load(GOVERNED.read_text(encoding="utf-8"))
    )

    for column, word in governance.axis_singular:
        assert governance.noun_for(column, 1) == word, column
    for column, word in governance.axis_plural:
        for count in (0, 2, 43):
            assert governance.noun_for(column, count) == word, (column, count)
    for count in (1, 5):
        assert governance.noun_for("an_axis_he_named_nothing_for", count) == governance.others_noun
