"""A rebase moved no content of this feature — `H-1`, and the third recurrence closed.

**The sentence kept being wrong, so the sentence stopped being the instrument.**

Three times in three cycles a hand-written guard claimed more than it measured:

* `358` — *"no line of `005`'s log mentions `006`"*, against two mentions;
* `361` — the reviewer measured a rebase guard at the wrong pair of commits and nearly
  produced a false finding;
* `362` — *"`git diff` came back EMPTY"*, against one file: this very node, carrying the
  `BASE` that the rebase moved.

Each time the remedy was *"correct the sentence"*, and each time the next sentence came
back wrong — because the guard was **measured by hand and rewritten by hand, in prose,
every cycle**. Correcting prose does not fix prose.

## So the guard is a node, and it DRIVES git rather than describing a check

For every rebase of this branch onto the `005` line, the two commits are named and the
trees are compared **by git**. Every path that differs must be **declared with a
reason**, and anything else is a failure. The `BASE` moving is no longer a paragraph a
reader has to marry to another paragraph: it is a **named exception** with the two shas
that produced it.

**A declaration that no longer differs fails too.** A dead exception is the shape this
repository refuses everywhere else — it looks like a considered decision while excusing
nothing.

## Absence skips, and it is not a loophole here

The *before* commits are orphaned by the rebase that replaced them: they live on local
backup branches and are unreachable from the remote. On a fresh clone they are simply
absent, and reporting that as content movement would be a node going red for something
that is not the thing it guards. **Absence skips loudly; a real difference fails.**
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

#: `tests/contract/` -> `tests/` -> package -> `packages/` -> repository.
REPO = Path(__file__).resolve().parents[4]

#: What belongs to this feature. The rebases below must not move any of it.
#:
#: `tools/git-hooks` is here even though it is not a package of this feature: the push
#: gate was rewritten on this branch, and a rebase silently reverting it is exactly the
#: kind of loss the guard exists to catch.
FEATURE_PATHS = (
    "packages/insights_prioritisation",
    "specs/006-insights-and-prioritisation",
    "tools/git-hooks",
)


@dataclass(frozen=True, slots=True)
class Rebase:
    """One update of this branch from the `005` line, with what it was allowed to move."""

    before: str
    after: str
    why: str
    declared: dict[str, str]


#: Every rebase of this branch onto the `005` line, newest last.
#:
#: **The disentangling rewrite of cycle 358 is deliberately NOT here.** That one moved
#: content on purpose — twenty-two files re-added where the history had dropped them —
#: and its guard was the opposite claim: the tree had to be IDENTICAL to `1d1db30`'s.
#: Listing it here would ask this node to assert something it never claimed.
REBASES = (
    Rebase(
        before="095c447b87068b085edd95f3553bc634c2245dac",
        after="ff0f96e307fca4b1cc0ee05bf121df854e1f2f5a",
        why="the first update from the 005 line, taken because the shared push gate ran "
        "005's suite and the copy on this branch predated the skip on an expired credential",
        declared={
            "packages/insights_prioritisation/tests/contract/test_no_upstream_file_was_edited.py": (
                "BASE moved from 783e6d3 to 7492d154 -- the anchor is the parent of this "
                "branch's first commit, so bringing 005 forward moves it by definition"
            ),
        },
    ),
    Rebase(
        before="c87fe785a156a7fc4d97fb9743ce7517e81cbcc6",
        after="c69f34979943e28dbb1726499893aefd11631edb",
        why="the third update, taken so the harness formatting landed on this branch BEFORE "
        "the push gate started deriving over it -- a gate born red is a gate somebody routes "
        "around, and the formatting was mechanical to pay",
        declared={
            "packages/insights_prioritisation/tests/contract/test_no_upstream_file_was_edited.py": (
                "BASE moved from 4dfd63f to a48ecf1, for the same reason as the two above: the "
                "anchor is the parent of this branch's first commit, so bringing 005 forward "
                "moves it"
            ),
        },
    ),
    Rebase(
        before="583fa855c39910afacd8d8907fbf9f7f81ea8420",
        after="85c6ce942fc5ceba8c873c42cfd2fd3cb3f10e8d",
        why="the second update, taken to receive 004's allowlist fix as COMMITS OF 005 rather "
        "than as an edit by 006, which the boundary node forbids",
        declared={
            "packages/insights_prioritisation/tests/contract/test_no_upstream_file_was_edited.py": (
                "BASE moved from 7492d154 to 4dfd63f, for the same reason as above"
            ),
        },
    ),
)


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False)


def _both_commits_are_here(rebase: Rebase) -> bool:
    """Whether git can see both sides. The *before* side is orphaned by design."""
    return all(
        _git("cat-file", "-e", f"{commit}^{{commit}}").returncode == 0
        for commit in (rebase.before, rebase.after)
    )


def differing_paths(rebase: Rebase) -> list[str]:
    """Every file of THIS FEATURE that differs across the rebase, declared or not.

    Driven off `git diff` rather than off a memory of what was checked — which is the
    whole of `H-1`. Exposed as a function so a test can call it with the declarations
    withheld and see the difference come back.
    """
    result = _git("diff", "--name-only", rebase.before, rebase.after, "--", *FEATURE_PATHS)
    if result.returncode != 0:  # pragma: no cover - unreachable while the guard above holds
        pytest.skip(f"git could not compare the pair: {result.stderr.strip()[:120]}")
    return sorted(line.strip() for line in result.stdout.splitlines() if line.strip())


def undeclared_movement(rebase: Rebase, declared: dict[str, str] | None = None) -> list[str]:
    """What moved that nobody declared. ``declared`` is a parameter so a node can drive it."""
    names = rebase.declared if declared is None else declared
    return [path for path in differing_paths(rebase) if path not in names]


def test_there_is_a_rebase_to_measure() -> None:
    """**Vacuity guard.** With no rebase named, every assertion below is trivially true.

    **And the guard itself was vacuous, which the strict type checker proved rather than
    suspected**: `REBASES` is a tuple literal in this module, so `assert REBASES` is a
    statement a checker can evaluate to true without running anything. It could never have
    failed while the tuple was written where it is. Comparing the LENGTH keeps the runtime
    meaning -- emptying the tuple still fails here -- without asserting something already
    known at read time.
    """
    assert len(REBASES) > 0, "no rebase is named, so this file measures nothing at all"


@pytest.mark.parametrize("rebase", REBASES, ids=lambda r: r.after[:7])
def test_no_content_of_this_feature_moved(rebase: Rebase) -> None:
    """The claim the prose kept getting wrong, asserted by comparing the trees."""
    if not _both_commits_are_here(rebase):  # pragma: no cover - a clone without the backups
        pytest.skip(
            f"{rebase.before[:7]} is not in this checkout; the pre-rebase side is orphaned "
            "by design and unreachable from the remote"
        )
    moved = undeclared_movement(rebase)
    assert not moved, (
        f"the rebase {rebase.before[:7]}..{rebase.after[:7]} moved content of this feature "
        f"that nobody declared: {moved}"
    )


@pytest.mark.parametrize("rebase", REBASES, ids=lambda r: r.after[:7])
def test_every_declared_exception_really_moved(rebase: Rebase) -> None:
    """**A dead declaration screams.**

    An exception for a path that did not move looks like a considered decision while
    excusing nothing — the same shape as an exclusion naming a commit outside the window,
    and this repository deletes those rather than letting them settle.
    """
    if not _both_commits_are_here(rebase):  # pragma: no cover - a clone without the backups
        pytest.skip(f"{rebase.before[:7]} is not in this checkout")
    moved = set(differing_paths(rebase))
    dead = sorted(path for path in rebase.declared if path not in moved)
    assert not dead, f"declared as moved and did not move: {dead}"


@pytest.mark.parametrize("rebase", REBASES, ids=lambda r: r.after[:7])
def test_withholding_the_declaration_exposes_the_movement(rebase: Rebase) -> None:
    """**Proof this node bites, driven rather than described.**

    This is the reviewer's own acceptance criterion executed as a call: with the
    declarations withheld, a path of this feature that moved MUST come back — otherwise
    the node would be reporting *"nothing moved"* because it looks at nothing.
    """
    if not _both_commits_are_here(rebase):  # pragma: no cover - a clone without the backups
        pytest.skip(f"{rebase.before[:7]} is not in this checkout")
    exposed = undeclared_movement(rebase, declared={})
    assert exposed == sorted(rebase.declared), (
        "with nothing declared, the movement this rebase really made did not come back: "
        f"{exposed}. The comparison is looking at the wrong pair or the wrong paths."
    )


def test_every_declared_reason_says_something() -> None:
    """A one-word reason is a reason nobody can check, and the allowlist next door
    refuses the same shape with `len(entry.why) > 40`."""
    for rebase in REBASES:
        assert len(rebase.why) > 40, f"{rebase.after[:7]} cites a thin reason"
        for path, why in rebase.declared.items():
            assert len(why) > 40, f"{path} in {rebase.after[:7]} is excused by a thin reason"
