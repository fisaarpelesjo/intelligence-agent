"""No clock on the request path — T056 (FR-099; SC-057).

    The reference date MUST be supplied explicitly by the caller and MUST NOT be
    read from a system clock. A question carrying a relative or named period
    expression with no reference date MUST clarify or refuse; it MUST NOT default
    to the current day. — `FR-099`

The failure this prevents is quiet. A defaulted reference date makes "semana
passada" mean something different depending on when the request happened to run,
so the same question asked twice produces two answers with no visible cause —
and `SC-005`'s reproducibility requirement fails in a way no test of a single run
would catch.

**Scanned as calls, not as text.** ``from datetime import date`` for a type
annotation is legitimate and ubiquitous; ``date.today()`` is not. Only a call-site
scan separates them, and a text scan would ban the annotation.

This file also carries the derivation half. `FR-097` forbids either date being
filled from the other, and the shape that would take is an assignment or default
mentioning both — checked directly, because "no derivation" is otherwise a claim
nobody can verify from a passing call.
"""

from __future__ import annotations

import ast
import inspect
from datetime import date
from pathlib import Path

import pytest

import analytics_interaction
from analytics_interaction.contracts.intake import QuestionIntake
from analytics_interaction.intake.dates import IntakeDates, period_anchor, version_pin

pytestmark = pytest.mark.contract

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent

#: Calls that read a clock. ``time`` is deliberately absent as a bare name: it is
#: also a `datetime` *type*, and banning the name would ban the annotation.
CLOCK_CALLS = (
    "today",
    "now",
    "utcnow",
    "fromtimestamp",
    "utcfromtimestamp",
    "monotonic",
    "perf_counter",
    "time_ns",
    "gmtime",
    "localtime",
)

CLOCK_MODULES = ("time", "calendar")


def _sources() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _calls(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = (
            node.func.attr
            if isinstance(node.func, ast.Attribute)
            else node.func.id
            if isinstance(node.func, ast.Name)
            else ""
        )
        if name:
            found.append((node.lineno, name))
    return found


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)
    return found


# --- no clock is read ---------------------------------------------------------


@pytest.mark.parametrize("call", CLOCK_CALLS)
def test_no_module_calls_a_clock(call: str) -> None:
    offenders = [
        f"{path.relative_to(SRC).as_posix()}:{line} {name}()"
        for path in _sources()
        for line, name in _calls(path)
        if name == call
    ]
    assert not offenders, f"a clock is read on the request path: {offenders}"


@pytest.mark.parametrize("module", CLOCK_MODULES)
def test_no_module_imports_a_clock_module(module: str) -> None:
    offenders = [
        f"{path.relative_to(SRC).as_posix()} imports {imported}"
        for path in _sources()
        for imported in _imports(path)
        if imported == module or imported.startswith(module + ".")
    ]
    assert not offenders, f"a clock module is imported: {offenders}"


def test_the_scan_permits_the_datetime_type_it_must_not_ban() -> None:
    """`date` and `datetime` are annotations across the contracts.

    Asserted so the guard's narrowness is deliberate and documented rather than
    an oversight somebody later "fixes" into a text scan.
    """
    assert QuestionIntake.model_fields["reference_date"].annotation is date
    assert any("datetime" in imported for path in _sources() for imported in _imports(path))


def test_the_scan_would_catch_a_planted_clock_read() -> None:
    planted = ast.parse("reference_date = date.today()\n")
    names = {
        node.func.attr
        for node in ast.walk(planted)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert names & set(CLOCK_CALLS)


# --- neither date is derived from the other -----------------------------------


def test_no_module_assigns_one_date_from_the_other() -> None:
    """The shape a derivation would take, checked directly.

    An assignment or default whose value mentions the *other* date is the only
    way one could be filled from the other, and it is what this catches.
    """
    offenders: list[str] = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign | ast.AnnAssign):
                continue
            targets = [node.target] if isinstance(node, ast.AnnAssign) else list(node.targets)
            rendered_target = " ".join(ast.unparse(t) for t in targets)
            rendered_value = ast.unparse(node.value) if node.value is not None else ""
            crosses = ("as_of" in rendered_target and "reference_date" in rendered_value) or (
                "reference_date" in rendered_target and "as_of" in rendered_value
            )
            if crosses:
                offenders.append(
                    f"{path.relative_to(SRC).as_posix()}:{node.lineno} "
                    f"{rendered_target} = {rendered_value}"
                )
    assert not offenders, f"one date is derived from the other: {offenders}"


def test_neither_accessor_can_reach_the_other_date() -> None:
    """Structural, not behavioural: each returns one field and branches on nothing."""
    for accessor, field_name, other in (
        (period_anchor, "reference_date", "as_of"),
        (version_pin, "as_of", "reference_date"),
    ):
        source = inspect.getsource(accessor)
        body = source.split('"""')[2]
        assert f"dates.{field_name}" in body
        assert other not in body, f"{accessor.__name__} mentions {other}"


def test_an_omitted_as_of_stays_none_rather_than_becoming_the_reference_date() -> None:
    dates = IntakeDates(reference_date=date(2026, 8, 13))
    assert period_anchor(dates) == date(2026, 8, 13)
    assert version_pin(dates) is None


def test_the_two_dates_vary_independently() -> None:
    """Changing one leaves the other untouched, in both directions."""
    a = IntakeDates(reference_date=date(2026, 8, 13), as_of=date(2026, 1, 1))
    b = IntakeDates(reference_date=date(2026, 8, 14), as_of=date(2026, 1, 1))
    c = IntakeDates(reference_date=date(2026, 8, 13), as_of=date(2026, 2, 2))

    assert version_pin(a) == version_pin(b) and period_anchor(a) != period_anchor(b)
    assert period_anchor(a) == period_anchor(c) and version_pin(a) != version_pin(c)


def test_the_pair_round_trips_and_serialises_deterministically() -> None:
    """Both are disclosed on every response, so both must survive a round trip."""
    original = IntakeDates(reference_date=date(2026, 8, 13), as_of=date(2026, 7, 1))
    rendered = original.model_dump_json()
    assert IntakeDates.model_validate_json(rendered) == original
    assert rendered == original.model_dump_json()
    assert '"reference_date":"2026-08-13"' in rendered
    assert '"as_of":"2026-07-01"' in rendered


def test_an_omitted_as_of_serialises_as_null_rather_than_being_dropped() -> None:
    """`FR-098`: both are disclosed on every response, including the absent one.

    Dropping the key would make "not pinned" indistinguishable from "field not
    present in this version of the contract".
    """
    rendered = IntakeDates(reference_date=date(2026, 8, 13)).model_dump_json()
    assert '"as_of":null' in rendered
