"""A step that did not report is a failure — the rule parallelism makes easy to break.

The push gate runs its eight steps **at once**, each writing its output and its exit code
to its own file, and reads the files afterwards. That is what took the wall clock from
543 s to 226 s without dropping a single suite from the coverage.

**And it introduces one way to be quietly wrong that the serial version did not have.**
Serially, a step that never ran could not be mistaken for a step that passed: the loop
would have stopped. In parallel, a missing exit-code file is just… a missing file, and
the tempting reading of *"nothing said it failed"* is **"it passed"**.

It is not. *"Did not measure"* is never *"passed"* — the same rule this repository keeps
re-learning about skips, empty windows and vacuous checks, arriving here in a new shape.

## This file DRIVES the gate's verdict rather than reading its source

`pre-push --read-run DIR` reports on a run directory that already exists, **without
running a single suite**. So the three cases below are executed against the real script:
every step reported zero; one step reported a non-zero code; one step reported nothing at
all. A node that grepped the hook for an `if` would be the `G-1` defect — describing a
shape instead of driving a behaviour — and it would keep passing if the branch were
rewritten to treat the missing file as fine.

## Absence skips, loudly

Without `bash` the script cannot be asked anything, and reporting that as a broken gate
would be red for something this node does not guard.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

#: `tests/contract/` -> `tests/` -> package -> `packages/` -> repository.
REPO = Path(__file__).resolve().parents[4]
HOOK = REPO / "tools" / "git-hooks" / "pre-push"


def _read_run(directory: Path) -> subprocess.CompletedProcess[str]:
    """Drive the gate's verdict over a prepared run directory."""
    if not HOOK.exists():  # pragma: no cover - a checkout without the hook
        pytest.skip("tools/git-hooks/pre-push is not in this checkout; nothing was measured")
    bash = shutil.which("bash")
    if bash is None:  # pragma: no cover - a machine without a POSIX shell
        pytest.skip("no bash on this machine; the gate could not be asked for a verdict")
    return subprocess.run(
        [bash, str(HOOK), "--read-run", str(directory)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_directory(tmp_path: Path, *, steps: int = 2) -> Path:
    """A finished run where every step passed, with one skip recorded on the first."""
    directory = tmp_path / "runs"
    directory.mkdir()
    (directory / "jobs").write_text(
        "\n".join(f"suite-{index}" for index in range(1, steps + 1)) + "\n", encoding="utf-8"
    )
    for index in range(1, steps + 1):
        skipped = ", 3 skipped" if index == 1 else ""
        (directory / f"{index}.out").write_text(f"10 passed{skipped} in 1.00s\n", encoding="utf-8")
        (directory / f"{index}.rc").write_text("0\n", encoding="utf-8")
    return directory


def test_a_finished_run_where_everything_passed_is_a_pass(tmp_path: Path) -> None:
    """The premise. Without it the two refusals below could be refusing everything."""
    result = _read_run(_run_directory(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_step_that_reported_a_non_zero_code_blocks(tmp_path: Path) -> None:
    """The ordinary failure, still asserted: the gate must not have stopped reading codes."""
    directory = _run_directory(tmp_path)
    (directory / "2.rc").write_text("7\n", encoding="utf-8")
    result = _read_run(directory)
    assert result.returncode == 1
    assert "FAILED, exit 7" in result.stdout + result.stderr


def test_a_step_that_reported_nothing_at_all_blocks(tmp_path: Path) -> None:
    """**The one parallelism introduced, and the reason this file exists.**

    A missing exit-code file means the step did not report. Reading that as a pass would
    let a whole suite vanish from the gate without anything going red — the failure mode
    that is invisible precisely because nothing is there to see.
    """
    directory = _run_directory(tmp_path)
    (directory / "2.rc").unlink()
    result = _read_run(directory)
    assert result.returncode == 1, (
        "the gate reported a pass for a run where a step never wrote an exit code. "
        "'Did not measure' is not 'passed'."
    )
    # The wording moved on 2026-09-03 (S-42) and the PROPERTY did not: a step that never
    # reported still blocks. What changed is that the gate now says WHY — a job with no exit
    # code did not fail a test, it died before it could write one, and those two ask for
    # opposite actions. Both halves are asserted here so neither can be dropped: it must
    # still name the missing exit code, and it must name the machine as the cause.
    reported = result.stdout + result.stderr
    assert "never reported an exit code" in reported, reported
    assert "MACHINE FAILURE" in reported, reported


def test_the_skip_total_is_read_from_the_files_and_is_reported(tmp_path: Path) -> None:
    """The skip count, which is what made the `J-1` objection dissolve.

    Each step already writes its output to a file, so the total is read from files rather
    than piped out of a command whose exit code matters. The number is REPORTED — which is
    not the same as tolerated, and is what a reader needs to know what the gate did not
    measure.
    """
    directory = _run_directory(tmp_path)
    (directory / "2.out").write_text("4 passed, 5 skipped in 1.00s\n", encoding="utf-8")
    result = _read_run(directory)
    assert result.returncode == 0
    assert "8 test(s) skipped" in result.stdout, result.stdout


def test_the_gate_refuses_a_run_directory_it_cannot_read(tmp_path: Path) -> None:
    """A directory with no job list is not an empty run — it is an unreadable one.

    Reporting *"zero steps, all green"* over a directory the gate could not understand is
    the vacuous pass in yet another costume.
    """
    empty = tmp_path / "not-a-run"
    empty.mkdir()
    result = _read_run(empty)
    assert result.returncode == 2, result.stdout + result.stderr


#: The suite that declares a node floor, and the only one that does today.
FLOORED = "apps/telegram-bot"


def _declared_floor() -> int:
    """The floor, ASKED OF THE HOOK rather than copied into this file.

    It used to be a literal here beside the hook's own literal, and that is the `F136`
    shape: the same figure declared in two places, where the copy ages silently and the
    node goes on passing against a number nobody uses. The hook prints it on demand, so
    moving the floor there moves what this file asserts against, and a floor that moves in
    one place only cannot happen.
    """
    if not HOOK.exists():  # pragma: no cover - a checkout without the hook
        pytest.skip("tools/git-hooks/pre-push is not in this checkout; nothing was measured")
    bash = shutil.which("bash")
    if bash is None:  # pragma: no cover - a machine without a POSIX shell
        pytest.skip("no bash on this machine; the gate could not be asked for its floor")
    printed = subprocess.run(
        [bash, str(HOOK), "--floor-for", FLOORED],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    assert printed.isdigit(), (
        f"the hook printed {printed!r} as the floor for {FLOORED}, which is not a number; "
        "a floor that cannot be read is a floor that is not applied"
    )
    return int(printed)


def _floored_run(tmp_path: Path, summary: str) -> Path:
    """A finished run holding one step: the suite that declares a floor."""
    directory = tmp_path / "runs"
    directory.mkdir()
    (directory / "jobs").write_text(f"{FLOORED}\n", encoding="utf-8")
    (directory / "1.out").write_text(summary, encoding="utf-8")
    (directory / "1.rc").write_text("0\n", encoding="utf-8")
    return directory


def test_a_suite_at_its_floor_passes(tmp_path: Path) -> None:
    """The premise. A floor that refused its own measurement would refuse everything."""
    floor = _declared_floor()
    result = _read_run(_floored_run(tmp_path, f"{floor} passed in 25.83s\n"))
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_suite_below_its_floor_blocks(tmp_path: Path) -> None:
    """**The guard the push gate did not have, in the gate that runs without being asked.**

    `harness.yml` carried a floor and `run_local_ci.py` DOES execute it -- the guard was
    alive, but only through a door somebody opens by hand, and it was thirty-nine nodes
    behind the suite besides. This gate, the one that runs on every push, counted nothing:
    a push deleting a test was green here.

    One node short of the floor must block, and the refusal must name BOTH numbers, because
    *a node vanished* and *the floor is stale* are different decisions and the reader is the
    one who has to tell them apart.
    """
    floor = _declared_floor()
    short = floor - 1
    result = _read_run(_floored_run(tmp_path, f"{short} passed in 25.83s\n"))
    assert result.returncode == 1, (
        "a suite came back below its declared floor and the gate reported a pass; a node "
        "vanished and nothing said so"
    )
    combined = result.stdout + result.stderr
    assert "BELOW THE FLOOR" in combined
    assert str(short) in combined and str(floor) in combined, (
        "the refusal does not name both numbers, so a reader cannot tell whether a node "
        "vanished or the floor is stale"
    )


def test_a_suite_whose_count_cannot_be_read_blocks(tmp_path: Path) -> None:
    """**A count that cannot be read is a failure**, exactly like a missing exit code.

    Same rule, same place, same reason: *did not measure* is never *passed*. A summary
    line the gate cannot parse would otherwise slip past the floor in silence.
    """
    result = _read_run(_floored_run(tmp_path, "the run produced no summary line\n"))
    assert result.returncode == 1
    assert "NO NODE COUNT COULD BE READ" in result.stdout + result.stderr


def test_a_suite_with_no_declared_floor_is_not_invented_one(tmp_path: Path) -> None:
    """**Only one suite declares a floor, and the others are not silently given one.**

    Six suites are gated for pass/fail and NOT for disappearance. That is a real gap and
    it is named in the hook rather than implied — inventing a floor here would make this
    file assert coverage the repository does not have.
    """
    directory = tmp_path / "runs"
    directory.mkdir()
    (directory / "jobs").write_text("packages/semantic_catalog\n", encoding="utf-8")
    (directory / "1.out").write_text("3 passed in 1.00s\n", encoding="utf-8")
    (directory / "1.rc").write_text("0\n", encoding="utf-8")
    result = _read_run(directory)
    assert result.returncode == 0, (
        "a suite with no declared floor was refused, so a floor was invented for it"
    )


# --------------------------------------------------------------------------- #
# THE FLOOR MEASURES WHAT WAS COLLECTED, AND THAT CHANGED ON 2026-08-28.
#
# It compared `passed`, and on that day it blocked every push on the pushing machine with
# 971 passed and 4 skipped against a floor of 974 -- while the suite COLLECTED 975, one
# MORE than the floor. Nothing had vanished and the floor was not stale. The cause was a
# third thing the old message could not express: FOUR NODES THAT EXIST AND COULD NOT RUN
# THERE, because the BigQuery credential had lapsed.
#
# And the number carried an UNWRITTEN PRE-CONDITION -- `F136`. The hook's own comment says
# 974 came from *the run that reports ZERO skipped*, a run that only exists with a live
# credential, so the floor silently required one and nothing said so.
#
# The nodes below hold the new comparison. The two above still hold, unchanged: a summary
# with no skips has `collected == passed`, so they measure the same thing they always did.
# --------------------------------------------------------------------------- #


def test_a_suite_that_reaches_its_floor_only_with_its_skips_passes(tmp_path: Path) -> None:
    """**The case that blocked every push on 2026-08-28**, and it must not.

    Nodes that exist and could not run here are still nodes that exist. Below the floor on
    `passed`, at the floor on `collected` -- and the second is the number that answers *did
    a node disappear*.
    """
    floor = _declared_floor()
    summary = f"{floor - 4} passed, 4 skipped in 107.53s (0:01:47)\n"
    result = _read_run(_floored_run(tmp_path, summary))
    assert result.returncode == 0, (
        "a suite at its floor by collected count was refused for having skipped nodes; the "
        "floor would then require a live credential on the pushing machine, which is a "
        f"pre-condition nobody wrote down\n{result.stdout}{result.stderr}"
    )


def test_a_deleted_node_still_blocks_even_when_skips_are_present(tmp_path: Path) -> None:
    """**The property the floor exists for, and it survives the change.**

    Counting skips as collected must NOT buy a deleted node a free pass. One short of the
    floor by collected count blocks, whatever the split between passed and skipped is.
    """
    floor = _declared_floor()
    summary = f"{floor - 5} passed, 4 skipped in 107.53s\n"
    result = _read_run(_floored_run(tmp_path, summary))
    assert result.returncode == 1, (
        "a node was deleted and the gate reported a pass because skips padded the count"
    )
    combined = result.stdout + result.stderr
    assert "BELOW THE FLOOR" in combined
    assert f"{floor - 1} collected" in combined, (
        "the refusal does not name the COLLECTED count, so a reader cannot tell what was "
        f"compared\n{combined}"
    )
    assert str(floor) in combined


def test_the_refusal_names_the_third_cause_and_rules_it_out(tmp_path: Path) -> None:
    """**Three causes, not two**, and the reader is told which one this cannot be.

    The old message offered *a node vanished* and *the floor is stale*, and on 2026-08-28
    neither was true. A reader who has just seen four skips needs to be told, in the
    refusal itself, that the skips are not what blocked them.
    """
    floor = _declared_floor()
    result = _read_run(_floored_run(tmp_path, f"{floor - 1} passed in 25.83s\n"))
    combined = result.stdout + result.stderr
    assert "DELETED" in combined, "the refusal does not name deletion as a cause"
    assert "stale" in combined, "the refusal does not name a stale floor as a cause"
    assert "could not run here" in combined, (
        "the refusal does not name the third cause, so the reader who just saw skips is "
        f"left to guess whether they caused this\n{combined}"
    )


def test_a_suite_that_only_skipped_is_read_rather_than_called_unreadable(
    tmp_path: Path,
) -> None:
    """A summary with no `passed` at all is still a count, and the gate must read it.

    Pytest prints `N skipped in ...` with no passed clause when everything skipped. Calling
    that unreadable would turn *the whole suite could not run* into *the gate broke*, which
    are different problems for the person reading.
    """
    floor = _declared_floor()
    result = _read_run(_floored_run(tmp_path, f"{floor} skipped in 25.83s\n"))
    assert "NO NODE COUNT COULD BE READ" not in (result.stdout + result.stderr), (
        "a skipped-only summary was reported as unreadable rather than counted"
    )
    assert result.returncode == 0, result.stdout + result.stderr
