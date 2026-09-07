"""Pre-change baselines for the ADR 0010 entry point — 003:T001.

The invariant this phase must preserve is **node-ID preservation, not count
equality**. A suite can delete one test and add another and keep the same total,
so a count is evidence of nothing. What must hold is that every pytest node that
existed before the composed entry point was added still exists and still passes.

Counts are recorded here as context — `semantic_catalog` and `analytics_query`
stood at 1415 and 1715 when ADR 0010 was written — and are deliberately **not**
asserted. Additive tests are expected to raise both totals; this phase adds
several itself.

The captured node-ID sets live beside this module so the regression gates
(003:T010, 003:T011) can compare against them without re-deriving a baseline
from a tree that has already changed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

REPO = Path(__file__).resolve().parents[4]
BASELINE = Path(__file__).resolve().parent / "adr0010_baseline.json"

#: Informational only. Never asserted — see the module docstring.
RECORDED_COUNTS = {"semantic_catalog": 1415, "analytics_query": 1715}


def load_baseline() -> dict[str, list[str]]:
    """The captured node-ID sets, keyed by package."""
    return json.loads(BASELINE.read_text(encoding="utf-8"))["node_ids"]


def test_the_baseline_was_captured_before_the_entry_point_landed() -> None:
    """A baseline derived after the change would prove nothing."""
    assert BASELINE.is_file(), "the node-ID baseline must be captured and committed"
    payload = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert payload["captured_before"] == "packages/analytics_query/src/analytics_query/execute.py"
    assert set(payload["node_ids"]) == {"semantic_catalog", "analytics_query"}


def test_the_baseline_records_counts_as_context_and_asserts_none() -> None:
    """The counts are here to be read, not to gate.

    If a future edit turns either figure into an assertion, this fails: a count
    gate cannot distinguish a deleted test from an added one.
    """
    # THE PRESENCE CHECK READS THE MODULE NAMESPACE, NOT THE MODULE TEXT -- ADR 0034.
    #
    # It used to be ``assert "RECORDED_COUNTS" in body`` over this file's own source, and
    # `body` includes the assertion line, so the only occurrence the check needed was the
    # one the assertion itself writes. Measured on 2026-08-27: renaming the constant to
    # `COUNTS_FOR_READING` removed it from the module and this still reported 3 passed.
    # A guard whose subject includes the guard cannot fail.
    assert "RECORDED_COUNTS" in globals(), (
        "the constant this node exists to watch is gone from the module, so the checks "
        "below are watching nothing"
    )
    source = Path(__file__).read_text(encoding="utf-8")
    body = source.split('"""', 2)[2]
    for count in ("1415", "1715"):
        # These stay text checks and stay honest: they assert an ABSENCE, so an occurrence
        # written by the assertion would make them fail loudly rather than pass quietly.
        assert f"assert {count}" not in body
        assert f"== {count}" not in body


def test_every_captured_node_is_uniquely_named() -> None:
    """A duplicated node id would let a lost test hide behind its twin."""
    for package, nodes in load_baseline().items():
        assert len(nodes) == len(set(nodes)), f"{package} baseline contains duplicates"
        assert nodes, f"{package} baseline is empty"
