"""Degradation membership and disclosure — T094 (ADR 0022; FR-051, FR-110; SC-021).

Two rules, and the second is what stops the first from being cosmetic:

* every degradation applied must be a **member of the capability matrix**;
* every degradation applied must be **disclosed**, using the matrix's own pt-BR wording.

An invented degradation refuses. A matrix-declared degradation with no disclosure wording also
refuses — applying it would be a silent structural change, and `FR-051` treats silence as the defect
rather than the adaptation.

**Structural only.** Shortening, summarising, rewording, rounding, rescaling, re-unitising,
localising, translating, eliding, omitting, sampling and trimming are content changes and are not
degradations at all. There is no operation in `outbound.degrade` that could perform one, and the
absence is asserted rather than described.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from channel_integration.outbound import degrade as degrade_module
from channel_integration.outbound.degrade import (
    FORBIDDEN_CONTENT_OPERATIONS,
    declared_degradations,
    disclosure_for,
    require_declared_degradation,
)
from channel_integration.outbound.withhold import NotRepresentable

from ..fixtures.payloads import FIXTURE_CAPABILITY

pytestmark = pytest.mark.unit

_DECLARED = ("table-as-list", "emphasis-dropped")


def test_the_fixture_matrix_declares_the_degradations_this_file_uses() -> None:
    """Without this, every assertion below could pass over an empty declaration."""
    assert declared_degradations(FIXTURE_CAPABILITY) == _DECLARED


@pytest.mark.parametrize("name", _DECLARED)
def test_a_declared_degradation_resolves_and_carries_its_disclosure(name: str) -> None:
    degradation = require_declared_degradation(FIXTURE_CAPABILITY, name, "fixture-capability-1")
    assert degradation.capability_ref == "fixture-capability-1"
    assert degradation.disclosure_code == disclosure_for(FIXTURE_CAPABILITY, name)
    assert degradation.disclosure_code.strip()


@pytest.mark.parametrize(
    "invented",
    ["shortened", "summarised", "table-as-summary", "rounded-values", "trimmed", ""],
)
def test_an_invented_degradation_refuses(invented: str) -> None:
    """`SC-021`: the matrix decides what a channel may do, not the renderer."""
    with pytest.raises(NotRepresentable) as caught:
        require_declared_degradation(FIXTURE_CAPABILITY, invented, "fixture-capability-1")
    assert "not declared by the capability matrix" in str(caught.value)


def test_a_declared_degradation_without_disclosure_wording_refuses() -> None:
    """Declared but undisclosable is still undisclosable, so it cannot be applied."""
    capability = {
        **FIXTURE_CAPABILITY,
        "disclosure_wording": {"emphasis-dropped": "a ênfase não é expressável neste canal"},
    }
    with pytest.raises(NotRepresentable) as caught:
        require_declared_degradation(capability, "table-as-list", "fixture-capability-1")
    assert "no governed disclosure wording" in str(caught.value)


def test_a_matrix_with_no_degradation_list_refuses_rather_than_defaulting_to_none() -> None:
    """Refusing beats defaulting: a malformed document must not look like a stricter rule."""
    capability = {
        key: value for key, value in FIXTURE_CAPABILITY.items() if key != "permitted_degradations"
    }
    with pytest.raises(NotRepresentable) as caught:
        declared_degradations(capability)
    assert "permitted_degradations" in str(caught.value)


def test_a_degradation_entry_that_is_not_a_named_string_refuses() -> None:
    for malformed in ([1, 2], [None], [""], ["  "], "table-as-list"):
        capability = {**FIXTURE_CAPABILITY, "permitted_degradations": malformed}
        with pytest.raises(NotRepresentable):
            declared_degradations(capability)


def test_no_content_altering_operation_exists_in_the_degradation_module() -> None:
    """`FR-110`, structurally. The list is imported so the scan and the rule stay one thing."""
    source = Path(inspect.getfile(degrade_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    defined = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    for name in defined:
        for forbidden in FORBIDDEN_CONTENT_OPERATIONS:
            assert forbidden not in name.lower(), f"{name} performs a content change"


def test_the_forbidden_list_covers_the_operations_the_contract_names() -> None:
    """The list is the mechanism, so its coverage is asserted rather than assumed."""
    for required in ("truncate", "summarise", "reword", "round", "elide", "omit", "sample", "trim"):
        assert required in FORBIDDEN_CONTENT_OPERATIONS


def test_the_degradation_contract_has_no_field_for_a_content_change() -> None:
    """By field set: a content change has nowhere to be recorded, because none is permitted."""
    from channel_integration.contracts.presentation import Degradation

    assert set(Degradation.model_fields) == {"capability_ref", "disclosure_code"}
    for forbidden in ("original", "replacement", "removed", "shortened_to", "summary"):
        assert forbidden not in Degradation.model_fields
