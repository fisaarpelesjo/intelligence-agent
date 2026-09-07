"""T115 — one interpretation path exists, and it is `003`'s (`SC-047`, `SC-055`; ADR 0017).

ADR 0017 authorized a composed entry point owned by `003` on one condition: this feature must not
order, compose or re-derive the sixteen steps. A second ordering anywhere would be a second
interpretation pipeline, and two pipelines mean two answers to one question — the failure the whole
ADR exists to prevent.

## What is asserted, and what would be a heuristic

The steps have **numbers** and a **count**, both fixed by `003`'s intake contract § 6. Those are
checkable. What a step *means* is prose, and matching this feature's slug against that prose would
be this test guessing at a mapping nobody authored — so the correspondence asserted here is
positional and numeric, never lexical.

Concretely:

* the contract's table declares steps 1 - 16, each exactly once, ascending;
* `STEP_ORDER` declares sixteen distinct names;
* `interact.py` carries one ascending run of step markers, 1 - 16, so its control flow follows one
  ordering rather than an emergent one;
* exactly one module in `003` declares such a run, so the ordering is declared once;
* **no** module in `004` declares one, and no `004` module imports `ask` or `STEP_ORDER`.

The last assertion is the one that constrains this feature. The others exist so it means something:
"`004` has no ordering" is worth little if nobody checked that `003` has exactly one.
"""

from __future__ import annotations

import ast
import re
import tokenize
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract


def _repository_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "packages").is_dir() and (parent / "docs").is_dir():
            return parent
    raise AssertionError("repository root not found")


_ROOT = _repository_root()
_CONTRACT = _ROOT / "specs" / "003-nl-analytics-interaction" / "contracts" / "intake-contract.md"
_INTERACTION_SRC = _ROOT / "packages" / "analytics_interaction" / "src" / "analytics_interaction"
_CHANNEL_SRC = _ROOT / "packages" / "channel_integration" / "src" / "channel_integration"

#: An **interpretation**-step marker as `interact.py` writes them: ``# --- interpretation step 7:
#: period resolution ---``. Anchored at the comment start and requiring the separator, so a sentence
#: mentioning "step 7" in prose is not a marker. The number is the only part this test reads.
#:
#: The word `interpretation` carries weight. This feature owns an eight-step **inbound** ordering of
#: its own, marked `# --- step 4: message kind ---` in `inbound/convert.py`, and it is authorized:
#: converting a transport payload is not interpreting a question. An earlier version of this test
#: matched any `step N` marker and flagged that module, which would have read as an ADR 0017
#: violation where there is none. Two orderings exist in this repository; only one of them is the
#: sixteen steps, and the prefix is what keeps them apart.
_STEP_MARKER = re.compile(r"^#\s*-{2,}\s*interpretation\s+step\s+(\d+)\s*:")

#: A row of the contract's ordered-sequence table: ``| 7 | Period resolution ... |``.
_TABLE_ROW = re.compile(r"^\|\s*(\d+)\s*\|")

_EXPECTED_STEPS = 16


def _step_numbers(path: Path) -> list[int]:
    """Every step marker's number in ``path``, in file order.

    Read through :mod:`tokenize` rather than by scanning lines, so a marker-shaped string inside a
    docstring or a literal is not mistaken for a marker. Only ``COMMENT`` tokens are considered.
    """
    found: list[int] = []
    with path.open("rb") as handle:
        for token in tokenize.tokenize(handle.readline):
            if token.type != tokenize.COMMENT:
                continue
            match = _STEP_MARKER.match(token.string.strip())
            if match is not None:
                found.append(int(match.group(1)))
    return found


def _python_sources(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _step_order() -> tuple[str, ...]:
    """`STEP_ORDER`'s value, read from the source by :mod:`ast`.

    Read statically rather than imported: importing `003` to check that `004` does not compose its
    steps would make the test itself the counter-example.
    """
    module = ast.parse((_INTERACTION_SRC / "interact.py").read_text(encoding="utf-8"))
    for node in module.body:
        if not isinstance(node, ast.AnnAssign | ast.Assign):
            continue
        targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
        names = {t.id for t in targets if isinstance(t, ast.Name)}
        if "STEP_ORDER" not in names:
            continue
        value = node.value
        if not isinstance(value, ast.Tuple):
            raise AssertionError("STEP_ORDER is no longer a tuple literal")
        return tuple(
            element.value
            for element in value.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        )
    raise AssertionError("STEP_ORDER not found in interact.py")


def test_the_contract_declares_sixteen_steps_numbered_once_each() -> None:
    """The count this feature must not re-derive comes from `003`'s contract, not from here."""
    section = _CONTRACT.read_text(encoding="utf-8").split("## 6. The ordered sequence", 1)
    assert len(section) == 2, "the intake contract no longer has a § 6 ordered sequence"
    body = section[1].split("\n---", 1)[0]

    numbers = [
        int(match.group(1))
        for line in body.splitlines()
        if (match := _TABLE_ROW.match(line.strip())) is not None
    ]
    assert numbers == list(range(1, _EXPECTED_STEPS + 1)), (
        f"the contract's ordered sequence reads {numbers}; expected 1 to "
        f"{_EXPECTED_STEPS} ascending, each exactly once"
    )


def test_step_order_declares_sixteen_distinct_names() -> None:
    order = _step_order()
    assert len(order) == _EXPECTED_STEPS, f"STEP_ORDER has {len(order)} entries"
    assert len(set(order)) == len(order), "STEP_ORDER repeats a name"


def test_the_entry_point_follows_one_ascending_ordering() -> None:
    """Markers 1 - 16 in ascending file order.

    A repeated or out-of-order number would mean the control flow revisits a step, which is how an
    ordering stops being an ordering.

    **A marker means the step is accounted for, not that code runs.** Three steps compose nothing
    today: 8 is optional model narrowing while `D-20` is undeclared, and 13 and 15 belong to the
    two-execution route, which this composition does not exercise. Each says so at its marker. The
    alternative — omitting them — would make the ordering look complete while silently skipping
    three of the contract's rows, and this test would have been the thing that agreed.
    """
    numbers = _step_numbers(_INTERACTION_SRC / "interact.py")
    assert numbers == list(range(1, _EXPECTED_STEPS + 1)), (
        f"interact.py's step markers read {numbers}; expected 1 - {_EXPECTED_STEPS} ascending"
    )


def test_exactly_one_module_in_the_interaction_package_declares_an_ordering() -> None:
    """One ordering, declared once. Two would be two pipelines inside one package."""
    carriers = [
        str(path.relative_to(_INTERACTION_SRC))
        for path in _python_sources(_INTERACTION_SRC)
        if _step_numbers(path)
    ]
    assert carriers == ["interact.py"], f"step markers appear in {carriers}"


def test_this_feature_declares_no_ordering_of_its_own() -> None:
    """The assertion ADR 0017 actually constrains: `004` orders no **interpretation** step.

    Its own inbound ordering is untouched by this: that sequence converts a transport payload into a
    canonical message and decides nothing about what a question means.
    """
    offenders = {
        str(path.relative_to(_CHANNEL_SRC)): _step_numbers(path)
        for path in _python_sources(_CHANNEL_SRC)
        if _step_numbers(path)
    }
    assert not offenders, (
        f"{offenders} declare step markers. Ordering the sixteen steps here is a second "
        "interpretation pipeline (ADR 0017 § Acceptance)"
    )


def test_this_feature_names_no_step_of_the_pipeline() -> None:
    """Naming several step functions is composing them, marker comments or not.

    One name is not enough to fail: `resolve_period` or `screen_question` could plausibly appear in
    a
    sentence about what this feature does not do. Two or more in one module is a composition.
    """
    order = set(_step_order())
    offenders: dict[str, list[str]] = {}
    for path in _python_sources(_CHANNEL_SRC):
        module = ast.parse(path.read_text(encoding="utf-8"))
        named = sorted(
            {
                node.id
                for node in ast.walk(module)
                if isinstance(node, ast.Name) and node.id in order
            }
            | {
                alias.asname or alias.name
                for node in ast.walk(module)
                if isinstance(node, ast.ImportFrom)
                for alias in node.names
                if alias.name in order
            }
        )
        if len(named) > 1:
            offenders[str(path.relative_to(_CHANNEL_SRC))] = named
    assert not offenders, f"{offenders} name several pipeline steps"


def test_this_feature_imports_neither_the_entry_point_nor_its_ordering() -> None:
    """`004` consumes the port, never the composition.

    Importing `ask` would not be a second pipeline — it would be the first one, reached around the
    port that ADR 0017 made the only authorized surface.
    """
    forbidden = {"ask", "STEP_ORDER", "InteractionCollaborators", "governed_request_for"}
    offenders: dict[str, list[str]] = {}
    for path in _python_sources(_CHANNEL_SRC):
        module = ast.parse(path.read_text(encoding="utf-8"))
        imported = sorted(
            {
                alias.name
                for node in ast.walk(module)
                if isinstance(node, ast.ImportFrom)
                and (node.module or "").startswith("analytics_interaction")
                for alias in node.names
                if alias.name in forbidden
            }
        )
        if imported:
            offenders[str(path.relative_to(_CHANNEL_SRC))] = imported
    assert not offenders, f"{offenders} import the composed entry point directly"
