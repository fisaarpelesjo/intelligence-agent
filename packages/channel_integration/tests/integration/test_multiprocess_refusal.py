"""A multi-instance configuration refuses — T100 (ADR 0021; FR-067; SC-029).

Duplicate suppression is process-local. Run two instances and a redelivery that lands on the other
one is not recognised, so the sender receives a governed answer **twice**.

The choice is therefore between refusing and degrading silently, and degrading silently is the worse
option by a wide margin: it hands an operator the words "duplicate suppression" and none of the
behaviour, and the gap surfaces as a doubled answer rather than as a startup failure. `NG-4` records
that this feature does not build the governed shared store that would make cross-process suppression
real, so there is nothing to fall back to.

The instance count is **passed in**, never discovered. Reading it from an environment variable would
be an ambient read the leak and persistence scans forbid, so the deployment declares its own
shape and this gate judges it.

Zero refuses too. A declared count of zero is malformed, and treating it as "not running yet" would
let a caller pass zero to skip the check.
"""

from __future__ import annotations

import pytest

from channel_integration.compliance.readiness import (
    IDEMPOTENCY_SCOPE_STATEMENT,
    MultiInstanceRefused,
    require_single_instance,
)

pytestmark = pytest.mark.integration


def test_a_single_instance_is_permitted() -> None:
    assert require_single_instance(1) == 1


@pytest.mark.parametrize("declared", [2, 3, 8, 64])
def test_any_multi_instance_configuration_refuses(declared: int) -> None:
    with pytest.raises(MultiInstanceRefused) as caught:
        require_single_instance(declared)
    assert str(declared) in str(caught.value)


@pytest.mark.parametrize("declared", [0, -1])
def test_a_malformed_count_refuses_rather_than_being_read_charitably(declared: int) -> None:
    """Zero is not "not running yet"; it is a declaration nobody can act on."""
    with pytest.raises(MultiInstanceRefused):
        require_single_instance(declared)


def test_the_refusal_carries_the_scope_statement_verbatim() -> None:
    """One wording, one place: the refusal and a report read the same sentence."""
    with pytest.raises(MultiInstanceRefused) as caught:
        require_single_instance(4)
    assert IDEMPOTENCY_SCOPE_STATEMENT in str(caught.value)


def test_the_refusal_explains_why_rather_than_only_that() -> None:
    """A refusal an operator cannot act on gets worked around."""
    with pytest.raises(MultiInstanceRefused) as caught:
        require_single_instance(2)
    message = str(caught.value).lower()
    assert "process-local" in message
    assert "no cross-process" in message


def test_the_check_reads_nothing_from_the_environment() -> None:
    """The count is declared by the caller, so nothing here consults ambient state.

    Scanned over the function body with its **docstring removed**. The docstring explains that the
    count is passed rather than discovered, and naming ``environ`` in that explanation is how the
    rule gets recorded — a scan that could not tell the explanation from the behaviour would
    forbid the function from documenting itself.
    """
    import ast
    import inspect
    import textwrap

    from channel_integration.compliance import readiness

    source = textwrap.dedent(inspect.getsource(readiness.require_single_instance))
    tree = ast.parse(source)
    function = tree.body[0]
    assert isinstance(function, ast.FunctionDef)
    body = function.body[1:] if ast.get_docstring(function) else function.body
    code = " ".join(ast.unparse(node) for node in body)

    for forbidden in ("environ", "getenv", "argv", "open(", "read_text"):
        assert forbidden not in code, f"the check reads {forbidden}"
    assert list(inspect.signature(require_single_instance).parameters) == ["declared_instances"]


def test_the_docstring_names_what_would_go_wrong() -> None:
    """The reason is recorded with the rule, so a future reader does not relax it for tidiness."""
    doc = MultiInstanceRefused.__doc__ or ""
    lowered = doc.lower()
    assert "twice" in lowered, "the doubled-answer consequence is not stated"
    assert "ng-4" in lowered, "the missing governed store is not named"
