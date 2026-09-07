"""The upstream node-ID guard, as a contract — T175 (FR-057; SC-032).

    Evidence: the three existing workflows are untouched. — `tasks.md` T175

## The defect this file exists because of

The guard's first version checked `packages/` out of the baseline commit **over the
current tree**:

```
git checkout "$base" -- packages
```

On a `push` that is harmless — the previous commit contains every package. On a
`pull_request` the base is `main`, which has no `packages/analytics_interaction` and no
`analytics_query.execute`. Reverting `packages/` there leaves the current 003 in the tree,
installed editable against an `analytics_query` that no longer has the module it imports.
Pytest exited **2** during collection, before the comparison ran — and because `collect()`
redirected all of pytest's output into a file, the log showed nothing but the exit code.

Two failures in one: a mixed, uncollectable tree, and a tooling error that looked like a
guard result.

## What the corrected guard must do, and what these tests assert

The invariant is unchanged: **every 001 and 002 node ID present at the baseline must still
be present at the head**, additive tests allowed, and every preserved node must actually
run and pass.

What changed is how the baseline is obtained — an isolated `git worktree` under
`RUNNER_TEMP` with its own virtual environment, so the head checkout is never modified and
baseline collection resolves baseline sources rather than the head's editable installs.

These are **contract tests over the workflow**, not a re-implementation of it. Two kinds:

* **structural** — parse `nl-analytics.yml` and assert the shape that makes the failure
  impossible: no checkout over `packages/`, a worktree under `RUNNER_TEMP`, a separate
  interpreter, 003 absent from the collected set, a cleanup trap, no total-count equality;
* **behavioural** — extract the baseline-resolution block and **run it under bash** with
  synthesised event inputs, so "push uses `before`", "all-zero falls back" and "an
  unresolvable baseline fails loudly" are executed rather than described.

Bash is required rather than optional. The guard *is* a bash script; a machine that cannot
run bash cannot validate it, and reporting that as a skip would be reporting an unrun check
as a passing one.
"""

from __future__ import annotations

import inspect
import os
import re
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

import analytics_interaction

pytestmark = pytest.mark.contract

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent
REPO = SRC.parents[3]
WORKFLOWS = REPO / ".github" / "workflows"
GUARD = WORKFLOWS / "nl-analytics.yml"

#: The three workflows `T175` must leave alone.
PRE_EXISTING = ("catalog.yml", "analytics-query.yml", "readiness-guard.yml")

#: Every workflow this guard protects: the three `T175` must leave alone, plus `003`'s own.
#:
#: **Protection is inclusion and integrity, never cardinality.** The first form of the
#: assertion below compared the directory's `*.yml` set for **equality** with this set,
#: which turned the repository's momentary workflow count into a permanent contract: a
#: later feature adding an independent workflow failed it without touching anything
#: protected. `004` discovered that (ADR 0024).
#:
#: The rule that replaced it holds for any number of workflows, so a sixth needs no edit
#: here. What it does **not** become is a licence to change an existing workflow: each
#: protected path must still exist, at its own name, structurally intact, and every
#: content assertion in this module still reads `nl-analytics.yml` directly.
PROTECTED_WORKFLOWS = (*PRE_EXISTING, "nl-analytics.yml")

#: The upstream packages the guard compares. `analytics_interaction` is deliberately
#: absent: it does not exist at a `pull_request` baseline, and collecting the current one
#: against base `analytics_query` is precisely what broke.
UPSTREAM = ("semantic_catalog", "analytics_query")


def _workflow() -> dict[str, Any]:
    loaded: object = yaml.safe_load(GUARD.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return cast("dict[str, Any]", loaded)


def _steps() -> list[dict[str, Any]]:
    jobs = cast("dict[str, Any]", _workflow()["jobs"])
    return cast("list[dict[str, Any]]", jobs["nl-analytics"]["steps"])


def _step(fragment: str) -> dict[str, Any]:
    matches = [s for s in _steps() if fragment.lower() in str(s.get("name", "")).lower()]
    assert len(matches) == 1, (
        f"expected exactly one step matching {fragment!r}, found {len(matches)}"
    )
    return matches[0]


def _script(fragment: str) -> str:
    return str(_step(fragment)["run"])


def _bash(script: str, **env: str) -> subprocess.CompletedProcess[str]:
    """Run a shell fragment, returning the completed process.

    ``bash`` is looked up rather than assumed at a path, and its absence fails the test.
    The guard is a bash script; a machine that cannot run bash cannot validate it, and a
    skip here would report an unrun check as a passing one.
    """
    executable = shutil.which("bash")
    assert executable, "bash is required to validate a bash workflow step"
    # The ambient environment is inherited rather than stubbed: the block calls `git`, and
    # a minimal PATH found no interpreter on Windows -- which made every resolution test
    # fail for a reason that had nothing to do with the logic under test.
    return subprocess.run(
        [executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **env},
    )


# --- the workflow is well-formed and leaves the others alone --------------------


def test_the_workflow_parses_and_declares_one_job() -> None:
    """A malformed workflow would make every assertion below vacuous."""
    workflow = _workflow()
    assert set(workflow["jobs"]) == {"nl-analytics"}
    assert _steps()


def absent_protected_workflows(
    present: Iterable[str], protected: Iterable[str] = PROTECTED_WORKFLOWS
) -> list[str]:
    """Protected names missing from ``present``. Empty means intact.

    A pure predicate over names, so the rule can be driven with synthetic sets rather than
    only observed on the current tree — which is what makes "the rule does not depend on
    the current workflow count" assertable instead of merely stated.

    **Inclusion, deliberately not equality.** An unprotected name in ``present`` is not a
    finding: a later feature may add its own workflow. A protected name *missing* from
    ``present`` always is, and no other file can satisfy it — the comparison is by exact
    name, so an equivalent copy under a different name reports the protected path as absent.
    """
    names = set(present)
    return sorted(name for name in protected if name not in names)


def assert_workflow_intact(path: Path) -> None:
    """``path`` is a real workflow file, structurally whole.

    Presence alone would let a protected workflow be replaced by an empty file or a symlink
    to something else and still pass. Structural rather than byte-exact on purpose: the
    three pre-existing workflows belong to `001` and `002` and may legitimately change
    under their own gates. What this guard owns is that **`003` left them there and left
    them working**, and — for `nl-analytics.yml` — every content assertion in this module
    still reads the file directly.
    """
    assert path.is_file(), f"{path.name} is missing"
    assert not path.is_symlink(), f"{path.name} is a symlink, not the protected file"
    text = path.read_text(encoding="utf-8")
    assert text.strip(), f"{path.name} is empty"
    loaded: object = yaml.safe_load(text)
    assert isinstance(loaded, dict), f"{path.name} does not parse as a workflow mapping"
    document = cast("dict[str, Any]", loaded)
    assert document.get("jobs"), f"{path.name} declares no job"
    assert "on" in document or True in document, f"{path.name} declares no trigger"


def test_the_three_pre_existing_workflows_are_untouched() -> None:
    """`T175`'s named evidence. This workflow is additive.

    **Name and node ID preserved; the premise corrected** (ADR 0024). The obligation is
    unchanged — every pre-existing workflow is still present and still intact — but it is
    now expressed as **inclusion and integrity** rather than as equality over the
    directory's `*.yml` set. The old form made the repository's momentary workflow count a
    permanent contract and failed on an additive workflow from a later feature that touched
    nothing protected.
    """
    for name in PRE_EXISTING:
        assert (WORKFLOWS / name).is_file(), name

    present = {p.name for p in WORKFLOWS.glob("*.yml")}
    assert not absent_protected_workflows(present), absent_protected_workflows(present)

    for name in PROTECTED_WORKFLOWS:
        assert_workflow_intact(WORKFLOWS / name)


# --- adversarial regressions for the corrected premise (ADR 0024) ---------------
#
# Driven with synthetic name sets and temporary directories, so each rule is shown to fail
# on a real violation rather than merely to pass on the current tree.


def test_every_protected_workflow_is_mandatory() -> None:
    """(1) All four protected names are required, individually."""
    assert set(PRE_EXISTING) <= set(PROTECTED_WORKFLOWS)
    assert "nl-analytics.yml" in PROTECTED_WORKFLOWS
    assert not absent_protected_workflows(PROTECTED_WORKFLOWS)
    for name in PROTECTED_WORKFLOWS:
        without = [other for other in PROTECTED_WORKFLOWS if other != name]
        assert absent_protected_workflows(without) == [name]


def test_removing_a_protected_workflow_fails() -> None:
    """(2) Deletion is always a finding, whatever else is present."""
    present = {name for name in PROTECTED_WORKFLOWS if name != "catalog.yml"}
    assert absent_protected_workflows(present) == ["catalog.yml"]
    present |= {"multichannel.yml", "future-feature.yml"}
    assert absent_protected_workflows(present) == ["catalog.yml"], (
        "adding workflows must not compensate for a removed protected one"
    )


def test_renaming_a_protected_workflow_fails() -> None:
    """(3) A rename is a removal plus an addition, and the removal still fails."""
    present = {name for name in PROTECTED_WORKFLOWS if name != "readiness-guard.yml"}
    present.add("readiness-guard-v2.yml")
    assert absent_protected_workflows(present) == ["readiness-guard.yml"]


def test_adding_an_independent_workflow_does_not_invalidate_the_guard() -> None:
    """(4) The case the old premise broke on: `004`'s additive workflow."""
    present = {*PROTECTED_WORKFLOWS, "multichannel.yml"}
    assert not absent_protected_workflows(present)


def test_an_equivalent_new_file_does_not_substitute_a_protected_path(tmp_path: Path) -> None:
    """(5) Equivalent content under another name satisfies nothing.

    Matching is by exact name, so a copy cannot mask an absence — and a symlink or an empty
    file at the protected path cannot either.
    """
    original = (WORKFLOWS / "catalog.yml").read_text(encoding="utf-8")
    present = {name for name in PROTECTED_WORKFLOWS if name != "catalog.yml"}
    present.add("catalog-copy.yml")
    assert absent_protected_workflows(present) == ["catalog.yml"]

    hollow = tmp_path / "catalog.yml"
    hollow.write_text("", encoding="utf-8")
    with pytest.raises(AssertionError, match="is empty"):
        assert_workflow_intact(hollow)

    jobless = tmp_path / "jobless.yml"
    jobless.write_text("on: push\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="declares no job"):
        assert_workflow_intact(jobless)

    assert original.strip(), "the protected workflow read for this test is non-empty"


def test_changing_protected_content_is_still_detected_by_the_existing_guards() -> None:
    """(6) The correction relaxed cardinality, not content.

    Two facts together: this module still carries many assertions that read
    `nl-analytics.yml`'s own content, and structural corruption of a protected file still
    fails :func:`assert_workflow_intact`.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    content_readers = [
        name
        for name, member in sorted(globals().items())
        if name.startswith("test_")
        and callable(member)
        and any(
            token in inspect.getsource(cast("Any", member))
            for token in ("_script(", "_step(", "_steps(", "_workflow(")
        )
    ]
    assert len(content_readers) >= 10, (
        f"only {len(content_readers)} content assertions remain over the protected workflow"
    )
    assert "GUARD = WORKFLOWS /" in source, "the protected workflow is still read by path"


def test_the_rule_does_not_depend_on_the_current_workflow_count() -> None:
    """(7) Any number of workflows satisfies the rule while the protected set is present."""
    for extra in (0, 1, 2, 10, 50):
        present = {*PROTECTED_WORKFLOWS, *(f"feature-{index}.yml" for index in range(extra))}
        assert not absent_protected_workflows(present), f"failed with {extra} extra workflows"


def test_a_future_sixth_workflow_would_need_no_change_here() -> None:
    """(8) The premise that expired must not be able to come back.

    Asserted over this module's own source: no equality comparison over the directory's
    `*.yml` set may exist, in this test or any other. That is the shape the expired premise
    had, and the reason it expired.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    # Assembled from fragments rather than written out: a scanner whose pattern list is
    # itself a match would flag its own source, which is the same self-reference defect the
    # expired premise had in a different form.
    glob_call = 'glob("*.yml")'
    for forbidden in (
        glob_call + "} ==",
        glob_call.replace('"', "'") + "} ==",
        glob_call + ") ==",
        "len(list(WORKFLOWS." + "glob",
    ):
        assert forbidden not in source, f"a closed-cardinality premise reappeared: {forbidden}"

    sixth = {*PROTECTED_WORKFLOWS, "multichannel.yml", "proactive-insights.yml"}
    assert not absent_protected_workflows(sixth)


# --- 10. no current-head tracked path is overwritten ----------------------------


def test_no_step_checks_a_commit_out_over_the_current_tree() -> None:
    """**The defect, forbidden structurally.**

    `git checkout <sha> -- packages` is what produced the mixed tree. No step may do it,
    and no step may stash the working tree either — the previous version did both, and a
    stash that failed to pop would leave the head checkout altered for every later step.
    """
    for step in _steps():
        script = str(step.get("run", ""))
        assert not re.search(r"git\s+checkout\s+[^\n]*--\s+packages", script), step.get("name")
        assert "git stash" not in script, step.get("name")


def test_the_baseline_is_read_from_an_isolated_worktree() -> None:
    script = _script("node-ID preservation")
    assert "git worktree add --detach" in script
    assert 'worktree="$RUNNER_TEMP/' in script
    assert 'venv="$RUNNER_TEMP/' in script


def test_the_guard_writes_only_under_runner_temp() -> None:
    """Every file the step creates is scoped to the runner's temporary directory.

    The previous version wrote to `/tmp/...` by absolute path. Scoping to `RUNNER_TEMP`
    keeps the artefacts with the job and keeps the cleanup honest -- it can remove what it
    made without a broad `rm -rf` anywhere else.

    Asserted on the **path assignments** rather than on the redirect targets. Redirects go
    through locals (`> "$raw"`), so matching them would only prove that a variable was
    used; where the variable points is the claim.
    """
    script = _script("node-ID preservation")

    assignments = re.findall(r'^\s*(?:local\s+)?(\w+)="([^"]*/[^"]*)"', script, re.M)
    paths = [(name, value) for name, value in assignments if "/" in value]
    assert paths, "the guard assigns no paths; the extraction is probably wrong"

    # Ciclo 497: `renames` aponta para o mapa versionado de renames declarados
    # (.github/upstream-node-renames.txt) -- CONSUMIDO, nunca escrito. A excecao e por
    # NOME e por prefixo, e o instrumento novo logo abaixo garante a metade que importa:
    # o passo nao redireciona nada para dentro do workspace.
    for name, value in paths:
        if name == "renames":
            assert value.startswith(("$GITHUB_WORKSPACE/", "${GITHUB_WORKSPACE}/")), (name, value)
            continue
        assert value.startswith(("$RUNNER_TEMP/", "${RUNNER_TEMP}/", "$venv/")), (name, value)

    # And no absolute literal outside it, which is what the old step used.
    assert not re.search(r"(?<![\w$])/tmp/", script)

    # A leitura e permitida; a escrita nao: nenhum redirect aponta para o workspace
    # nem para o proprio mapa.
    assert not re.search(r">{1,2}\s*\S*GITHUB_WORKSPACE", script)
    assert not re.search(r">{1,2}\s*\S*renames", script)


# --- 1 & 2. 003 is never collected from, or against, the baseline ---------------


def test_the_guard_collects_only_the_two_upstream_packages() -> None:
    """**A `pull_request` baseline has no `analytics_interaction`, and needs none.**

    The loop names the two upstream packages explicitly. A glob over `packages/` would pick
    up 003 at a `push` baseline — where it does exist — and collect it against base 002
    code, which is the import that failed.
    """
    script = _script("node-ID preservation")
    assert "for package in semantic_catalog analytics_query; do" in script

    loop = script[script.index("failed=0") :]
    assert "analytics_interaction" not in loop.split("# 003 is deliberately absent")[0]


def test_the_guard_states_why_003_is_absent_even_when_present_at_the_baseline() -> None:
    """A `push` baseline *does* contain 003, and it is still not collected.

    Asserted because "the loop happens to name two packages" and "003 is deliberately
    excluded" are different claims, and only the second survives somebody adding a third
    upstream package.
    """
    script = _script("node-ID preservation")
    assert "003 is deliberately absent from the loop" in script
    assert "it is still not collected from there, by design" in script


def test_baseline_collection_uses_a_separate_interpreter() -> None:
    """So the baseline resolves baseline sources, not the head's editable installs.

    Same-interpreter collection would import the head's `analytics_query` while claiming to
    describe the baseline's — a silent wrong answer rather than a loud failure.
    """
    script = _script("node-ID preservation")
    assert 'python -m venv "$venv"' in script
    assert 'baseline_python="$venv/bin/python"' in script
    assert 'collect baseline "$baseline_python" "$worktree"' in script
    assert 'collect current "$(command -v python)" "$GITHUB_WORKSPACE"' in script


def test_collection_is_insulated_from_ambient_state() -> None:
    """`PYTHONPATH` cleared, no bytecode, no pytest cache.

    Three ways the head could leak into a baseline collection, each closed where the
    command runs rather than in a preamble somebody could move.
    """
    script = _script("node-ID preservation")
    assert "PYTHONPATH= PYTHONDONTWRITEBYTECODE=1" in script
    assert "-p no:cacheprovider" in script
    assert "-p no:randomly" in script


# --- 3, 4, 5. baseline selection, executed ------------------------------------


def _resolution_script(event: str, pr_base: str, push_before: str) -> str:
    """The workflow's own resolution block, with the event inputs substituted.

    Extracted from the YAML rather than retyped: a copy would drift, and the drifted copy
    would be the one the tests passed against.
    """
    body = _script("Resolve the upstream baseline")
    body = body.replace("${{ github.event_name }}", event)
    body = body.replace("${{ github.event.pull_request.base.sha }}", pr_base)
    body = body.replace("${{ github.event.before }}", push_before)
    # `git cat-file` and `$GITHUB_OUTPUT` are the only environment this needs.
    return f'cd "{REPO.as_posix()}"\nexport GITHUB_OUTPUT=/dev/null\n{body}'


HEAD = "d7eaea8561dcda1cb4b641e6ae85dbbd8743701a"
MAIN = "b668ae16fc0c7c3efbd464fac1db3616f3e99623"
PREVIOUS = "a584198"
ZERO = "0" * 40


def test_a_pull_request_uses_the_base_sha() -> None:
    """The base the PR would merge into, even though it predates this feature."""
    result = _bash(_resolution_script("pull_request", MAIN, ""))
    assert result.returncode == 0, result.stderr
    assert MAIN in result.stdout
    assert "pull_request.base.sha" in result.stdout


def test_a_push_uses_the_before_sha() -> None:
    """**Requirement 3.** Not `HEAD^` — the event says which commit preceded this one."""
    result = _bash(_resolution_script("push", "", PREVIOUS))
    assert result.returncode == 0, result.stderr
    assert PREVIOUS in result.stdout
    assert "push.before" in result.stdout
    assert "fallback" not in result.stdout


def test_an_all_zero_before_sha_uses_the_documented_fallback() -> None:
    """**Requirement 4.** A branch's first push reports all zeros.

    `HEAD^` is the fallback and says so in its own origin string, so a log reader can tell a
    fallback baseline from a reported one without reading the workflow.
    """
    result = _bash(_resolution_script("push", "", ZERO))
    assert result.returncode == 0, result.stderr
    assert "fallback" in result.stdout
    assert "all-zero" in result.stdout
    assert ZERO not in result.stdout


def test_an_absent_before_sha_uses_the_same_fallback() -> None:
    """An empty `before` is the other shape of the same situation."""
    result = _bash(_resolution_script("push", "", ""))
    assert result.returncode == 0, result.stderr
    assert "fallback" in result.stdout


def test_an_unresolvable_baseline_fails_with_a_diagnostic() -> None:
    """**Requirement 5.** No baseline means no guard, and that must be loud.

    The failure this forecloses is the quiet one: an unresolved baseline treated as "nothing
    to compare", which passes while checking nothing.
    """
    unsupported = _bash(_resolution_script("schedule", "", ""))
    assert unsupported.returncode != 0
    assert "::error::no upstream baseline could be resolved" in unsupported.stdout
    assert "unsupported event: schedule" in unsupported.stdout


def test_a_baseline_that_is_not_a_commit_fails() -> None:
    """A well-formed SHA that this repository does not contain is still unusable."""
    absent = "0" * 39 + "1"
    result = _bash(_resolution_script("pull_request", absent, ""))
    assert result.returncode != 0
    assert "is not a commit in this repository" in result.stdout


# --- 6, 7, 8. regression and tooling failures are distinguishable ---------------


def test_a_vanished_node_emits_one_error_line_per_node() -> None:
    """**Requirement 6.** A real regression, named node by node.

    One `::error::` per node rather than a blob, so GitHub annotates each and a reviewer
    reads what vanished instead of a count.
    """
    script = _script("node-ID preservation")
    assert "NODE-ID REGRESSION" in script
    assert "while IFS= read -r node; do" in script
    assert '<<< "$missing"' in script


def test_a_collection_failure_is_labelled_as_one() -> None:
    """**Requirements 7 and 8.** Tooling failure, with the side named.

    `COLLECTION FAILURE (baseline side)` and `(current side)` are different problems: the
    first means the comparison could not be made, the second means the head is broken. The
    original step could report neither — it exited 2 with an empty log.
    """
    script = _script("node-ID preservation")
    assert "COLLECTION FAILURE ($label side)" in script
    assert "collect baseline " in script
    assert "collect current " in script
    assert 'echo "::error::TOOLING:' in script


def test_a_collection_failure_prints_package_side_sha_and_exit_code() -> None:
    """All four, because any one alone leaves a reader guessing which run failed."""
    script = _script("node-ID preservation")
    marker = "package=$package commit=$sha exit=$status"
    assert marker in script


def test_pytest_diagnostics_are_printed_rather_than_swallowed() -> None:
    """**The second half of the original defect.**

    The old `collect()` sent stdout into the redirect file, so a collection error left the
    log with an exit code and nothing else. The corrected one captures output to a file
    *and* prints an excerpt on failure.
    """
    script = _script("node-ID preservation")
    assert "pytest collection diagnostics" in script
    assert "--- end diagnostics ---" in script
    assert re.search(r'(grep -E[^\n]*\$raw[^\n]*head|tail -25 "\$raw")', script)


def test_an_empty_collection_is_a_failure_rather_than_an_empty_set() -> None:
    """Zero collected nodes would make the subset comparison pass vacuously."""
    script = _script("node-ID preservation")
    assert 'if [ ! -s "$out" ]; then' in script
    assert "collected zero nodes" in script


# --- 9. additive tests pass; no count equality ---------------------------------


def test_the_comparison_is_a_subset_check_not_an_equality() -> None:
    """**Requirement 9.** Additive suites are expected and must not fail the gate.

    `comm -23` is the baseline-minus-current direction: nodes that vanished. The other
    direction is reported as `additive` and never gates.
    """
    script = _script("node-ID preservation")
    assert 'missing="$(comm -23 "$base_ids" "$head_ids"' in script
    assert 'added="$(comm -13 "$base_ids" "$head_ids"' in script
    assert 'if [ -n "$missing" ]; then' in script
    assert not re.search(r'\[\s*"\$base_count"\s*(-eq|==)\s*"\$head_count"', script)


def test_all_four_counts_are_reported_per_package() -> None:
    """Baseline, current, missing and additive — for each package, independently."""
    script = _script("node-ID preservation")
    # Split so the assertion fits, and checked as a sequence so the four counts must appear
    # on one line in this order -- four separate `in` checks would pass for four counts
    # scattered across four different messages.
    line = (
        'echo "$package: baseline=$base_count current=$head_count '
        'missing=$missing_count additive=$added_count"'
    )
    assert line in script


def test_each_package_is_compared_independently() -> None:
    """A merged comparison would let one package's additions mask another's loss."""
    script = _script("node-ID preservation")
    assert 'base_ids="$RUNNER_TEMP/${package}-base.txt"' in script
    assert 'head_ids="$RUNNER_TEMP/${package}-head.txt"' in script


def test_a_failure_in_one_package_does_not_stop_the_other() -> None:
    """Both packages are reported before the step exits.

    `failed=1; continue` rather than an immediate exit, so one broken collection does not
    hide the second package's result and send somebody round the loop twice.
    """
    script = _script("node-ID preservation")
    assert "failed=1" in script
    assert 'exit "$failed"' in script


# --- 11. cleanup happens on success and on failure -----------------------------


def test_cleanup_runs_on_every_exit_path() -> None:
    """**Requirement 11.** A trap, not a trailing command.

    A cleanup line at the end of the script never runs when the script exits early — which
    is exactly when a stale worktree would be left behind.
    """
    script = _script("node-ID preservation")
    assert "trap cleanup EXIT" in script
    assert script.index("cleanup()") < script.index("git worktree add")


def test_cleanup_removes_only_what_the_step_created() -> None:
    """No broad destructive cleanup.

    The worktree is removed by path and the venv by path. An `rm -rf` over a directory the
    step did not create is how a cleanup becomes the incident.
    """
    script = _script("node-ID preservation")
    assert 'git worktree remove --force "$worktree"' in script
    assert 'rm -rf "$venv"' in script
    for destructive in ("rm -rf /", "rm -rf $RUNNER_TEMP\n", "rm -rf .", "git clean"):
        assert destructive not in script, destructive


def test_the_cleanup_trap_is_exercisable() -> None:
    """The trap pattern fires on a failing exit, proven by running it.

    A structural assertion that `trap cleanup EXIT` is present does not prove the trap runs
    when the script fails, so a reduced form of the same pattern is executed here.
    """
    probe = (
        'marker="$(mktemp -d)"\n'
        'cleanup() { rmdir "$marker" && echo CLEANED; }\n'
        "trap cleanup EXIT\n"
        "exit 3\n"
    )
    result = _bash(probe)
    assert result.returncode == 3
    assert "CLEANED" in result.stdout


# --- the preserved nodes actually run ------------------------------------------


def test_the_upstream_suites_are_run_and_checked_for_skips() -> None:
    """A preserved node that is skipped, xfailed or deselected is not preserved.

    Subset-of-collected is only half the invariant. The other half is that the head's
    upstream suites run clean — which, given the subset, means every preserved node passed.
    """
    script = _script("Upstream suites run clean")
    assert "--strict-markers" in script
    assert re.search(r'grep -qE "\[0-9\]\+ \(skipped\|xfailed\|xpassed\|deselected\)"', script) or (
        "skipped|xfailed|xpassed|deselected" in script
    )
    assert "::error::" in script
    for package in UPSTREAM:
        assert package in script


def test_the_guard_runs_after_the_suites_it_depends_on() -> None:
    """Ordering, because a subset check over a red suite proves nothing."""
    names = [str(step.get("name", "")) for step in _steps()]
    suites = names.index(next(n for n in names if "Upstream suites run clean" in n))
    baseline = names.index(next(n for n in names if "Resolve the upstream baseline" in n))
    guard = names.index(next(n for n in names if "node-ID preservation" in n))
    assert suites < baseline < guard


def test_every_gate_is_blocking() -> None:
    """No `continue-on-error`, no `if: always()`. A gate that warns is a gate ignored."""
    for step in _steps():
        assert "continue-on-error" not in step, step.get("name")
        condition = str(step.get("if", ""))
        assert "always()" not in condition, step.get("name")


def test_the_workflow_reaches_no_secret_or_service() -> None:
    """Still fixture-backed: no warehouse, no provider, no credential."""
    text = GUARD.read_text(encoding="utf-8")
    assert "secrets." not in text
    assert "services:" not in text
    for forbidden in ("BIGQUERY", "OPENAI", "ANTHROPIC", "GOOGLE_APPLICATION_CREDENTIALS"):
        assert forbidden not in text, forbidden
