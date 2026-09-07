"""The ledger's prose may not carry a task count — `F-I`, and it is the fourth of its kind today.

**The defect has one shape and this repository keeps meeting it:** a number measured
correctly, written into prose, and then left behind while the thing it counted moved.
This file's own ledger did it three times in one paragraph set — *"31 of 33"*, *"eleven
of the twenty-three"*, and *"the twelve that remain … none is marked"* — the last of
which named `T007`, `T008` and `T009` as unmarked on a day all three were done.

**The remedy is not a better number. It is not writing one.** The checkboxes are the
ledger; a count beside them is a second declaration of the same fact, and two
declarations of one fact drift. So this node refuses a hand-written task count in the
prose, and refuses a `[BLOCKED-EXTERNAL]` marker, which the ledger claims about itself
and which nothing was checking.

## What it deliberately does NOT do

It does not require the file to be countless. Counts of things that are **not tasks** —
`13 FR`, `9 SC`, the four owner decisions, `129` reason codes — are measurements of
other artefacts, they do not move when a checkbox flips, and forbidding them would be
this node inventing a rule wider than the defect.

The scan is therefore narrow on purpose: a number **adjacent to a word for tasks**, in
prose, outside a task line. A wider rule would be enforced by deletion, which is how a
gate teaches people to route around it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

#: `tests/contract/` -> `tests/` -> package -> `packages/` -> repository.
REPO = Path(__file__).resolve().parents[4]
LEDGER = REPO / "specs" / "006-insights-and-prioritisation" / "tasks.md"

#: Number words as well as digits: *"eleven of the twenty-three"* carried the defect
#: without a single digit in it.
NUMBER = (
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"twenty-one|twenty-two|twenty-three)"
)

#: The SHAPES that actually aged, written out rather than a wide rule.
#:
#: A wide rule -- "any number near the word task" -- catches *"not one task below may
#: begin"*, *"a Phase 1 task"* and *"no task promised"*, which are QUANTIFIERS and do not
#: move when a checkbox flips. A gate that fails on those is a gate people delete.
#:
#: So each alternative below is a shape this ledger actually carried and that actually
#: went false:
#:
#: * ``31 of 33`` and ``eleven of the twenty-three`` -- a fraction of a ledger;
#: * ``the twelve that remain`` -- a count of what is left;
#: * ``eleven tasks are done`` -- a count with the noun attached.
#:
#: Three exclusions, each because the phrase is a QUANTIFIER or counts another artefact:
#: ``item 7 of nine`` counts the owner's roadmap; ``not one of the twenty-six`` counts
#: `001`'s contract fields. Neither moves when a checkbox flips, and failing on them
#: would be this node reaching past the defect it was written for.
TASK_COUNT = re.compile(
    rf"(?<!item )(?<!not )(?<!no )\b{NUMBER}\s+of\s+(?:the\s+)?{NUMBER}\b"
    rf"|\b{NUMBER}\s+that\s+remain\b"
    rf"|\b{NUMBER}\s+tasks?\s+(?:are|is|remain)\b",
    re.IGNORECASE,
)


def _prose_lines() -> list[tuple[int, str]]:
    """Every line that is not a task line and not a table row.

    A task line is the ledger itself and legitimately carries an identifier; a table
    row is a structured claim with its own column. The prose is what rots.
    """
    lines = LEDGER.read_text(encoding="utf-8").splitlines()
    return [
        (number, line)
        for number, line in enumerate(lines, start=1)
        if not line.lstrip().startswith(("- [", "|"))
    ]


def test_the_ledger_exists_and_has_prose_to_scan() -> None:
    """**Read this before believing the node below.**

    A missing file or an all-table document would make the scan vacuous — the failure
    mode that produced `F-G` on the other branch, where a check ran against a directory
    that did not exist and its empty answer was reported as a proof.
    """
    assert LEDGER.is_file(), LEDGER
    prose = _prose_lines()
    assert len(prose) > 50, f"only {len(prose)} prose lines; the scan would prove little"
    assert any("[X]" in line for line in LEDGER.read_text(encoding="utf-8").splitlines()), (
        "the ledger has no marked task, so there is nothing a count could be wrong about"
    )


def test_the_ledger_carries_no_blocked_external_and_no_hand_written_count() -> None:
    """The two claims the ledger makes about itself, made checkable.

    `[BLOCKED-EXTERNAL]` marks a dependency **record** rather than work, and the ledger
    says none of its tasks is one. That was prose. It is now read from the file.

    And the count: the checkboxes are the ledger. A number beside them is a second
    declaration of the same fact, and two declarations of one fact drift.
    """
    text = LEDGER.read_text(encoding="utf-8")

    marked = [
        line
        for line in text.splitlines()
        if line.lstrip().startswith("- [") and "BLOCKED-EXTERNAL" in line
    ]
    assert not marked, f"a task is marked BLOCKED-EXTERNAL: {marked}"

    offenders = [
        f"{number}: {line.strip()}" for number, line in _prose_lines() if TASK_COUNT.search(line)
    ]
    assert not offenders, (
        "the ledger's prose counts tasks, which is the F136 defect this node exists for -- "
        f"state the property and let the checkboxes answer the number: {offenders}"
    )
