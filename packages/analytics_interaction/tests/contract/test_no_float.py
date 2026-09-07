"""No binary floating point on the arithmetic path — T105 (FR-070; SC-040).

    Evidence: a float in the path fails the scan. — `tasks.md` T105

**A type scan, not a token scan.** The check walks the AST of every module the
comparison arithmetic can reach and looks for ``float`` as an *identifier* — an
annotation, a call, a base class, a default. A substring scan would fire on
``floating``, on a docstring saying "no float", and on this very file's name; the
narrowing is what makes the guard survive contact with prose about itself.

**Why it matters more than it looks.** ``0.1 + 0.2 != 0.3`` is the famous case,
but the one that bites here is quieter: two warehouses returning the same decimal
figure, one through a float column, produce differences that disagree in the
sixteenth digit. `SC-005` requires identical output for identical input, and a
comparison that is *nearly* reproducible is not reproducible.

**The scan is proven to fire.** Six planted sources — an annotation, a
constructor, a literal default, a division that returns a float, a ``round`` call
and a ``float``-typed field — each fail it. A denylist never shown to fire proves
nothing, and this one has to survive the fact that the modules it guards discuss
floats at length in their docstrings.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

import analytics_interaction
from analytics_interaction.comparison import compute, formula, refusal, units

pytestmark = pytest.mark.contract

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent

#: The arithmetic path. Named module by module rather than globbed, so a new
#: module joining the comparison package is a deliberate addition here — and so
#: the scan's scope is legible rather than implied.
ARITHMETIC_PATH = (compute, formula, units, refusal)

#: Identifiers that introduce or produce binary floating point. ``round`` is
#: included because it is the rounding this feature must not apply, and because
#: ``round(Decimal)`` silently returns a value quantised by a rule nobody
#: governed.
FLOAT_NAMES = frozenset({"float", "round", "fsum", "isclose"})

#: Operators that produce a float from exact inputs. ``/`` does **not**: it is
#: exact on ``Decimal`` and is how ratio and percentage change are computed.
FLOAT_OPERATORS = (ast.FloorDiv,)


def _float_uses(source: str, filename: str = "<test>") -> list[str]:
    """Every float-introducing identifier, literal and operator, by AST."""
    tree = ast.parse(source, filename=filename)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in FLOAT_NAMES:
            found.append(f"{node.lineno}:{node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in FLOAT_NAMES:
            found.append(f"{node.lineno}:{node.attr}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, float):
            found.append(f"{node.lineno}:literal")
        elif isinstance(node, ast.BinOp) and isinstance(node.op, FLOAT_OPERATORS):
            found.append(f"{node.lineno}:operator")
    return found


def _source_of(module: object) -> tuple[Path, str]:
    path = Path(inspect.getfile(module))  # type: ignore[arg-type]
    return path, path.read_text(encoding="utf-8")


# --- the path is clean -------------------------------------------------------------


@pytest.mark.parametrize("module", ARITHMETIC_PATH, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_no_arithmetic_module_touches_binary_floating_point(module: object) -> None:
    path, source = _source_of(module)
    offenders = _float_uses(source, str(path))
    assert not offenders, f"{path.name} reaches binary floating point at {offenders}"


def test_no_module_anywhere_in_the_package_introduces_a_float_literal() -> None:
    """Wider than the arithmetic path, because a float reaches it by being passed.

    A float literal anywhere in `003` is a value that could be handed to a
    comparison, so the literal check runs over the whole source tree while the
    identifier check stays scoped to the modules that compute.
    """
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        offenders += [
            f"{path.relative_to(SRC).as_posix()}:{node.lineno}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, float)
        ]
    assert not offenders, f"a float literal is declared: {offenders}"


def test_the_scan_is_not_confused_by_the_prose_about_floats() -> None:
    """These modules say "float" repeatedly, and none of them uses one.

    The distinction the AST makes and a token scan cannot.
    """
    _, source = _source_of(compute)
    assert "float" in source
    assert not _float_uses(source)


# --- the values that actually flow are exact ---------------------------------------


def test_the_lifting_function_admits_only_exact_types() -> None:
    """Read from the source: ``Decimal`` and ``int``, and nothing else.

    Asserted structurally as well as behaviourally, so a widening that added a
    ``float`` branch shows up here even if a behavioural test were forgotten.
    """
    tree = ast.parse(inspect.getsource(compute.to_exact))
    admitted = {
        ast.unparse(node.comparators[0]) if node.comparators else ""
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare)
    }
    checked = {
        ast.unparse(node.args[1])
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "isinstance"
    }
    assert checked == {"Decimal", "int", "bool"}
    assert "float" not in checked | admitted


def test_the_derived_figure_field_is_decimal() -> None:
    """The contract, not just the computation."""
    from decimal import Decimal

    from analytics_interaction.contracts.comparison import DerivedFigure

    assert DerivedFigure.model_fields["value"].annotation is Decimal


# --- the scan fires ------------------------------------------------------------------


@pytest.mark.parametrize(
    "planted",
    [
        pytest.param("def go(x: float) -> float:\n    return x\n", id="annotation"),
        pytest.param("def go(x):\n    return float(x)\n", id="constructor"),
        pytest.param("TOLERANCE = 0.001\n", id="literal"),
        pytest.param("def go(a, b):\n    return a // b\n", id="floor-division"),
        pytest.param("def go(x):\n    return round(x, 2)\n", id="rounding"),
        pytest.param("import math\ndef go(a, b):\n    return math.isclose(a, b)\n", id="tolerance"),
    ],
)
def test_the_scan_catches_a_planted_float(planted: str) -> None:
    """Each is a real way binary floating point or invented rounding gets in."""
    assert _float_uses(planted), "a float use was not detected"


@pytest.mark.parametrize(
    "innocent",
    [
        pytest.param('"""No binary floating point anywhere."""\n', id="docstring"),
        pytest.param("FLOATING_POINT_IS_BANNED = True\n", id="similar-name"),
        pytest.param("from decimal import Decimal\nX = Decimal('0.1')\n", id="exact-decimal"),
        pytest.param("def go(a, b):\n    return a / b\n", id="exact-division"),
    ],
)
def test_the_scan_does_not_fire_on_prose_or_on_exact_arithmetic(innocent: str) -> None:
    """``/`` on ``Decimal`` is exact and is how ratio is computed."""
    assert not _float_uses(innocent)
