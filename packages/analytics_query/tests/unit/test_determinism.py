"""Deterministic output — T113 (FR-057, FR-058, FR-059; SC-021).

Identical invocations produce byte-identical JSON and byte-identical pt-BR text.

Two runs compared byte-for-byte, not field-by-field. A field-wise comparison
passes while key order drifts, and key order drift is enough to make a diff
between two compliance reports unreadable -- which is exactly when someone stops
reading them.

`FR-059` draws a line this suite respects: automation reports **presence and
determinism**, never linguistic correctness. Nothing here asserts that a pt-BR
sentence is well written or says the right thing; that is the reviewer duty
recorded as `D-10`, and a test claiming otherwise would be automation vouching
for something it cannot check.
"""

from __future__ import annotations

import json

import pytest

from analytics_query.cli.main import main
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from analytics_query.messages.registry import load_registry, message_for

pytestmark = pytest.mark.unit

#: Sorted so parametrize ids are stable across runs.
_CODES: list[AnalyticsReasonCode] = sorted(AnalyticsReasonCode, key=lambda c: c.value)

COMMANDS = [
    ["validate-governance"],
    ["explain-plan"],
    ["ledger", "show"],
    ["schema", "export"],
    ["messages"],
]


# --- byte-identical JSON -----------------------------------------------------


@pytest.mark.parametrize("argv", COMMANDS, ids=lambda a: " ".join(a))
def test_two_invocations_produce_byte_identical_json(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    main(argv)
    first = capsys.readouterr().out
    main(argv)
    second = capsys.readouterr().out
    assert first == second


@pytest.mark.parametrize("argv", COMMANDS, ids=lambda a: " ".join(a))
def test_json_keys_are_sorted(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    """Key order drift makes a diff unreadable, which is when it stops being read."""
    main(argv)
    payload = json.loads(capsys.readouterr().out)
    assert list(payload) == sorted(payload)


@pytest.mark.parametrize("argv", COMMANDS, ids=lambda a: " ".join(a))
def test_output_is_compact_json_on_one_line(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """Fixed separators, no pretty-printing.

    Asserted on the structure rather than by searching for a comma-space:
    governed pt-BR wording legitimately contains commas followed by spaces,
    and a naive scan would flag the message text itself.
    """
    main(argv)
    out = capsys.readouterr().out
    assert out.endswith("\n")
    assert out.count("\n") == 1, "one line, so two runs diff cleanly"
    assert not out.startswith("{\n"), "not pretty-printed"


# --- byte-identical pt-BR text ----------------------------------------------


@pytest.mark.parametrize("code", _CODES, ids=[c.value for c in _CODES])
def test_each_message_is_byte_identical_across_repeats(code: AnalyticsReasonCode) -> None:
    assert message_for(code) == message_for(code)


def test_the_registry_is_byte_stable_across_reloads() -> None:
    first = {code.value: message_for(code) for code in AnalyticsReasonCode}
    load_registry.cache_clear() if hasattr(load_registry, "cache_clear") else None
    second = {code.value: message_for(code) for code in AnalyticsReasonCode}
    assert first == second


def test_no_message_is_generated_or_translated_at_answer_time() -> None:
    """Stored wording selected by code -- never composed."""
    import ast
    import inspect

    from analytics_query.messages import registry

    tree = ast.parse(inspect.getsource(registry))
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            node.value = ast.Constant("")
    # Only the lookup path matters. The module may raise f-string *errors*;
    # what it must never do is build the returned wording.
    returns = [
        ast.unparse(node).lower()
        for node in ast.walk(tree)
        if isinstance(node, ast.Return) and node.value is not None
    ]
    for rendered in returns:
        for marker in ("translate", "gettext", ".format(", "f'", 'f"', "%s", " + "):
            assert marker not in rendered, f"a message is composed on return: {marker!r}"


# --- FR-059: automation checks presence, not correctness --------------------


def test_automation_asserts_presence_and_determinism_only() -> None:
    """`D-10` reserves linguistic correctness for a human reviewer.

    Every code has non-empty stored wording and the same wording twice. Whether
    that wording is *good* pt-BR is not something this suite claims.
    """
    for code in AnalyticsReasonCode:
        text = message_for(code)
        assert text.strip(), f"{code.value} has no stored wording"
        assert text == message_for(code)
