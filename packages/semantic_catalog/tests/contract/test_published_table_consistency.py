"""The published §4.4 table and the executable map must be identical — T021.

`catalog-file-contracts.md §4.4` declares itself the authoritative classification.
`contracts/classification.py` is what the semantic fingerprint actually reads. If
the two disagree, the governance document describes a rule the code is not
applying, and the gate protecting SC-021 is protecting a different set of fields
than the one anybody approved.

This test parses the Markdown and compares it with the map in four directions —
missing, stale, duplicated, differently classified — so the disagreement cannot
survive a build.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from semantic_catalog.contracts.classification import (
    CLASSIFICATION,
    FINGERPRINT_INPUTS,
    FieldClass,
    is_fingerprinted,
)

pytestmark = pytest.mark.contract

CONTRACT_DOC = (
    Path(__file__).resolve().parents[4]
    / "specs"
    / "001-semantic-catalog"
    / "contracts"
    / "catalog-file-contracts.md"
)

_LABEL_TO_CLASS = {
    "Stable Identity": FieldClass.STABLE_IDENTITY,
    "Semantic": FieldClass.SEMANTIC,
    "Descriptive": FieldClass.DESCRIPTIVE,
    "Availability": FieldClass.AVAILABILITY,
    "Lifecycle": FieldClass.LIFECYCLE,
    "Governance": FieldClass.GOVERNANCE,
}

_ROW = re.compile(
    r"^\|\s*`(?P<path>[A-Za-z_]+\.[A-Za-z_]+)`\s*\|\s*(?P<label>[A-Za-z ]+?)\s*\|"
    r"\s*(?P<fingerprint>\*\*yes\*\*|no)\s*\|$"
)


def _published_rows() -> list[tuple[str, str, str]]:
    """Rows of the Complete classification section, in document order."""
    text = CONTRACT_DOC.read_text(encoding="utf-8")
    start = text.index("#### Complete classification")
    end = text.index("#### What each class triggers")
    rows: list[tuple[str, str, str]] = []
    for line in text[start:end].splitlines():
        match = _ROW.match(line.strip())
        if match:
            rows.append((match["path"], match["label"], match["fingerprint"]))
    return rows


@pytest.fixture(scope="module")
def published() -> dict[str, FieldClass]:
    rows = _published_rows()
    assert rows, f"no classification rows parsed from {CONTRACT_DOC.name}"
    return {path: _LABEL_TO_CLASS[label] for path, label, _ in rows}


def test_contract_document_is_present() -> None:
    assert CONTRACT_DOC.is_file(), CONTRACT_DOC


def test_published_table_has_no_duplicate_rows() -> None:
    paths = [path for path, _, _ in _published_rows()]
    duplicates = sorted({p for p in paths if paths.count(p) > 1})
    assert not duplicates, f"§4.4 lists these fields more than once: {duplicates}"


def test_published_table_uses_only_the_six_approved_classes() -> None:
    labels = {label for _, label, _ in _published_rows()}
    assert labels <= set(_LABEL_TO_CLASS), f"unknown class labels in §4.4: {sorted(labels)}"


def test_published_table_matches_executable_map(published: dict[str, FieldClass]) -> None:
    """The single consistency gate: four failure directions, one assertion each."""
    missing = sorted(set(CLASSIFICATION) - set(published))
    stale = sorted(set(published) - set(CLASSIFICATION))
    differing = sorted(
        f"{path}: doc={published[path].value} map={CLASSIFICATION[path].value}"
        for path in set(published) & set(CLASSIFICATION)
        if published[path] is not CLASSIFICATION[path]
    )

    assert not missing, f"classified in code but absent from §4.4: {missing}"
    assert not stale, f"listed in §4.4 but not a model field: {stale}"
    assert not differing, f"classified differently in §4.4 and in code: {differing}"
    assert len(published) == len(CLASSIFICATION)


def test_published_fingerprint_column_matches_the_closure_rule(
    published: dict[str, FieldClass],
) -> None:
    """The Fingerprinted column is derived, so it cannot drift independently."""
    mismatched = sorted(
        f"{path}: doc={'yes' if fp == '**yes**' else 'no'} map={is_fingerprinted(path)}"
        for path, _, fp in _published_rows()
        if (fp == "**yes**") is not is_fingerprinted(path)
    )
    assert not mismatched, f"Fingerprinted column disagrees with the closure rule: {mismatched}"
    _ = published


def test_published_table_declares_the_expected_field_count() -> None:
    """The prose count and the row count must agree."""
    text = CONTRACT_DOC.read_text(encoding="utf-8")
    declared = re.search(r"One row per authored field, \*\*?(\d+)", text) or re.search(
        r"One row per authored field, (\d+) in total", text
    )
    assert declared, "§4.4 does not state how many rows it contains"
    assert int(declared.group(1)) == len(CLASSIFICATION)


def test_fingerprint_set_unchanged_by_the_documentation_correction() -> None:
    """Regression guard: documenting fields must not widen the fingerprint.

    **RE-DERIVED on 2026-08-30, not deleted.** It asserted ``len(FINGERPRINT_INPUTS) == 29``,
    and 29 was the weak half all along: `FR-806` added `MetricVersion.value_column` and
    `MetricVersion.kpi_name`, both semantic, and the count moved to 31. A number written here
    has to be edited every time a field is classified, and **a check that needs editing to
    stay green is a check that stopped measuring**.

    The property never moved and it is the line below: the fingerprint is EXACTLY the
    semantic fields plus the three as-of fields. Documenting a field does not widen it;
    classifying one as semantic does, which is the whole point of classifying.
    """
    assert FINGERPRINT_INPUTS, "the fingerprint is empty; it would agree with anything"
    semantic = {p for p, c in CLASSIFICATION.items() if c is FieldClass.SEMANTIC}
    as_of = {
        "MetricVersion.version",
        "MetricVersion.effective_from",
        "MetricVersion.effective_to",
    }
    assert semantic | as_of == FINGERPRINT_INPUTS
