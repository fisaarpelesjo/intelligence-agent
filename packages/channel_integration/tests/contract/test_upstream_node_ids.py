"""T114 — every node ID `T106` captured is still collected, and still runs unfiltered (`SC-057`).

The additive rule of ADR 0017 has a measurable consequence: **zero upstream node removed, zero
renamed**. `T106` captured the pre-change node-ID sets of `001`, `002` and `003` for exactly this
comparison. This is the gate that performs it.

## Two halves, and which one lives here

"Present and passing" is two claims, and this file is explicit about where each is proven.

**Present** is proven here, by collection. Each upstream suite is collected — not run — and its
node-ID set is compared against the baseline, both sides canonicalised so the answer does not depend
on which platform collected them. A vanished or renamed node fails.

That canonicalisation is not cosmetic. The first version of this gate compared raw IDs, passed on
the Windows machine that captured the baseline, and failed on the Linux runner with 1 056 removals
that never happened — review finding W. The fold is documented at :func:`_canonical`, and two tests
below assert that it preserves the invariant rather than hiding behind it.

**Passing** is proven by running each suite here, and separately by asserting that each package's
own workflow runs it unfiltered — no `-k`, no `-m`, no `--deselect`, no `--ignore`. Both halves are
needed: running the suites locally says nothing about whether CI narrows them, and reading the
workflow says nothing about whether they pass.

The third failure mode the task names — a **skipped** node — cannot be seen either way, because a
skip keeps the node ID in the collected set. So it is measured by running: each upstream suite runs
once with `-rs`. An `xfailed`, a `deselected` or an `error` fails outright; a `skipped` is judged
against a declared partition, and a skip outside it fails the same way.

**A static scan was tried first and was wrong.** Prohibiting `pytest.skip` upstream flagged five
conditional guards — `schemas/ not present`, `no message registry is authored yet` — none of which
fires in practice. Those are honest defensive guards in suites this feature does not own, and a gate
that failed on them would be `004` legislating `001`'s test style over a property it was measuring
incorrectly anyway.

**And on 2026-09-03 the dynamic check reproduced that same defect.** `semantic_catalog` gained
credential-gated nodes that measure the real warehouse; the runners hold no credential by design and
each of these workflows says so in its own header. Five honest guards began to FIRE, and three
workflows went red for three days over a suite where nothing was broken — this file legislating
`001`'s test style after all, by the other route. The partition is what separates *a node nobody
classified* from *a node this runner cannot run*: it is compared by FILE AND REASON, never by count,
and it is asked of `tools/git-hooks/pre-push`, the single place all four doors now read. See
:func:`_unexplained_skips`. The invariant below is untouched — none of the five is in the baseline.

**The cost is measured, not estimated**: 62 s for `001`, 4 s for `002`, 41 s for `003`, so about 108
s. That is real and it is accepted, because this file is a Phase D0 **gate** rather than a unit test
— a gate that asserts "passing" by reading a workflow file is asserting somebody's intention.

## Counts are context, never the invariant

The baseline records 1 729, 1 816 and 4 216 nodes. Those numbers appear in failure messages so a
reader can see the scale of a difference, and they are asserted **nowhere**: upstream suites are
expected to grow, and a count equality would fail on a new upstream test that removed nothing. The
invariant is set inclusion in one direction.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

pytestmark = pytest.mark.contract


def _repository_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "packages").is_dir() and (parent / "docs").is_dir():
            return parent
    raise AssertionError("repository root not found")


_ROOT = _repository_root()
_BASELINE = (
    _ROOT / "packages" / "channel_integration" / "tests" / "fixtures" / "upstream_node_ids.json"
)
_WORKFLOWS = _ROOT / ".github" / "workflows"

#: Which workflow runs each upstream package's own full suite. Named per package because the
#: assertion is "this package's suite runs unfiltered somewhere", not "some suite runs somewhere".
_SUITE_WORKFLOW = {
    "semantic_catalog": "catalog.yml",
    "analytics_query": "analytics-query.yml",
    "analytics_interaction": "nl-analytics.yml",
}

#: Options that narrow a run. `--ignore` and `--deselect` remove nodes outright; `-k` and `-m`
#: filter them. Any of these in the whole-suite step would mean the green tick covers less than the
#: suite.
#:
#: Checked against the **arguments**, never the whole command line: every invocation contains
#: `python -m pytest`, so a naive substring search for `-m ` matched all three workflows and
#: reported each of them as narrowed.
_NARROWING = ("-k ", "-m ", "--deselect", "--ignore")

#: Outcome words that mean a collected node did not run AND can never be explained away.
#: `skipped` used to sit here with them, and that is what turned three workflows red for
#: three days -- see :func:`_unexplained_skips` for why it left and what took its place.
#: `xpassed` ENTROU EM 2026-09-06, e nao estava aqui antes de a particao existir -- entao
#: isto nao e regressao de 80b8010, e um buraco que sobreviveu a ela. Nenhum pacote declara
#: `xfail_strict`, entao uma passagem inesperada reporta `1 xpassed` com codigo de saida ZERO
#: e atravessa um no que diz apanhar "um no colhido que nao roda". As portas irmas ja o vetam:
#: `nl-analytics.yml` e `harness.yml` nomeiam `xpassed` nas suas proprias alternacoes.
_NEVER_TOLERATED = ("xfailed", "xpassed", "deselected", "error")


def _unexplained_skips(package: str, output: str) -> list[str]:
    """The SKIPPED lines of ``output`` that fall outside ``package``'s declared partition.

    **Why `skipped` is no longer judged by the summary word alone.**

    This file's own docstring already settled the principle, from the other direction: a
    static scan prohibiting `pytest.skip` upstream was tried, flagged five conditional
    guards -- *"schemas/ not present"*, *"no message registry is authored yet"* -- and was
    discarded because *"those are honest defensive guards in suites this feature does not
    own, and a gate that failed on them would be `004` legislating `001`'s test style"*.

    What changed on 2026-09-03 is that five such guards began to FIRE: `semantic_catalog`
    gained credential-gated nodes that measure the real warehouse, and the runners hold no
    credential by design -- every one of those workflows says so in its own header. So the
    dynamic check reproduced the exact defect the static one was discarded for, and three
    workflows went red on a suite where nothing is broken.

    The invariant is untouched. This module states it twice -- *"the invariant is set
    inclusion in one direction"* and *"counts are context, never the invariant"* -- and
    :func:`test_no_baseline_node_id_vanished_or_was_renamed` is what asserts it. Not one of
    the five skipping nodes is in the `T106` baseline: that set holds 1729 IDs captured on
    2026-08-17, and all five arrived among the ~428 added since.

    So the tolerance is by FILE AND REASON, never by count, and it is **asked of the push
    hook** rather than written here. That is his shape, sanctioned in `catalog.yml` in the
    same commit that introduced the first skip, and the hook is now the single place all
    four doors read. A skip outside the partition stays red, and a suite the hook declares
    no partition for is REFUSED -- silence is never "nothing needed explaining".
    """
    hook = _ROOT / "tools" / "git-hooks" / "pre-push"
    assert hook.is_file(), f"{hook} is not in this checkout; the partition could not be asked"
    bash = shutil.which("bash")
    assert bash is not None, (
        "no bash on this machine, so the declared skip partition could not be read; that is "
        "a failure and not an absence of one"
    )
    judged = subprocess.run(
        (bash, str(hook), "--unexplained-skips", f"packages/{package}"),
        cwd=_ROOT,
        input=output,
        capture_output=True,
        text=True,
        check=False,
    )
    assert judged.returncode == 0, (
        f"the push hook declares no skip partition for packages/{package}, so its skips were "
        f"not judged: {judged.stderr.strip()!r}"
    )
    return [line for line in judged.stdout.splitlines() if line.strip()]


@dataclass(frozen=True, slots=True)
class BaselineEntry:
    """One upstream package's captured node-ID set.

    Typed on the way in rather than read as a mapping of `object`: the count and the list must
    agree, and a validated shape here is what lets every assertion below say what it means.
    """

    package: str
    node_count: int
    node_ids: tuple[str, ...]


def _baseline() -> dict[str, BaselineEntry]:
    document = cast("Mapping[str, object]", json.loads(_BASELINE.read_text(encoding="utf-8")))
    packages = document["packages"]
    assert isinstance(packages, dict), "baseline `packages` is not a mapping"
    typed = cast("Mapping[str, Mapping[str, object]]", packages)

    entries: dict[str, BaselineEntry] = {}
    for feature, raw in typed.items():
        node_ids = raw["node_ids"]
        assert isinstance(node_ids, list), f"{feature}'s node_ids is not a list"
        count = raw["node_count"]
        assert isinstance(count, int), f"{feature}'s node_count is not an integer"
        entries[feature] = BaselineEntry(
            package=str(raw["package"]),
            node_count=count,
            node_ids=tuple(str(node) for node in cast("list[object]", node_ids)),
        )
    return entries


#: Any run of path separators, in either direction. Collapsed to one forward slash on **both** sides
#: of every comparison — review finding W.
_SLASH_RUN = re.compile(r"[\\/]+")


def _canonical(node_id: str) -> str:
    """One node ID in a form that does not depend on which platform collected it.

    `pytest` escapes a backslash inside a parametrised ID, so a path parameter that reads
    ``docs/adr/x.md`` on Linux arrives as ``docs\\\\adr\\\\x.md`` on Windows — two characters per
    separator. `T106` captured on Windows and normalised each of those to a slash, which is why the
    fixture carries ``docs//adr//x.md``; on a Linux runner the same node collects as
    ``docs/adr/x.md`` and the raw sets disagree on 1 056 nodes that nobody removed. That is what
    turned `c7011aa`'s `multichannel` workflow red while this suite was green here.

    Collapsing runs rather than mapping ``\\\\`` to ``/`` is deliberate. Three of `002`'s baseline
    IDs carry a **genuine** ``//`` inside an injection payload, and those must compare equal to
    themselves on both platforms too. A rule that special-cased the escape would fix the artifact
    and break them.

    **This cannot mask a rename**, which is the invariant the gate exists for: a rename changes the
    characters of a name, and no amount of separator folding makes two different names equal. What
    it could in principle do is merge two baseline IDs that differ **only** in how many slashes they
    contain — so that is asserted rather than assumed, in
    :func:`test_canonicalisation_merges_no_two_baseline_nodes`.
    """
    return _SLASH_RUN.sub("/", node_id)


def _package_dir(package: str) -> Path:
    return _ROOT / "packages" / package


def _collected_node_ids(package: str) -> set[str]:
    """Every collected node ID, canonicalised — the form every comparison uses."""
    return {_canonical(node) for node in _raw_collected_node_ids(package)}


def _raw_collected_node_ids(package: str) -> set[str]:
    """Every node ID `pytest` collects in ``package`` today, exactly as it prints them.

    ``--collect-only -q`` prints one node ID per line and then a summary line, which is dropped by
    requiring a ``::`` in the entry. ``-p no:randomly`` keeps the output order irrelevant to the
    comparison; the comparison is over sets, so it is a courtesy to a reader diffing manually.
    """
    completed = subprocess.run(
        (
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:randomly",
            "--no-header",
        ),
        cwd=_package_dir(package),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, (
        f"collection failed in {package}: a collection error means the comparison below would be "
        f"over a truncated set.\n{completed.stdout[-4000:]}\n{completed.stderr[-2000:]}"
    )
    return {
        line.strip()
        for line in completed.stdout.splitlines()
        if "::" in line and not line.startswith(("=", "-", " "))
    }


def test_the_baseline_describes_the_three_upstream_packages() -> None:
    """Without this, a missing package key would make its comparison silently vacuous."""
    packages = _baseline()
    named = {entry.package for entry in packages.values()}
    assert named == set(_SUITE_WORKFLOW), f"baseline covers {sorted(named)}"
    for key, entry in sorted(packages.items()):
        assert entry.node_ids, f"{key} has no node IDs"
        assert len(entry.node_ids) == entry.node_count, f"{key}'s count disagrees with its list"
        assert len(set(entry.node_ids)) == len(entry.node_ids), f"{key} repeats a node ID"


@pytest.mark.parametrize("feature", ["001", "002", "003"])
def test_canonicalisation_merges_no_two_baseline_nodes(feature: str) -> None:
    """The one risk canonicalisation carries, asserted instead of assumed.

    Folding separators is safe only while it stays injective over the baseline. If two captured IDs
    ever differed **only** in slash count, they would canonicalise to one string, and a real removal
    of either could hide behind the survivor. Nothing in the fixture does that today, and this is
    what notices if that changes.
    """
    entry = _baseline()[feature]
    folded = {_canonical(node) for node in entry.node_ids}
    assert len(folded) == len(entry.node_ids), (
        f"canonicalisation collapses {len(entry.node_ids) - len(folded)} of {feature}'s baseline "
        "IDs into another, so a removal could hide behind the survivor"
    )

    #: The other direction of the same risk: a *live* node folding onto a removed baseline ID would
    #: satisfy the comparison without the removed node existing. Checked over what collects today,
    #: because that is the set the comparison actually reads.
    collected = _collected_node_ids(entry.package)
    raw_collected = _raw_collected_node_ids(entry.package)
    assert len(collected) == len(raw_collected), (
        f"canonicalisation collapses {len(raw_collected) - len(collected)} of {entry.package}'s "
        "collected nodes, so one could stand in for another"
    )


@pytest.mark.parametrize("feature", ["001", "002", "003"])
def test_a_linux_shaped_collection_matches_the_windows_captured_baseline(feature: str) -> None:
    """Review finding W, encoded so it cannot recur silently.

    The baseline was captured on Windows; CI collects on Linux. This constructs the Linux shape from
    the baseline itself — a single separator where the escape produced two — and asserts that the
    comparison the gate performs finds nothing missing.

    It also asserts that the **raw** comparison does find something, because a test that passes both
    ways proves nothing about the fix. That direction is why this file exists: `c7011aa` was green
    on this machine and red on the runner, and no local test disagreed with it.
    """
    entry = _baseline()[feature]
    linux_shaped = {node.replace("//", "/") for node in entry.node_ids}

    raw_missing = set(entry.node_ids) - linux_shaped
    canonical_missing = {_canonical(n) for n in entry.node_ids} - {
        _canonical(n) for n in linux_shaped
    }

    assert not canonical_missing, (
        f"the gate still depends on the collecting platform for {feature}: "
        f"{len(canonical_missing)} nodes differ, first three {sorted(canonical_missing)[:3]}"
    )
    if feature == "003":
        assert not raw_missing, "003 carries no escaped separator, so raw and canonical agree"
    else:
        assert raw_missing, (
            f"{feature}'s baseline no longer carries an escaped separator, so this test no longer "
            "proves the canonical comparison is doing anything. Re-derive it or delete it."
        )


@pytest.mark.parametrize("feature", ["001", "002", "003"])
def test_no_baseline_node_id_vanished_or_was_renamed(feature: str) -> None:
    """The invariant: every captured node ID is still collected.

    A rename shows up here as a removal, which is the correct reading — a caller pinning the old ID
    finds nothing, and "we renamed it" is not a defence against ADR 0017's additive limit.
    """
    entry = _baseline()[feature]
    baseline_ids = {_canonical(node) for node in entry.node_ids}
    collected = _collected_node_ids(entry.package)

    missing = sorted(baseline_ids - collected)
    assert not missing, (
        f"{len(missing)} of {len(baseline_ids)} baseline node IDs are no longer collected in "
        f"{entry.package}; first ten: {missing[:10]}"
    )


@pytest.mark.parametrize("feature", ["001", "002", "003"])
def test_every_upstream_suite_passes_with_nothing_skipped(feature: str) -> None:
    """The other half of the invariant: the nodes that collect also run, and pass.

    `-rs` reports skip reasons, so a skip that appears here arrives with its own explanation rather
    than as a number. `-p no:randomly` removes ordering as a variable between this run and the run
    that produced the baseline.

    Slow on purpose. See this module's docstring for the measured cost and why it is accepted.
    """
    package = _baseline()[feature].package
    completed = subprocess.run(
        (sys.executable, "-m", "pytest", "-q", "-rs", "-p", "no:randomly"),
        cwd=_package_dir(package),
        capture_output=True,
        text=True,
        check=False,
    )
    tail = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
    assert completed.returncode == 0, (
        f"{package}'s suite does not pass, so no baseline node can be called preserved: "
        f"{tail} — {completed.stdout[-4000:]}"
    )
    never = [word for word in _NEVER_TOLERATED if word in tail]
    assert not never, (
        f"{package}'s suite reports {never} in its summary line: {tail!r}. A collected node that "
        "does not run is not a preserved node, and these three are explained by nothing"
    )
    unexplained = _unexplained_skips(package, completed.stdout)
    assert not unexplained, (
        f"{package} skipped a node outside its declared partition:\n"
        + "\n".join(unexplained)
        + f"\n\nSummary line: {tail!r}. A collected node that does not run is not a preserved "
        "node. Either the skip is not about something the runner lacks by design -- in which "
        "case it should fail rather than skip -- or its reason belongs in "
        "`tolerated_skip_reasons` in tools/git-hooks/pre-push, in the diff that adds it."
    )


@pytest.mark.parametrize("package", sorted(_SUITE_WORKFLOW))
def test_each_upstream_suite_runs_unfiltered_in_its_own_workflow(package: str) -> None:
    """The other half: nothing narrows the run that produces the green tick.

    Asserted over the workflow that owns the package. A filtered whole-suite step would let a node
    stay collected, stay unskipped, and still never execute.

    Read by scanning the workflow's `pytest` invocations rather than by matching one command shape:
    the three workflows write the same run four different ways — bare, `cd`-prefixed, line-continued
    — and a single pattern would have quietly matched none of them in at least one file.
    """
    workflow = _WORKFLOWS / _SUITE_WORKFLOW[package]
    assert workflow.is_file(), f"{workflow} is missing"

    invocations = [
        line.strip().split("python -m pytest", 1)[1]
        for line in workflow.read_text(encoding="utf-8").splitlines()
        if "python -m pytest" in line
    ]
    assert invocations, f"{workflow.name} runs no pytest at all"

    #: A whole-suite run: no path argument and no narrowing option. `-q`, `-rs`, `--strict-markers`
    #: and `-p no:randomly` all leave the collected set alone and are therefore not narrowing.
    whole_suite = [
        command
        for command in invocations
        if "tests/" not in command
        and "tests\\" not in command
        and not any(option in command for option in _NARROWING)
    ]
    assert whole_suite, (
        f"{workflow.name} has no unfiltered whole-suite run, so 'passing' is asserted nowhere for "
        f"{package}. Its pytest steps are: {invocations}"
    )
