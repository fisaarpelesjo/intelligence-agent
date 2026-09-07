"""Every caveat arrives at the position the finding occupies — T021 (`FR-011`, `SC-008`).

**A caveat is not ours, and that is the whole reason it must travel.** The per-game
breakdown is *"uma aproximação declarada pela própria origem: a assinatura inteira é
atribuída ao jogo mais jogado do usuário"* — the source says so, `005` carries it, and a
ranking that puts a game first while dropping that sentence presents an approximation as
a measurement. `spec.md` § 2 names exactly that.

## What is asserted, and why not simply "the field exists"

A `caveats` field that exists and arrives empty satisfies nothing, so the assertions run
over the **whole path a finding takes**: grouped into ties, placed into an ordering per
class, placed into a normalised ordering, and carried as not-prioritisable. Each is a
place where a caveat could be dropped by rebuilding a finding instead of carrying it.

**And the sentence is compared against the catalog's own text, not against a copy.** A
copy in this file would drift the day the source is re-worded and the drift would look
like a passing test.

## The one transformation, measured rather than assumed

`PriorityModel` sets ``str_strip_whitespace``, so a caveat loses whitespace around it.
It is measured here and stated: **the surrounding whitespace goes, the sentence does
not** — inner spacing, accents and punctuation arrive byte for byte.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from anomaly_investigation.contracts import AggregationClass
from pydantic import ValidationError

from insights_prioritisation.contracts import (
    ComponentAbsence,
    Normalisation,
    NotPrioritisable,
    Ordering,
    PrioritisedFinding,
    PriorityComponent,
    PriorityReasonCode,
)
from insights_prioritisation.order import (
    group_ties,
    one_ordering_per_class,
    single_normalised_ordering,
)

pytestmark = pytest.mark.contract

INSTANT = datetime(2026, 8, 26, 13, 24, tzinfo=UTC)

#: The three shapes `FR-011` names: approximate attribution, unreconciled segments,
#: withheld freshness. Held as a fixture of INPUT, never as something this feature says.
CAVEATS = (
    "A quebra por jogo e uma aproximacao declarada pela propria origem.",
    "Os segmentos nao reconciliam com o total.",
    "A frescura da origem foi retida.",
)

#: Where the real sentence lives. Read rather than copied — see the module docstring.
SOURCE_FILE = "semantic/sources/subscription_daily.yaml"


def _finding(identifier: str, *, caveats: tuple[str, ...] = CAVEATS) -> PrioritisedFinding:
    return PrioritisedFinding(
        finding_id=identifier,
        components=(
            PriorityComponent(
                name="magnitude", read_from="candidate_finding", value=Decimal("0.5")
            ),
        ),
        reading_instant=INSTANT,
        caveats=caveats,
    )


def _carried(orderings: tuple[Ordering, ...]) -> dict[str, tuple[str, ...]]:
    """What arrived, by finding, across every position and every unplaced finding.

    **Annotated with what it actually receives.** A bare `tuple` made every attribute read
    below untyped, so twelve strict errors came from one missing pair of brackets -- and,
    worse than the count, a wrong attribute name in this loop would have gone unreported.
    """
    arrived: dict[str, tuple[str, ...]] = {}
    for ordering in orderings:
        for group in ordering.positions:
            for finding in group:
                arrived[finding.finding_id] = finding.caveats
        for unplaced in ordering.not_prioritisable:
            arrived[unplaced.finding_id] = unplaced.caveats
    return arrived


def test_every_caveat_is_on_the_position_the_finding_occupies() -> None:
    """`SC-008` measured over each caveat, not over the field's existence."""
    orderings = one_ordering_per_class(
        {
            AggregationClass.COUNT: [(_finding("a"),)],
            AggregationClass.SNAPSHOT: [(_finding("c"),)],
        }
    )
    arrived = _carried(orderings)
    assert set(arrived) == {"a", "c"}
    for finding_id, caveats in arrived.items():
        for caveat in CAVEATS:
            assert caveat in caveats, f"{caveat!r} did not reach {finding_id}"


def test_a_normalised_ordering_carries_them_too() -> None:
    """The cross-class path is a second place a finding could be rebuilt."""
    ordering = single_normalised_ordering(
        [(_finding("a"), _finding("b"))],
        normalisation=Normalisation(
            basis="declared_basis",
            covers=(AggregationClass.COUNT, AggregationClass.SNAPSHOT),
        ),
        classes_present=(AggregationClass.COUNT, AggregationClass.SNAPSHOT),
    )
    assert _carried((ordering,)) == {"a": CAVEATS, "b": CAVEATS}


def test_a_tie_does_not_merge_two_findings_into_one_set_of_caveats() -> None:
    """**Two findings that tie are two findings**, and their caveats are not pooled.

    A tie is the place where merging looks harmless: the members are equal on every
    component, so treating the group as one row is tempting. It is not harmless — the
    approximation attached to ONE of them would then be read as covering both, or as
    covering neither.
    """
    first = _finding("a", caveats=(CAVEATS[0],))
    second = _finding("b", caveats=(CAVEATS[1],))
    groups = group_ties([first, second])
    assert len(groups) == 1, "the fixture no longer ties, so this measures nothing"

    orderings = one_ordering_per_class({AggregationClass.COUNT: groups})
    assert _carried(orderings) == {"a": (CAVEATS[0],), "b": (CAVEATS[1],)}


def test_a_finding_that_could_not_be_placed_keeps_its_caveats() -> None:
    """**The easiest one to lose, and the worst one to lose.**

    A not-prioritisable finding is already the report of a gap. Dropping its caveats
    would leave a reader with a finding that is both unplaced and unqualified.
    """
    unplaced = NotPrioritisable(
        finding_id="d",
        components=(
            PriorityComponent(
                name="reach",
                read_from="investigation",
                absence=ComponentAbsence(reason=PriorityReasonCode.PRIORITY_COMPONENT_UNAVAILABLE),
            ),
        ),
        reading_instant=INSTANT,
        caveats=CAVEATS,
    )
    orderings = one_ordering_per_class(
        {AggregationClass.COUNT: [(_finding("a"),)]}, not_prioritisable=[unplaced]
    )
    assert _carried(orderings)["d"] == CAVEATS


def test_the_sentence_is_the_source_s_own_and_is_not_a_copy_kept_here() -> None:
    """**Compared against the catalog, because a copy in this file would drift.**

    The caveat belongs to `semantic/sources/subscription_daily.yaml`. If the source
    re-words it, a finding must travel the NEW words — a fixture holding the old ones
    would keep passing while the output said something the source no longer says.
    """
    root = Path(__file__).resolve()
    while root.parent != root and not (root / SOURCE_FILE).exists():
        root = root.parent
    catalog = root / SOURCE_FILE
    if not catalog.exists():  # pragma: no cover - a checkout without the catalog
        pytest.skip(f"{SOURCE_FILE} is not in this checkout; absence is not a failure here")

    limitations = yaml.safe_load(catalog.read_text(encoding="utf-8"))["content"]["limitations"]
    stated = [line for line in limitations if "quebra por jogo" in line]
    assert len(stated) == 1, (
        "the per-game approximation is no longer stated once in the source; FR-011 names "
        "it explicitly and this node cannot measure what it cannot find"
    )

    travelled = _carried(
        one_ordering_per_class({AggregationClass.COUNT: [(_finding("a", caveats=(stated[0],)),)]})
    )
    assert travelled["a"] == (stated[0],), (
        "the source's own sentence did not arrive unchanged at the position"
    )


def test_the_only_transformation_is_the_whitespace_around_it() -> None:
    """Measured, not assumed: `str_strip_whitespace` is on the base model.

    Surrounding whitespace goes. **Inner spacing, accents and punctuation do not** — a
    caveat that arrived normalised would be a paraphrase with extra steps.
    """
    exact = "  Uma aproximacao:  a assinatura inteira e atribuida ao jogo.  "
    finding = _finding("a", caveats=(exact,))
    assert finding.caveats == (exact.strip(),)
    assert finding.caveats[0] != exact.strip().replace("  ", " ")


def test_the_position_holds_the_finding_itself_so_nothing_can_drop_a_caveat_later() -> None:
    """**The structural half: the ordering carries the object, and the object is frozen.**

    Travel is not a copy step that could be skipped — the position IS the finding, so a
    caveat can only be lost by losing the finding. And nothing downstream can strip one
    afterwards, because the model refuses the assignment.
    """
    finding = _finding("a")
    orderings = one_ordering_per_class({AggregationClass.COUNT: [(finding,)]})
    assert orderings[0].positions[0][0] is finding

    with pytest.raises(ValidationError):
        finding.caveats = ()


def test_the_comparison_would_notice_a_dropped_caveat() -> None:
    """**Proof this file bites.** A finding rebuilt without its caveats, same path."""
    stripped = _finding("a", caveats=())
    arrived = _carried(one_ordering_per_class({AggregationClass.COUNT: [(stripped,)]}))
    assert arrived["a"] != CAVEATS, "the comparison cannot tell a dropped caveat from a carried one"
