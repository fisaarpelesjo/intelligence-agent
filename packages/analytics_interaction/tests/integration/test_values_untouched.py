"""Values are carried, never touched — T130 (FR-033; SC-008).

    Evidence: byte-identical to the port response; no arithmetic on a side's
    figure. — `tasks.md` T130

A figure that arrives from `002` reaches the answer unchanged. Not rounded, not
reformatted, not re-scaled, not normalised to a "nicer" precision, not summed and
not averaged. The only number this feature produces is the derived comparison
figure, and it is marked `CALCULATED_COMPARISON` precisely so a reader can tell
the two apart.

## Why `str` and not `==`

``Decimal("150.00") == Decimal("150")`` is ``True`` and the two serialise
differently. The trailing zeros are significant — they say the warehouse reported
two decimal places — and an answer that quietly dropped them would be presenting
a figure at a precision nobody measured. So the assertions compare **strings**,
which is what a consumer actually receives.

## The scan, and what it is for

Behavioural equality proves the value survived *this* path. The static scan
proves there is no arithmetic on the answer path at all — no ``round``, no ``sum``,
no ``quantize``, no ``normalize``, no ``/``, no ``*``. Together they say the value
was not altered and could not have been.

`answer/derived.py` is excluded from the arithmetic scan and included in the
float scan: it carries the difference Phase 10 computed, and carrying is not
computing.
"""

from __future__ import annotations

import ast
import inspect
from decimal import Decimal
from pathlib import Path

import pytest

from analytics_interaction.answer import assemble, caveats, claims, derived, provenance, withhold
from analytics_interaction.answer.claims import cell_for, factual
from analytics_interaction.contracts.intent import ResolvedIntent

from ..fixtures.answers import ref
from ..fixtures.comparisons import executed

pytestmark = pytest.mark.integration

ANSWER_PATH = (assemble, claims, caveats, derived, provenance, withhold)

#: Operations that would alter a figure. ``quantize`` and ``normalize`` are the
#: ones that look harmless: both produce a "tidier" decimal and both change what
#: the warehouse reported.
ARITHMETIC = frozenset(
    {"round", "sum", "quantize", "normalize", "scaleb", "shift", "fma", "mean", "abs"}
)


def _source(module: object) -> str:
    return Path(inspect.getfile(module)).read_text(encoding="utf-8")  # type: ignore[arg-type]


# --- the value survives ---------------------------------------------------------


@pytest.mark.parametrize(
    "reported",
    [
        Decimal("150"),
        Decimal("150.00"),
        Decimal("0.1"),
        Decimal("1E+3"),
        Decimal("-42.5"),
        Decimal("123456789012345678901234567890"),
        7,
    ],
)
def test_the_reported_figure_reaches_the_claim_byte_identically(
    reported: Decimal | int,
) -> None:
    """Compared as strings: trailing zeros and exponents are significant."""
    answer = executed(reported)
    cell = cell_for(answer.result)

    claim = factual(subject="installs", cell=cell, unit="count", message=ref("claim.factual"))

    assert claim.value is not None
    assert str(claim.value) == str(cell.value)
    assert claim.value == cell.value


def test_the_serialised_claim_preserves_the_reported_precision() -> None:
    """What a consumer actually receives, not what compares equal in memory."""
    answer = executed(Decimal("150.00"))
    claim = factual(
        subject="installs",
        cell=cell_for(answer.result),
        unit="count",
        message=ref("claim.factual"),
    )

    assert '"150.00"' in claim.model_dump_json() or "150.00" in claim.model_dump_json()
    assert str(claim.value) == "150.00"


def test_the_unit_is_carried_exactly() -> None:
    """No normalisation, no case folding, no aliasing."""
    answer = executed(Decimal("150"), unit="BRL")
    claim = factual(
        subject="revenue",
        cell=cell_for(answer.result),
        unit=answer.result.columns[0].unit,
        message=ref("claim.factual"),
    )
    assert claim.unit == "BRL"


def test_the_claim_takes_a_cell_not_a_number() -> None:
    """`FR-033` structurally: the value is read off a governed result.

    Passing a number in would let a caller compute anything and label it factual.
    Taking the cell means the only figure expressible is one `002` returned.
    """
    parameters = inspect.signature(factual).parameters
    assert "cell" in parameters
    assert "value" not in parameters
    assert parameters["cell"].kind is inspect.Parameter.KEYWORD_ONLY


# --- and could not have been altered --------------------------------------------


@pytest.mark.parametrize("module", ANSWER_PATH, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_no_answer_module_performs_arithmetic_on_a_figure(module: object) -> None:
    """No rounding, no summing, no quantising anywhere on the path."""
    tree = ast.parse(_source(module))
    called = {
        node.attr if isinstance(node, ast.Attribute) else node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute | ast.Name)
    }
    offenders = sorted(called & ARITHMETIC)
    assert not offenders, f"arithmetic on the answer path: {offenders}"


@pytest.mark.parametrize("module", ANSWER_PATH, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_no_answer_module_uses_binary_floating_point(module: object) -> None:
    """`SC-005` requires identical output for identical input, to the last digit."""
    tree = ast.parse(_source(module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, float):
            pytest.fail(f"a float literal appears at line {node.lineno}")
        if isinstance(node, ast.Name | ast.Attribute):
            name = node.id if isinstance(node, ast.Name) else node.attr
            assert name != "float", f"float() is called at line {node.lineno}"


@pytest.mark.parametrize("module", ANSWER_PATH, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_no_answer_module_multiplies_or_divides(module: object) -> None:
    """The two operations that silently re-scale a figure."""
    tree = ast.parse(_source(module))
    operations = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult | ast.Div | ast.FloorDiv)
    ]
    assert not operations, f"a scaling operation appears at line {operations[0].lineno}"


def test_the_derived_figure_is_carried_not_recomputed() -> None:
    """Phase 10 owns the arithmetic; `derived.py` reads its result.

    A second implementation here would be free to disagree with the first, and
    the disagreement would surface as two different answers to one question.
    """
    tree = ast.parse(_source(derived))
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "derive_figure" not in called
    assert "to_exact" not in called
    assert "Decimal" not in called


def test_the_answer_contract_declares_decimal_not_float() -> None:
    """The contract, not only the code path."""
    from analytics_interaction.contracts.answer import AnswerClaim

    annotation = AnswerClaim.model_fields["value"].annotation
    assert "Decimal" in str(annotation)
    assert "float" not in str(annotation)


# --- the two claim kinds stay distinguishable ------------------------------------


def test_a_carried_figure_and_a_derived_one_are_different_classes(
    resolved_intent: ResolvedIntent,
) -> None:
    """`SC-009`. A reader can tell a warehouse number from a computed one.

    Not by wording — by type, which survives any renderer.
    """
    from analytics_interaction.contracts.answer import ClaimClass

    answer = executed(Decimal("150"))
    carried = factual(
        subject="installs",
        cell=cell_for(answer.result),
        unit="count",
        message=ref("claim.factual"),
    )

    assert carried.claim_class is ClaimClass.FACTUAL_RESULT
    assert carried.derived_from is None
    assert carried.basis is None
    assert resolved_intent.metrics == ("installs",)
