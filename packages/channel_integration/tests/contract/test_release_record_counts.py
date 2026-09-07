"""The release record's ledger count is derived from the ledger, or it fails (review finding F13).

`docs/release/multichannel-internal-validation.md` § 8.6 declares how many executable tasks of
`004` are complete. That line was wrong the day it was written: § 8 was authored, then the same
delivery marked `T108` and `T117`, and the record was left declaring the state **prior to its own
marking**.

## Why a one-line correction was not the whole fix

F13 was the **fourth** occurrence of one defect family in this review loop:

* a comment ordinal that said "fourth set" when it was the fifth (F1);
* a docstring count that said three upstream paths when the allowlist held nine (F5);
* a test **name** asserting a positional reading the test did not measure (F8);
* and this: a count in a release record whose entire purpose is to declare measured state.

The first three were each fixed by editing prose, and each recurred somewhere else. F5 was the one
that broke the cycle, by binding the prose to `len(AUTHORIZED)` — and that node then caught real
drift five cycles later, when the allowlist grew from nine paths to thirteen. This file does the
same thing for the release record.

## What is asserted

Three claims, and the third is the one that stops the obvious workaround:

* the record **states** a ledger count in the anchored form;
* that count **equals** the number of `- [x]` rows in
  `specs/004-multichannel-integration/tasks.md`;
* **removing the claim fails too.** Deleting the sentence rather than correcting it is otherwise
  the cheapest way to make this node green, and it would take the record back to declaring nothing.

## What is deliberately not asserted

Not the ledger total. `156` is the count of *executable* tasks and it moves when the ledger gains or
loses one, which is a governed change with its own authorization — pinning it here would make this
node fail for a reason it is not competent to judge. Only the completed count is bound, because that
is the number that goes stale silently as work lands.

## The external-record count, added 2026-08-19 (review finding F15)

The family recurred a **fifth** time, and worse than the four before it: both release records
declared "**twenty-two** external records — eleven of this feature's own, twelve inherited", which
contradicts itself on its own line. Eleven plus twelve is twenty-three, and parsing the four
readiness documents gives 4 + 4 + 4 + 11 = 23.

So the same treatment is applied a second time. The records' external-record count is now derived
from the documents themselves: every capability entry across `docs/readiness/*.yaml`, counted, and
compared against the number each record spells out in words. Both records are held, because F15 was
present in both and a gate covering one of them would have caught half of it.

The count is matched **as an English word**, because that is how the records write it. A numeral
would have been easier to parse and is not what the prose says, and a gate that only reads a form
the document does not use is a gate that reads nothing.
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


_ROOT = _repository_root()
_RECORD = _ROOT / "docs" / "release" / "multichannel-internal-validation.md"
_LEDGER = _ROOT / "specs" / "004-multichannel-integration" / "tasks.md"

#: The claim, anchored on the words around it. Every gap is a whitespace class rather than a literal
#: space: the record is wrapped prose, so any of these words can end a line, and a formatter
#: re-wrapping the paragraph must not turn a correct count into a missing claim. That failure is not
#: hypothetical — the F5 node's first pattern used literal spaces and broke exactly that way.
_CLAIM = re.compile(r"ledger,\s+feature\s+`004`:\s+\*\*(?P<complete>\d+)\s+of\s+(?P<total>\d+)\*\*")

#: A completed task row. The state character is matched case-insensitively because the ledger uses
#: both `x` and `X`, and counting only one would silently undercount.
_COMPLETE_ROW = re.compile(r"^- \[[xX]\] ", re.M)

_READINESS = _ROOT / "docs" / "readiness"
_RELEASE_STATE = _ROOT / "docs" / "release" / "multichannel-release-state.md"

#: One external capability record. **Two spellings, and both are needed**: `001`'s document keys its
#: entries `- capability:` while the other three key them `- id:`. Measured 2026-08-19 — a pattern
#: matching only `- id:` reads `001` as holding zero records and makes the total four short,
#: which is
#: how a count that looks derived can still be wrong.
_RECORD_ENTRY = re.compile(r"^\s*- (?:id|capability): ", re.M)

#: The **total open** external-record claim, in the two phrasings the two records actually use.
#:
#: Anchored on "stay open" and "records open:" rather than on the words "external
#: records" alone, and that narrowing is the whole difficulty of this gate. Both
#: documents also make *feature-scoped* claims about this feature's own eleven, and both
#: of those are **correct**. The first pattern written here matched them too and reported
#: the validation record as claiming eleven, which is a gate failing a document for
#: saying something true.
#:
#: So only the total is bound. A feature-scoped count is a different claim about a different set and
#: this node is not competent to judge it.
#:
#: Emphasis is optional because the records differ: § 9.6 writes `**twenty-three**` and
#: the sentence at the top of the same document writes it plain. Requiring the asterisks
#: would have read one occurrence and left the other unchecked — which is exactly how
#: F15 survived in two places at once.
_EXTERNAL_CLAIMS = (
    re.compile(r"(?P<count>[a-z-]+)\*{0,2}\s+external\s+records\s+stay\s+open"),
    re.compile(r"external\s+records\s+open:\s+\*{0,2}(?P<count>[a-z-]+)"),
)


def stated_external_counts(text: str) -> list[str]:
    """Every total-open external-record count ``text`` states, in either phrasing."""
    found: list[str] = []
    for pattern in _EXTERNAL_CLAIMS:
        found.extend(match.group("count").strip("*") for match in pattern.finditer(text))
    return found


#: English number words, only as far as this count could plausibly reach. A mapping rather than a
#: parser: the point is to read what the document says, and a document saying something outside this
#: range is a document that needs a human to look at it.
_NUMBER_WORDS: dict[str, int] = {
    "nineteen": 19,
    "twenty": 20,
    "twenty-one": 21,
    "twenty-two": 22,
    "twenty-three": 23,
    "twenty-four": 24,
    "twenty-five": 25,
    "twenty-six": 26,
    "twenty-seven": 27,  # +d_10 (OD-103, ciclo 537)
}


def declared_external_records() -> int:
    """How many external capability records the four readiness documents declare."""
    documents = sorted(_READINESS.glob("*.yaml"))
    assert documents, f"{_READINESS} holds no readiness document, so nothing below is derived"
    return sum(
        len(_RECORD_ENTRY.findall(document.read_text(encoding="utf-8"))) for document in documents
    )


def _record_text() -> str:
    assert _RECORD.is_file(), f"{_RECORD} is missing, so nothing below can be checked"
    return _RECORD.read_text(encoding="utf-8")


def _ledger_text() -> str:
    assert _LEDGER.is_file(), f"{_LEDGER} is missing, so the comparison has no source of truth"
    return _LEDGER.read_text(encoding="utf-8")


def completed_in_ledger() -> int:
    """How many executable tasks the ledger marks complete. The source of truth."""
    return len(_COMPLETE_ROW.findall(_ledger_text()))


def claimed_in_record() -> re.Match[str] | None:
    """The record's own claim, or ``None`` when it no longer makes one."""
    return _CLAIM.search(_record_text())


def test_the_record_still_states_a_ledger_count() -> None:
    """Deleting the claim is not a way to pass this file.

    Asserted before the equality below, and separately from it, because the two fail for different
    reasons and a reader needs to know which happened: a record that stopped declaring is a
    different problem from a record declaring the wrong thing.
    """
    assert claimed_in_record() is not None, (
        "the release record no longer states its ledger count in the asserted form "
        '("ledger, feature `004`: **N of M** executable tasks"). Restate it rather than removing '
        "it — an unstated count is how this line went stale in the first place"
    )


def test_the_records_ledger_count_matches_the_ledger() -> None:
    """The claim equals the count, or the record is describing a state that has moved on."""
    claim = claimed_in_record()
    assert claim is not None, "no claim to compare; see the node above"

    stated = int(claim.group("complete"))
    measured = completed_in_ledger()

    assert stated == measured, (
        f"the release record declares {stated} completed executable tasks and "
        f"`{_LEDGER.name}` marks {measured}. The ledger is the source of truth and the record "
        "is the copy — update the record. This is the defect F13 recorded: § 8 was written, "
        "the same delivery then marked two tasks, and the record was left declaring the state "
        "before its own marking"
    )


def test_the_comparison_is_not_vacuous() -> None:
    """Both sides are non-empty and plausible, so an equality of zeros cannot pass.

    A ledger that matched nothing would make `completed_in_ledger` return `0`, and a record
    claiming `0` would satisfy the equality while proving that neither pattern works.
    """
    measured = completed_in_ledger()
    assert measured > 0, (
        f"no completed task row matched in {_LEDGER.name}, so the equality above would compare two "
        "zeros and prove nothing about either file"
    )

    claim = claimed_in_record()
    assert claim is not None
    total = int(claim.group("total"))
    assert 0 < measured <= total, (
        f"{measured} completed against a declared total of {total}: the counts are not coherent, "
        "so one of the two patterns is matching something it should not"
    )


def test_the_readiness_documents_are_read_in_both_of_their_two_spellings() -> None:
    """The derivation is held to reading every document, not most of them.

    `001` keys its entries `- capability:` and the other three key them `- id:`. A pattern matching
    one spelling silently reads the other document as empty, and a total that is four short still
    looks derived. So every document is required to contribute at least one record.
    """
    for document in sorted(_READINESS.glob("*.yaml")):
        found = len(_RECORD_ENTRY.findall(document.read_text(encoding="utf-8")))
        assert found > 0, (
            f"{document.name} contributes zero records, so either it changed its key spelling or "
            "the pattern above stopped reading it — either way the total below is short"
        )

    assert declared_external_records() > 0


@pytest.mark.parametrize("record", [_RECORD, _RELEASE_STATE], ids=["validation", "release-state"])
def test_each_record_states_the_external_count_it_is_held_to(record: Path) -> None:
    """Deleting the sentence is not a way to pass, exactly as with the ledger claim above."""
    assert record.is_file(), f"{record} is missing, so nothing below can be checked"
    assert stated_external_counts(record.read_text(encoding="utf-8")), (
        f"{record.name} no longer states its external-record count in the asserted form. Restate "
        "it rather than removing it — an unstated count is how F15 survived two documents"
    )


@pytest.mark.parametrize("record", [_RECORD, _RELEASE_STATE], ids=["validation", "release-state"])
def test_the_external_count_each_record_states_is_the_one_the_documents_declare(
    record: Path,
) -> None:
    """`F15`: eleven plus twelve is twenty-three, and both records said twenty-two.

    Every occurrence in the document is checked rather than the first, because the validation record
    states its count twice and a gate reading one of them would have caught half of F15.
    """
    measured = declared_external_records()
    text = record.read_text(encoding="utf-8")

    stated = stated_external_counts(text)
    assert stated, f"{record.name} states no external count; see the node above"

    for word in stated:
        assert word in _NUMBER_WORDS, (
            f"{record.name} states {word!r} external records, which is outside the range this gate "
            "can read. Either the number moved a long way or the prose changed shape"
        )
        assert _NUMBER_WORDS[word] == measured, (
            f"{record.name} declares {word} ({_NUMBER_WORDS[word]}) external records and the four "
            f"readiness documents declare {measured}. The documents are the source of truth and "
            "the record is the copy — this is F15, the fifth occurrence of a hand-written count "
            "with nothing asserting it"
        )


def test_the_external_count_gate_is_not_vacuous() -> None:
    """The word mapping and the entry pattern must both be able to disagree with a document.

    Without this, a `_NUMBER_WORDS` that mapped everything to the measured value, or an entry
    pattern that matched nothing, would make the nodes above pass over anything at all.
    """
    measured = declared_external_records()
    assert measured >= 19, f"the readiness documents declare only {measured} records"

    wrong = [word for word, value in _NUMBER_WORDS.items() if value != measured]
    assert wrong, "every word maps to the measured count, so the comparison cannot fail"

    assert stated_external_counts("all **twenty-two** external records stay open") == ["twenty-two"]
    assert stated_external_counts("all twenty-two external records stay open") == ["twenty-two"], (
        "the plain-prose form is not read, so one of the two occurrences in the validation record "
        "would go unchecked — which is how F15 survived in two places at once"
    )
    assert stated_external_counts("* external records open: **twenty-two** — eleven of") == [
        "twenty-two"
    ]

    # The narrowing that matters: a feature-scoped count is a different, correct claim.
    assert (
        stated_external_counts("All **eleven** external records `D-22` stand undeclared") == []
    ), (
        "the pattern reads a feature-scoped count as the total, so it would fail a document for "
        "stating something true"
    )
    assert stated_external_counts("because eleven external records are undeclared") == []
