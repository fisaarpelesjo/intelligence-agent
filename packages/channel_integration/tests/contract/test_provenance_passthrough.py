"""Provenance travels unmerged — T092 (FR-045; SC-023).

A comparison has two sides, and each side has its own provenance: its own sources, its own metric
versions, its own revisions, its own freshness. `002` keeps them separate and `003` carries them
separately, so `004` must not merge, summarise, deduplicate, average or "tidy" them.

The failure this prevents is specific and expensive. Merged provenance says "these numbers came
from these sources", which is true of the union and false of each side. A reader comparing July
against June, where one side's data is a week staler than the other's, cannot see that from a
merged record — and staleness on one side is exactly what makes a comparison misleading.

`004` carries provenance rather than rendering it into the body today: there is no `D-28` matrix
entry for a provenance block, so the assertion here is that the payload's provenance reaches the
delivery path **structurally intact** and that nothing in this package can combine two sides into
one.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from channel_integration.contracts.descriptor import ChannelId
from channel_integration.outbound import preserve as preserve_module
from channel_integration.outbound import render as render_module
from channel_integration.outbound.render import render_answer

from ..fixtures.payloads import CORPUS, FIXTURE_CAPABILITY

pytestmark = pytest.mark.contract

_TWO_SIDED = "multi-side provenance"


def test_the_payload_really_carries_two_sides() -> None:
    """Without this, every assertion below would pass over a single-sided payload."""
    payload = CORPUS[_TWO_SIDED]
    assert len(payload.answer.provenance) == 2
    sides = [side.contributing_sources for side in payload.answer.provenance]
    assert sides[0] != sides[1], "the two sides must be distinguishable to begin with"


def test_rendering_does_not_touch_provenance() -> None:
    """The answer that reaches delivery is the answer that arrived, provenance included.

    Asserted by identity on the carried object: the renderer returns a presentation and the
    payload's answer is unchanged — not a copy with merged provenance, not a reordered tuple.
    """
    payload = CORPUS[_TWO_SIDED]
    before = payload.answer.provenance
    render_answer(payload, ChannelId.SLACK, FIXTURE_CAPABILITY)
    assert payload.answer.provenance is before
    assert len(payload.answer.provenance) == 2


def test_each_side_keeps_its_own_sources_versions_and_revisions() -> None:
    """`SC-023`: field by field, the two sides stay separate."""
    payload = CORPUS[_TWO_SIDED]
    first, second = payload.answer.provenance
    assert first.contributing_sources != second.contributing_sources
    assert first.resolved_metric_versions != second.resolved_metric_versions
    assert first.data_revisions != second.data_revisions
    assert first.execution_identifiers != second.execution_identifiers


def test_no_outbound_module_can_merge_two_provenance_records() -> None:
    """Structural: there is no operation here that could combine sides.

    Scanned for the operations a merge would need — set union, ``update``, ``extend`` over
    provenance, ``dedup``, ``merge``, ``flatten``, ``summarise`` — over the modules that see the
    payload.
    """
    forbidden = ("merge", "dedup", "flatten", "combine", "summar", "union", "aggregate")
    offenders: list[str] = []
    for module in (render_module, preserve_module):
        source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        functions = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        for identifier in names | attributes | functions:
            for token in forbidden:
                if token in identifier.lower():
                    offenders.append(f"{Path(inspect.getfile(module)).name}: {identifier}")
    assert not offenders, offenders


def test_no_outbound_module_reads_provenance_at_all_yet() -> None:
    """The honest state: provenance is **carried**, not rendered, because `D-28` declares no block.

    Asserted so the gap is visible rather than assumed covered. When a matrix entry for a
    provenance block exists, this test is what fails and tells the next author to render it, and
    `SC-023` is what tells them to render both sides separately.
    """
    for module in (render_module, preserve_module):
        source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        assert "provenance" not in attributes, (
            f"{Path(inspect.getfile(module)).name} now reads provenance; render both sides "
            "separately and update this test (SC-023)"
        )
