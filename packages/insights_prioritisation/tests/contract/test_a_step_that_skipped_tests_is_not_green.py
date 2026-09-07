"""A step that exited zero having skipped tests is not green — the rule descending one level.

## The rule already existed, one level up

`run_local_ci.py`'s own docstring says it: **`VERDE` only when nothing was skipped**, because *a
skip makes a label assert more than was measured*. It counted **steps**. A step whose pytest skipped
twenty-one tests **exits zero**, and the runner read that step as measured in full — so the rule it
wrote for itself did not reach the level where the skips actually happen.

## What that cost, measured

On 2026-08-31 the application-default credential expired mid-cycle:

| suite | before | after |
|---|---|---|
| `anomaly_investigation` | 381 passed, **3 failed** | 376 passed, **8 skipped** |
| `daily_reporting` | 204 passed | 202 passed, 2 skipped |
| `insights_prioritisation` | 265 passed | 261 passed, 4 skipped |
| `proactive_distribution` | 87 passed | 84 passed, 3 skipped |
| the harness | 987 passed | 983 passed, 4 skipped |

**Twenty-one tests not run, zero failures anywhere** — and the three reds of `OD-23` that hold this
repository's push were among the ones that vanished. **It is the third time**: on 2026-08-30 the
same credential hid four reds of `006` and became `OD-22`. A defect that returns a third time is
not luck; it is a missing instrument.

## Both directions, because one of them is the whole risk

A skip is **not** turned into a failure — legitimate skips exist, and this repository's own suites
skip loudly when a credential is absent. What must not exist is an **invisible** skip. So this
drives the runner twice:

- a step whose pytest skips at least one test **must not** come out `VERDE`;
- a step that skipped nothing **must** come out `VERDE`.

Without the second, a blind gate would have been traded for a gate that never opens.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:  # pragma: no cover - typing only
    from types import ModuleType

pytestmark = pytest.mark.contract

#: `tests/contract/` -> `tests/` -> package -> `packages/` -> repository.
REPO = Path(__file__).resolve().parents[4]
RUNNER = REPO / "tools" / "local-ci" / "run_local_ci.py"
INTERPRETER = REPO / ".venv" / "Scripts" / "python.exe"


def _runner() -> ModuleType:
    """The runner, imported by path — it is a script and not a package."""
    if not RUNNER.is_file():  # pragma: no cover - a checkout without the runner
        pytest.skip(f"{RUNNER} is not in this checkout; nothing was measured")
    if shutil.which("bash") is None:  # pragma: no cover - no POSIX shell
        pytest.skip("no bash on this machine; the runner could not be driven")
    name = "run_local_ci_under_test"
    spec = importlib.util.spec_from_file_location(name, RUNNER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    #: Registered BEFORE executing: the runner defines dataclasses with `from __future__ import
    #: annotations`, and `dataclasses` resolves those through `sys.modules[cls.__module__]`. A
    #: module absent from there makes the class body raise instead of the guard being driven.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _workflow(tmp_path: Path, *, skipping: bool) -> Path:
    """A one-step workflow whose pytest **really** runs, and really skips or does not.

    `echo` of a summary line would test the parsing and not the behaviour. This runs the
    interpreter, so the step exits zero for the same reason a real suite does.
    """
    test_file = tmp_path / "test_one.py"
    body = (
        "import pytest\n\n\ndef test_it():\n    pytest.skip('a credencial nao esta aqui')\n"
        if skipping
        else "def test_it():\n    assert True\n"
    )
    test_file.write_text(body, encoding="utf-8")

    interpreter = INTERPRETER if INTERPRETER.is_file() else Path("python")
    #: **Forward slashes, and a block scalar.** A Windows path inside a YAML double-quoted string
    #: turns the backslash into an escape and the loader refuses the file -- which would have
    #: skipped this node for a reason unrelated to what it guards.
    command = f'"{interpreter.as_posix()}" -m pytest "{test_file.as_posix()}" -q -rs'
    workflow = tmp_path / "medido.yml"
    workflow.write_text(
        "name: medido\njobs:\n  um:\n    steps:\n      - name: a suite\n"
        f"        run: |\n          {command}\n",
        encoding="utf-8",
    )
    return workflow


def _result(tmp_path: Path, *, skipping: bool) -> Any:
    module = _runner()
    result = module.run_workflow(_workflow(tmp_path, skipping=skipping), dry_run=False)
    #: The step must actually have exited zero, or this measures a failure instead of a skip.
    assert result.failed is None, f"the step failed: {result.failed}"
    return result


def test_a_step_that_skipped_a_test_is_not_green(tmp_path: Path) -> None:
    """**The direction the credential kept exploiting.**"""
    result = _result(tmp_path, skipping=True)

    assert result.tests_skipped >= 1, "the skipped test was not counted"
    assert result.verdict != "VERDE", (
        f"a step that skipped {result.tests_skipped} tests came out {result.verdict}"
    )
    assert result.verdict == "PARCIAL"


def test_the_step_that_skipped_is_NAMED(tmp_path: Path) -> None:  # noqa: N802
    """A count with no name tells nobody where to look, which is the invisible skip renamed."""
    result = _result(tmp_path, skipping=True)

    (step,) = [step for step in result.steps if step.tests_skipped]
    assert step.name, "the step carrying the skip has no name"
    assert step.tests_skipped >= 1
    #: **And the reason travels with it.** The workflow this node builds always passes `-rs`, so
    #: the reason IS available and there is no excuse for it not arriving. An earlier version
    #: accepted `"-rs" in step.detail` as an alternative — and that alternative made the mutation
    #: "the reasons stop travelling" come out GREEN, because the fallback message contains `-rs`.
    #: An assertion with an escape hatch is an assertion the escape hatch satisfies.
    assert "a credencial nao esta aqui" in step.detail, step.detail


def test_a_step_that_skipped_nothing_is_green(tmp_path: Path) -> None:
    """**The other direction, and without it this is a gate that never opens.**"""
    result = _result(tmp_path, skipping=False)

    assert result.tests_skipped == 0, result.tests_skipped
    assert result.verdict == "VERDE", f"a step with no skip came out {result.verdict}"


def test_the_count_is_read_from_the_output_and_not_from_the_exit_code(tmp_path: Path) -> None:
    """The reading itself, over the summary lines pytest actually prints.

    Driven directly because this is where the rule descends: the exit code is zero in every case
    below, and only the text distinguishes them.
    """
    module = _runner()
    assert module.tests_skipped_in("202 passed, 2 skipped in 7.14s") == 2
    assert module.tests_skipped_in("376 passed, 8 skipped in 50.65s") == 8
    assert module.tests_skipped_in("1395 passed in 176.34s") == 0
    assert module.tests_skipped_in("3 failed, 381 passed, 1 warning in 87.99s") == 0

    reasons = module.skip_reasons_in(
        "SKIPPED [3] tests/integration/test_x.py:212: the credential needs re-login\n"
        "SKIPPED [2] tests/integration/test_x.py:257: the credential needs re-login\n"
    )
    assert len(reasons) == 2
    assert "test_x.py:212" in reasons[0]
