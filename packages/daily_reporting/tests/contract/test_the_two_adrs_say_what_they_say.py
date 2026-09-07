"""The authority is read from the two documents, not from memory — `T833`, `FR-824`.

**An ADR that exists is not an ADR that was measured.** `ADR 0036` was written in the cycle
that found `ADR 0035` did not cover this feature, and until now nothing checked that the
file says what the ledger claims it says.

This node reads **both**: the one that authorizes the two products, and the one that must
stay untouched and go on governing the prioritisable finding. Reading only the new one would
leave the half that matters unchecked — the danger was never that `0036` says too little, it
is that `0035` quietly grew to cover a digest it excludes by name.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract


def _repository_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "packages").is_dir() and (parent / "docs").is_dir():
            return parent
    raise AssertionError("repository root not found")


ADR_DIRECTORY = _repository_root() / "docs" / "adr"

#: Located by its number rather than by a filename written here: a filename is a second
#: copy of the same fact, and the two disagree the day one of them is renamed.
ADR_0035 = next(ADR_DIRECTORY.glob("0035-*.md"), None)
ADR_0036 = next(ADR_DIRECTORY.glob("0036-*.md"), None)


def test_both_documents_exist_and_are_readable() -> None:
    """Read this first: a missing file would make every assertion below vacuous."""
    assert ADR_0035 is not None, "ADR 0035 is missing; the finding's authority is unreadable"
    assert ADR_0036 is not None, "ADR 0036 is missing; this feature has no authority at all"
    assert ADR_0035.read_text(encoding="utf-8").strip()
    assert ADR_0036.read_text(encoding="utf-8").strip()


def _text(path: Path | None) -> str:
    assert path is not None
    return path.read_text(encoding="utf-8")


def test_0036_names_an_exception_to_the_requirement_it_supersedes() -> None:
    """It must say WHICH requirement it supersedes. An exception to nothing is not one."""
    text = _text(ADR_0036)
    assert "FR-062" in text, "ADR 0036 names no requirement, so it supersedes nothing"
    assert re.search(r"(?i)supersede", text), "ADR 0036 does not say it supersedes anything"


def test_0036_names_the_two_products_and_they_are_the_ones_this_feature_builds() -> None:
    """`FR-824`. The scope is two named products, and the names are checked against code."""
    from daily_reporting.origination.conditions import Product

    text = _text(ADR_0036).lower()
    for product in Product:
        spelled = product.value.replace("_", " ")
        assert spelled in text, (
            f"{product.value!r} is a product this feature may originate and ADR 0036 does "
            f"not name it; the code claims an authority the record does not grant"
        )


def test_0036_carries_five_conditions_and_the_code_answers_five() -> None:
    """The count is compared against the CODE, never written twice.

    A number in this file would be a second copy of a fact the enum already holds, and the
    two disagree the day a condition is added.
    """
    from daily_reporting.contracts.origination_codes import OriginationReasonCode

    conditions = [
        code
        for code in OriginationReasonCode
        if code is not OriginationReasonCode.ORIGINATION_NOT_NAMED_BY_THE_ADR
    ]
    text = _text(ADR_0036)
    stated = re.search(r"(?i)[-—]\s*(\w+)\s+conditions,\s+all\s+required", text)
    assert stated, "ADR 0036 does not state how many conditions it carries"
    spelled = {"three": 3, "four": 4, "five": 5, "six": 6}
    assert spelled.get(stated.group(1).lower()) == len(conditions), (
        f"the ADR states {stated.group(1)!r} conditions and the code answers "
        f"{len(conditions)}; one of the two was edited without the other"
    )


def test_0035_still_governs_the_prioritisable_finding() -> None:
    """The half that matters. `0035` must still be about the finding, and about that only."""
    text = _text(ADR_0035)
    assert re.search(r"(?i)PRIORITISABLE", text), (
        "ADR 0035 no longer names a prioritisable finding, so what it governs has changed"
    )


def test_0035_still_excludes_a_digest_by_name() -> None:
    """**This is the sentence that sent this feature to its own record.**

    If it ever disappears, `008` would silently fall back under `0035` — and a daily summary
    of twenty KPIs is exactly the digest that sentence excludes.
    """
    text = _text(ADR_0035).lower()
    assert "no digest" in text, (
        "ADR 0035 no longer excludes a digest by name; ADR 0036 exists BECAUSE it does, and "
        "removing that clause changes which record covers this feature"
    )


def test_0036_does_not_amend_or_widen_0035() -> None:
    """Two records, two authorities. A `0036` that edits `0035` would be one record again."""
    text = _text(ADR_0036)
    assert "0035" in text, "ADR 0036 does not mention the record it must not touch"
    assert re.search(r"(?i)not amended|untouched|not.{0,20}touched", text), (
        "ADR 0036 does not state that ADR 0035 stays untouched, which is the whole reason "
        "there are two records instead of one widened one"
    )


def test_the_ledger_does_not_mark_the_adr_as_measured_by_existing() -> None:
    """**`T833` is not marked by this file existing**, and that is stated where it is read.

    An ADR that exists is not an ADR that was measured; a node that exists is not a node
    that was seen to fail. The mark belongs to the cycle that runs the mutations.
    """
    ledger = _repository_root() / "specs" / "008-daily-report-and-rule-alerts" / "tasks.md"
    assert (
        "AN ADR THAT EXISTS IS NOT AN ADR THAT WAS MEASURED"
        in ledger.read_text(encoding="utf-8").upper()
    ), "the ledger no longer carries the sentence this node is named after"
