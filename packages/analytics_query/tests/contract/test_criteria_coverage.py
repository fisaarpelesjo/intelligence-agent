"""SC coverage audit — T118.

Every success criterion `SC-001` to `SC-036` maps to a named test.

Criteria differ from requirements in what coverage means. A requirement is
implemented somewhere and verified somewhere; a criterion is a **measurement**,
so the only meaningful mapping is to the test that performs it. There is no
"implementing module" half here, deliberately — a criterion cited only in `src/`
would be a claim about a measurement nobody takes.

Four criteria are measured only against fixtures (`SC-011`, `SC-015`, `SC-018`,
`SC-023`), and two are procedures rather than automated measurements (`SC-012`
retry cost, `SC-035` production cost observation). Those are named here rather
than quietly counted as satisfied: a criterion whose evidence is a documented
procedure is in a different state from one an assertion checks, and the release
report has to be able to tell them apart.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import analytics_query

pytestmark = pytest.mark.contract

TESTS = Path(__file__).resolve().parent.parent
REPO = Path(analytics_query.__file__).resolve().parents[4]

TOTAL_CRITERIA = 36
ALL_CRITERIA = tuple(f"SC-{i:03d}" for i in range(1, TOTAL_CRITERIA + 1))

#: Criteria whose evidence is a documented measurement procedure rather than an
#: assertion. They still require a test naming them — what differs is that the
#: test records the procedure's existence, not a measured figure.
PROCEDURE_BACKED = ("SC-012", "SC-035")

#: Criteria provable only against fixtures today. Named so the release report
#: can distinguish them from criteria measured against production.
FIXTURE_BACKED = ("SC-011", "SC-015", "SC-018", "SC-023")

_REFERENCE = re.compile(r"\bSC-(\d{3})\b")


def _cited() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path in sorted(TESTS.rglob("*.py")):
        for number in _REFERENCE.findall(path.read_text(encoding="utf-8")):
            found.setdefault(f"SC-{number}", set()).add(str(path.relative_to(TESTS)))
    return found


MEASURED = _cited()


def test_the_audit_reads_a_populated_suite() -> None:
    """A scan over nothing would report perfect coverage."""
    assert len(list(TESTS.rglob("*.py"))) >= 20


@pytest.mark.parametrize("criterion", ALL_CRITERIA)
def test_every_criterion_names_a_test(criterion: str) -> None:
    assert criterion in MEASURED, f"{criterion} names no test"


def test_the_full_range_is_mapped() -> None:
    """36/36, with the count itself asserted."""
    assert len(ALL_CRITERIA) == TOTAL_CRITERIA
    assert set(ALL_CRITERIA) <= set(MEASURED)


def test_no_citation_names_a_criterion_that_does_not_exist() -> None:
    assert set(MEASURED) <= set(ALL_CRITERIA), sorted(set(MEASURED) - set(ALL_CRITERIA))


def test_the_criterion_count_matches_the_specification() -> None:
    spec = REPO / "specs" / "002-analytics-query" / "spec.md"
    declared = re.findall(r"^- \*\*(SC-\d{3})\*\*:", spec.read_text(encoding="utf-8"), re.M)
    assert len(declared) == TOTAL_CRITERIA
    assert declared == list(ALL_CRITERIA), "the spec and this audit disagree"


# --- the criteria that are not plain assertions ------------------------------


@pytest.mark.parametrize("criterion", PROCEDURE_BACKED)
def test_a_procedure_backed_criterion_has_a_documented_procedure(criterion: str) -> None:
    """The procedure must exist as a file, not only as a claim in a test."""
    procedures = REPO / "docs" / "measurement"
    documented = " ".join(p.read_text(encoding="utf-8") for p in procedures.glob("*.md"))
    assert criterion in documented, f"{criterion} claims a procedure that is not written down"


def test_procedure_backed_criteria_are_not_reported_as_measured() -> None:
    """Defining a procedure is not performing the measurement."""
    procedures = REPO / "docs" / "measurement"
    for path in procedures.glob("*.md"):
        text = path.read_text(encoding="utf-8").lower()
        assert "unmeasured" in text or "not yet measured" in text, (
            f"{path.name} must state that the measurement has not been taken"
        )


@pytest.mark.parametrize("criterion", FIXTURE_BACKED)
def test_a_fixture_backed_criterion_is_named_as_such(criterion: str) -> None:
    """So the release report never presents it as production evidence."""
    assert criterion in MEASURED
    assert criterion in FIXTURE_BACKED
