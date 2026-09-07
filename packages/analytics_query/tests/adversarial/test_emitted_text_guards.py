"""Guard 2 adversarial suite — T055 (FR-026, FR-027, FR-028; SC-002, SC-022).

Every assertion in the emitted-text guard gets at least one input that fires it.
A guard nobody has seen fail is a guard nobody knows works.

These inputs are deliberately *synthetic*: they are texts the compiler should be
incapable of producing. The point is not that the compiler emits them — it is
that if a future change ever did, the guard stops it before the adapter is
reached. A guard failure **raises**; it is a defect, never a refusal shown to a
caller.
"""

from __future__ import annotations

import pytest

from analytics_query.compile.guards import GuardViolation, assert_emitted_text_is_safe
from analytics_query.execution.adapter import RenderedQuery, ScalarValue

pytestmark = pytest.mark.adversarial

SAFE = (
    "SELECT SUM(installs) AS installs FROM `semantic.metric_installs` WHERE d BETWEEN @p0 AND @p1"
)


def _query(text: str, parameters: dict[str, ScalarValue] | None = None) -> RenderedQuery:
    return RenderedQuery(text=text, parameters=parameters or {})


def test_the_baseline_text_passes() -> None:
    """Otherwise every assertion below would pass vacuously."""
    assert_emitted_text_is_safe(_query(SAFE))


@pytest.mark.parametrize(
    ("text", "what"),
    [
        (SAFE + "; DROP TABLE x", "second statement"),
        (SAFE + "; SELECT 1", "second SELECT"),
        (SAFE + " -- trailing comment", "line comment"),
        (SAFE + " /* block */", "block comment"),
        ("SELECT 1 # hash comment FROM `semantic.x`", "hash comment"),
        ("SELECT a FROM `raw.events`", "raw dataset"),
        ("SELECT a FROM `staging.events`", "staging dataset"),
        ("SELECT a FROM `core.events`", "core dataset"),
        ("SELECT a FROM `other_dataset.events`", "non-governed dataset"),
        ("SELECT a FROM `semantic.x.y`", "over-qualified reference"),
        ("INSERT INTO `semantic.x` VALUES (1)", "DML verb"),
        ("UPDATE `semantic.x` SET a = 1", "UPDATE"),
        ("DELETE FROM `semantic.x`", "DELETE"),
        ("CREATE TABLE `semantic.x` AS SELECT 1", "DDL verb"),
        ("DROP TABLE `semantic.x`", "DROP"),
        ("MERGE INTO `semantic.x` USING `semantic.y`", "MERGE"),
        ("GRANT SELECT ON `semantic.x` TO r", "GRANT"),
        ("SELECT a", "no table reference"),
        ("   ", "empty text"),
    ],
)
def test_each_hostile_text_is_refused(text: str, what: str) -> None:
    with pytest.raises(GuardViolation):
        assert_emitted_text_is_safe(_query(text))


def test_interpolation_reintroduction_is_caught() -> None:
    """The assertion that survives a refactor defeating guards 1 and 3.

    Here the value was formatted into the text *and* still declared as a
    parameter — the exact residue of a half-finished change.
    """
    text = "SELECT a FROM `semantic.x` WHERE country = 'BR'"
    with pytest.raises(GuardViolation) as caught:
        assert_emitted_text_is_safe(_query(text, {"p0": "BR"}))
    assert "never syntax" in str(caught.value)


def test_a_value_that_merely_resembles_the_text_is_still_caught() -> None:
    """No allowance for "it was probably a coincidence"."""
    with pytest.raises(GuardViolation):
        assert_emitted_text_is_safe(_query(SAFE, {"p0": "installs"}))


def test_a_guard_failure_is_not_a_governed_refusal() -> None:
    """It carries no reason code, because it is a defect, not a decision."""
    with pytest.raises(GuardViolation) as caught:
        assert_emitted_text_is_safe(_query("DELETE FROM `semantic.x`"))
    assert not hasattr(caught.value, "code")


def test_parameters_are_permitted_in_the_text_as_placeholders() -> None:
    """Placeholder *names* belong in the text; only values must not."""
    assert_emitted_text_is_safe(_query(SAFE, {"p0": "2026-07-01", "p1": "2026-07-31"}))
