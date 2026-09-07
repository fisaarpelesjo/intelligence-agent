"""No prose states which channels are open — `S-5` of cycle 395.

## The defect this exists because of

`FR-818` and `T826` ordered the NODES that asserted *no channel is enabled* to be re-derived
after `OD-18` signed `d_24` and `OD-20-A` split the key. **The nodes were re-derived. The
prose beside them was not**, and on 2026-08-30 three live modules still asserted the world of
2026-08-18:

* the CLI's own module docstring said ``capabilities`` *reports every channel disabled* — two
  lines above a docstring the cycle before had just corrected, in the same file, contradicting
  what the command answers;
* the fixture-substitution suite described the governed answer as *every record undeclared,
  every channel disabled*;
* `007`'s three-conditions module said *no channel is enabled* while a node in that same file
  asserted `sending == [TELEGRAM]`.

**The root is reach, and it is the root of `S-2` and of `S-4` face (a) as well.** What gets
re-derived is what a node asserts. Prose that no node reads ages without ever producing a
symptom — and a docstring that reads as governed and is not is the same defect whether it
promises a guard that does not exist or describes a world that ended.

## What is asserted here, and what deliberately is NOT

**Not** that the prose is true. A node cannot read English. What it can do is refuse the one
sentence shape that went stale: a **quantified claim about channel enablement**, stated
unattributed. *Every channel disabled*, *no channel is enabled*, *which channels are enabled* —
each is a snapshot of the records written somewhere nothing forces to stay true, and each is
replaceable by the reading itself. `may_send_to`, `may_receive_from` and ``capabilities``
answer at the instant they are asked; a count in a docstring is a second copy of that answer
with no mechanism behind it.

**Reporting what a node USED to assert stays permitted, and it must.** Deleting the record of
a correction is how the reason for the correction is lost. So a claim that is attributed —
*"it asserted no channel is enabled, and that stopped holding"* — passes, and the same words
stated flat do not. That distinction is the whole predicate.

**The sweep is derived from the directory, never listed.** A hand-written list of three files
would close these three and let the fourth in — which is exactly the shape `S-4` was: an
enumeration nothing forced to stay complete.

## What this cannot catch, stated rather than left for a reader to discover

A false sentence that avoids these shapes. *"The Telegram channel is closed"* names no
quantifier and would pass. **This is a guard against one recurring shape, not against prose
being wrong**, and it is written down here so nobody reads a green run as more than it is.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract


def _repository_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "packages").is_dir() and (parent / "docs").is_dir():
            return parent
    raise AssertionError("repository root not found")


REPO = _repository_root()

#: This file, excluded by identity rather than by name. It has to spell the forbidden shapes
#: out to say what it forbids, and a guard that failed on its own definition would be one more
#: hand-maintained exception.
SELF = Path(__file__).resolve()

#: Where prose lives beside code. **Globbed, not listed** — a package added tomorrow is swept
#: without anybody remembering to add it.
#: `OD-79` (2026-09-01): the harness moved to apps/telegram-bot — the sweep follows the
#: address, and the node below keeps asserting the bot is reached.
ROOTS = ("packages/*/src/**/*.py", "packages/*/tests/**/*.py", "apps/*/tests/**/*.py")

#: The shapes that are a snapshot of the records rather than a reading of them. Each quantifies
#: over channels and states enablement, which is the pair that makes a sentence go stale the
#: day the owner signs something.
CLAIM_SHAPES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(every|each|all|no|any)\s+channels?\s+(is\s+|are\s+)?(en|dis)abled\b", re.I),
    re.compile(r"\bwhich\s+channels\s+are\s+(en|dis)abled\b", re.I),
    re.compile(r"\bchannels?\s+(is|are)\s+(en|dis)abled\b(?=[^.]*\b(every|all|none|no)\b)", re.I),
)

#: A claim carrying one of these is a REPORT of what something used to say, not an assertion
#: about today. The list is short on purpose: a phrasing that is not here fails, and whoever
#: adds one does it in a diff somebody reads — the same arrangement
#: `PERMITTED_UNDIVIDED_CALLERS` uses in `test_the_split_key_is_asked_by_its_callers.py`.
ATTRIBUTION = ("asserted", "used to", "stopped holding", "stopped being true", "no longer")

#: A sentence, roughly. Prose here is hard-wrapped, so lines are joined before splitting and
#: every offset is mapped back to the line it came from.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _prose(path: Path) -> list[tuple[int, str]]:
    """Every docstring and comment in ``path``, as ``(line number, text)``.

    Docstrings are taken from the AST — module, class and function — so a string that merely
    looks like one is not swept. Comments are taken from the source, because the AST discards
    them and a comment is prose a reader trusts exactly as much.
    """
    source = path.read_text(encoding="utf-8")
    blocks: list[tuple[int, str]] = []

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        text = ast.get_docstring(node, clean=False)
        if text is None:
            continue
        first = node.body[0]
        start = first.lineno
        for offset, line in enumerate(text.splitlines()):
            blocks.append((start + offset, line))

    for number, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            blocks.append((number, stripped.lstrip("#").strip()))

    return blocks


def _claims(path: Path) -> list[tuple[int, str]]:
    """Unattributed claims in ``path``, as ``(line number, the sentence)``.

    The lines of one prose block are joined so a sentence wrapped across two of them is read
    whole, and each match is mapped back to the line its text started on.
    """
    found: list[tuple[int, str]] = []
    blocks = _prose(path)
    if not blocks:
        return found

    #: One run of consecutive prose lines is one block; a gap ends it, so a claim never picks
    #: up an attribution from an unrelated paragraph further down the file.
    runs: list[list[tuple[int, str]]] = []
    for entry in blocks:
        if runs and entry[0] == runs[-1][-1][0] + 1:
            runs[-1].append(entry)
        else:
            runs.append([entry])

    for run in runs:
        joined = ""
        offsets: list[tuple[int, int]] = []
        for number, text in run:
            offsets.append((len(joined), number))
            joined += text + " "

        position = 0
        for sentence in _SENTENCE_END.split(joined):
            start = joined.index(sentence, position)
            position = start + len(sentence)
            if not any(shape.search(sentence) for shape in CLAIM_SHAPES):
                continue
            if any(marker in sentence.lower() for marker in ATTRIBUTION):
                continue
            line = next(number for offset, number in reversed(offsets) if offset <= start)
            found.append((line, sentence.strip()))
    return found


def _swept() -> list[Path]:
    return sorted(
        {
            path
            for pattern in ROOTS
            for path in REPO.glob(pattern)
            if "__pycache__" not in path.parts and path.resolve() != SELF
        }
    )


def test_the_sweep_reaches_the_modules_it_claims_to() -> None:
    """A sweep over nothing forbids nothing — the `F115` shape, asserted before the sweep is."""
    swept = _swept()
    assert len(swept) > 200, f"the sweep found {len(swept)} modules"
    packages = {path.relative_to(REPO).parts[1] for path in swept}
    assert len(packages) >= 7, f"the sweep reached only {sorted(packages)}"
    assert any(path.parts[0] == "apps" for path in (p.relative_to(REPO) for p in _swept())), (
        "the bot is prose beside code too, and it carried the same sentence"
    )


def test_the_predicate_bites() -> None:
    """**Read this before believing the node below.**

    A predicate that matches nothing would report a clean repository forever. It is fed the
    three sentences that were live on 2026-08-30, and an attributed one that must survive.
    """
    stale = (
        "``capabilities`` reports every channel disabled.",
        "every record undeclared, every channel disabled, every governed document unresolvable.",
        "That is stated rather than hidden: no channel is enabled, this feature enables none.",
        "capabilities       which channels are enabled, and which records gate them",
    )
    for sentence in stale:
        assert any(shape.search(sentence) for shape in CLAIM_SHAPES), (
            f"the predicate does not see {sentence!r}, which was live prose"
        )

    attributed = "It then asserted no channel is enabled, which was true and is not now."
    assert any(shape.search(attributed) for shape in CLAIM_SHAPES)
    assert any(marker in attributed.lower() for marker in ATTRIBUTION), (
        "reporting what a node used to assert must stay permitted, or corrections lose "
        "the record of why they happened"
    )


def test_no_prose_states_which_channels_are_open() -> None:
    """`S-5`. Every such claim is attributed, or it is not made.

    The answer is `may_send_to`, `may_receive_from` and ``capabilities``, at the instant they
    are asked. A count written in prose is a second copy with nothing behind it.
    """
    offending: list[str] = []
    for path in _swept():
        relative = path.relative_to(REPO).as_posix()
        for line, sentence in _claims(path):
            offending.append(f"{relative}:{line}: {sentence}")
    assert not offending, (
        "this prose states which channels are open, and nothing keeps it true when the owner "
        "signs the next record — read the answer instead:\n" + "\n".join(offending)
    )
