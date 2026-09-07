"""FR coverage audit — T117.

Every requirement `FR-001` to `FR-078` maps to at least one implemented module
**and** at least one test. An unmapped requirement fails CI.

Both halves are needed and they catch different things. A requirement cited only
in `src/` is implemented and unverified. A requirement cited only in `tests/` is
verified against something nobody wrote down as its owner, so the next person to
refactor has no way to know what they are touching.

The audit reads **the code**, not `tasks.md`. Deriving coverage from the task
list would be circular: the task list is a plan, and a plan claiming coverage is
exactly what this is meant to check. Citations live in module and test
docstrings, which is where someone tracing a requirement actually looks.

It deliberately does not check *quality* of coverage. A citation asserts that a
file claims responsibility for a requirement; whether the assertions inside it
are good is a reviewer's judgement, and automation claiming otherwise would be
the same overreach `FR-059` forbids for pt-BR wording.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import analytics_query

pytestmark = pytest.mark.contract

SRC = Path(analytics_query.__file__).parent
TESTS = Path(__file__).resolve().parent.parent

TOTAL_REQUIREMENTS = 78
ALL_REQUIREMENTS = tuple(f"FR-{i:03d}" for i in range(1, TOTAL_REQUIREMENTS + 1))

_REFERENCE = re.compile(r"\bFR-(\d{3})\b")


def _cited_in(root: Path) -> dict[str, set[str]]:
    """Map each requirement to the files claiming it."""
    found: dict[str, set[str]] = {}
    for path in sorted(root.rglob("*.py")):
        for number in _REFERENCE.findall(path.read_text(encoding="utf-8")):
            found.setdefault(f"FR-{number}", set()).add(str(path.relative_to(root)))
    return found


IMPLEMENTED = _cited_in(SRC)
VERIFIED = _cited_in(TESTS)


def test_the_audit_reads_a_populated_tree() -> None:
    """A scan over nothing would report perfect coverage."""
    assert len(list(SRC.rglob("*.py"))) >= 25
    assert len(list(TESTS.rglob("*.py"))) >= 20


@pytest.mark.parametrize("requirement", ALL_REQUIREMENTS)
def test_every_requirement_names_an_implementing_module(requirement: str) -> None:
    assert requirement in IMPLEMENTED, f"{requirement} names no module under src/"


@pytest.mark.parametrize("requirement", ALL_REQUIREMENTS)
def test_every_requirement_names_a_verifying_test(requirement: str) -> None:
    assert requirement in VERIFIED, f"{requirement} names no test"


def test_the_full_range_is_mapped() -> None:
    """78/78, stated as a total so the count itself is asserted."""
    assert len(ALL_REQUIREMENTS) == TOTAL_REQUIREMENTS
    assert set(ALL_REQUIREMENTS) <= set(IMPLEMENTED)
    assert set(ALL_REQUIREMENTS) <= set(VERIFIED)


def test_no_citation_names_a_requirement_that_does_not_exist() -> None:
    """A stale reference is as misleading as a missing one."""
    cited = set(IMPLEMENTED) | set(VERIFIED)
    assert cited <= set(ALL_REQUIREMENTS), sorted(cited - set(ALL_REQUIREMENTS))


def test_the_requirement_count_matches_the_specification() -> None:
    """Adding an FR to the spec fails here until it is implemented and tested."""
    spec = (
        Path(analytics_query.__file__).resolve().parents[4]
        / "specs"
        / "002-analytics-query"
        / "spec.md"
    )
    declared = re.findall(r"^- \*\*(FR-\d{3})\*\*:", spec.read_text(encoding="utf-8"), re.M)
    assert len(declared) == TOTAL_REQUIREMENTS
    assert declared == list(ALL_REQUIREMENTS), "the spec and this audit disagree"
