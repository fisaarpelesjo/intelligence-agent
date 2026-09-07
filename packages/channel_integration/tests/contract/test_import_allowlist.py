"""T119 — the upstream import surface is enumerated by **name**, and nothing else is permitted.

`R-18` fixed the rule and `contracts/interaction-port.md` §3 holds the authoritative list: an
**allowlist**, never a denylist, because a new upstream module must not be permitted by default.

## The task text says seven. The contract says twenty-one. The contract wins.

`T119`'s own wording — "exactly the seven permitted upstream names" — was written before [ADR
0026](../../../../docs/adr/0026-resolved-wording-at-the-interaction-port.md), whose Acceptance row 3
reads "the import allowlist grows from seven names to nineteen". Two further **construction-only**
names were added the same day, making twenty-one.

This gate is written against the contract, and the staleness is recorded rather than quietly
reconciled: a gate that had honoured "seven" would have failed on twelve names an owner authorized,
and one that silently renamed the task's criterion would have hidden that the criterion moved. The
ledger row for `T119` carries the same note.

## Nineteen reading, two construction-only, and why the split is the tighter gate

A flat twenty-one would permit `ResolvedIntent` and `CostProvenance` anywhere. They exist for one
reason: **constructing** an allowlisted type transitively requires the types of its required fields,
and only the fixture corpus constructs one. In production `003` assembles the answer and `004`
receives it, so no module under `src/` needs either name.

So the reading surface stays at nineteen and the two are permitted in `tests/` alone. That is
strictly narrower than twenty-one everywhere, and it is asserted below rather than described.

## What this gate reads

Import **statements**, parsed with `ast`, not text matched. A regex over source would count a name
inside a docstring or a comment, and would miss `from x import (a, b)` spanning lines. Every
`import`/`from` node under `src/` and `tests/` is resolved to the names it actually binds.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract


def _package_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "src" / "channel_integration").is_dir():
            return parent
    raise AssertionError("package root not found")


_PACKAGE = _package_root()
_SRC = _PACKAGE / "src" / "channel_integration"
_TESTS = _PACKAGE / "tests"

#: The three upstream distributions. A fourth appearing is a new dependency, not a new import.
UPSTREAM_PACKAGES = frozenset({"semantic_catalog", "analytics_query", "analytics_interaction"})

#: The nineteen names `004` may **read**, from `contracts/interaction-port.md` §3. The interaction
#: port's own outcome types are the first row of that table, expressed here as the three names the
#: port signature actually binds.
PERMITTED_READING: frozenset[str] = frozenset(
    {
        # the interaction port and its outcome types
        "AnalyticsAnswer",
        "ClarificationContract",
        "QuestionIntake",
        # inherited, passed through unchanged
        "PrincipalContext",
        # the four reason-code namespaces and their shared classifier
        "ReasonCode",
        "AnalyticsReasonCode",
        "InterpretationReasonCode",
        "Outcome",
        # ADR 0026: rendering must read the payload it preserves
        "AnswerClaim",
        "ClaimClass",
        "AttributedCaveat",
        "CaveatSet",
        "CaveatOrigin",
        "LocalizedRef",
        "InsufficiencyNotice",
        "ComparisonBasis",
        "CandidateRef",
        "SlotKind",
        "DeclaredLanguage",
        "ResultProvenance",
    }
)

#: The two names permitted for **construction** only, and therefore in `tests/` only. `T103` asserts
#: the production half of the same rule from the other direction.
PERMITTED_CONSTRUCTION_ONLY: frozenset[str] = frozenset({"ResolvedIntent", "CostProvenance"})

#: **Names reached upstream that the contract does not list. This set is a finding, not a
#: permission.** `SourceUpdate` (`002`) is imported by `tests/fixtures/payloads.py` to build a
#: `ResultProvenance`, and `contracts/interaction-port.md` does not mention it — measured
#: 2026-08-19, zero occurrences. It is the same class as `ResolvedIntent` and `CostProvenance`: a
#: required field type needed to **construct** an allowlisted type. The contract added those two
#: "after the fixture corpus made the need concrete" and missed the third.  It is listed here rather
#: than folded into `PERMITTED_CONSTRUCTION_ONLY` because the contract says plainly that "a
#: twenty-second name is a new decision", and this gate is not the place that decision gets taken.
#: Recording it in a set whose own name says *unrecorded* keeps the suite honest and the gap loud:
#: `test_the_unrecorded_names_are_named_rather_than_absorbed` states what each one is and fails the
#: moment one is added without an explanation.  The violation predates this gate. It has been
#: reachable since the fixture corpus was written; what is new is that something now looks.
#:
#: **This set terminates**, and it did not until `F14` was raised in cycle 83.
#: `test_no_unrecorded_name_is_listed_by_the_contract` requires every name here to be **absent**
#: from `interaction-port.md`, so the day the contract lists one this fails and names the set it
#: should move to. Without that, the expected outcome — the contract authorizing `SourceUpdate` —
#: would have changed nothing here, and a recorded gap would have become a permanent permission
#: with nobody deciding it.
DISCOVERED_UNRECORDED: dict[str, str] = {
    "SourceUpdate": (
        "002, required field of ResultProvenance, construction-only in tests/fixtures/payloads.py; "
        "contracts/interaction-port.md does not list it and a twenty-second name is a new decision"
    ),
}


def _upstream_names_bound_by(source: Path) -> set[str]:
    """Every name ``source`` binds from an upstream package, by parsing its imports.

    `import x.y` binds the top-level package rather than a name, and `004` importing an upstream
    *module* wholesale is a different violation — `test_dependency_direction` owns that one. This
    gate is about names, so only `from upstream... import name` contributes.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"))
    bound: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        if node.module.split(".")[0] not in UPSTREAM_PACKAGES:
            continue
        bound.update(alias.name for alias in node.names)
    return bound


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def test_the_three_sets_are_disjoint() -> None:
    """Readable, construction-only and unrecorded must not overlap.

    **The contract's "nineteen" counts table rows, not names, and that is worth stating rather than
    asserting around.** One row is "the interaction port and its outcome types" — three names — and
    another groups `ReasonCode`, `AnalyticsReasonCode` and `InterpretationReasonCode` into one.
    Nine- teen rows expand to twenty readable names. Asserting `len(...) == 19` here would have been
    asserting a row count against a name set, which is how a number becomes wrong without anybody
    editing it.

    So what is asserted is the property that actually matters: the sets do not overlap. A name in
    two of them would make the narrower rule mean nothing.
    """
    assert not (PERMITTED_READING & PERMITTED_CONSTRUCTION_ONLY), (
        "a name is both readable and construction-only, so the narrower rule means nothing"
    )
    unrecorded = frozenset(DISCOVERED_UNRECORDED)
    assert not (unrecorded & (PERMITTED_READING | PERMITTED_CONSTRUCTION_ONLY)), (
        "a name is both permitted and recorded as unrecorded, which cannot both be true"
    )


def test_the_unrecorded_names_are_named_rather_than_absorbed() -> None:
    """Every unrecorded upstream name carries an explanation, and none is silently permitted.

    This node exists so `DISCOVERED_UNRECORDED` cannot become a quiet second allowlist. Adding a
    name without saying what it is and why the contract does not list it fails here — which is the
    whole difference between recording a gap and widening a boundary.
    """
    for name, why in sorted(DISCOVERED_UNRECORDED.items()):
        assert len(why) > 40, f"{name} is recorded with a thin reason: {why!r}"
        assert "contract" in why.lower(), (
            f"{name}'s reason does not say what the contract does about it"
        )


def test_every_allowlisted_name_appears_in_the_authoritative_contract() -> None:
    """The list is held to the document it copies, not trusted as a copy.

    A set that drifted from `interaction-port.md` would still pass every assertion below — it would
    simply be enforcing a different rule than the one that was authorized.
    """
    contract = _PACKAGE.parents[1] / "specs" / "004-multichannel-integration" / "contracts"
    document = contract / "interaction-port.md"
    assert document.is_file(), f"{document} is missing, so this list is held to nothing"

    text = document.read_text(encoding="utf-8")
    missing = sorted(
        name for name in PERMITTED_READING | PERMITTED_CONSTRUCTION_ONLY if f"`{name}`" not in text
    )
    assert not missing, (
        f"these names are permitted here but the contract does not list them: {missing}. "
        "Either the contract authorizes the name or this gate must not"
    )


def test_no_unrecorded_name_is_listed_by_the_contract() -> None:
    """The symmetric half of the node above, and the one that makes the set **terminate**.

    `F14`, raised by the REVIEWER in cycle 83, and the reasoning is worth stating because the set
    looked complete without it. `DISCOVERED_UNRECORDED` was held to three things — that each entry
    carries an explanation, that it is disjoint from the two permitted sets, and that production
    never reaches the name — but to nothing that would ever make an entry **leave**.

    The measured consequence: `test_tests_import_no_upstream_name_outside_the_full_allowlist` unions
    this set into `permitted`, so inside `tests/` the name is a permission in fact. On the day
    `interaction-port.md` lists `SourceUpdate` — which is the expected outcome, since it is a
    required field type of an allowlisted contract — the entry would sit here unchanged, nothing
    would fail, the name would be permitted by two routes at once, and a recorded gap would quietly
    become a permanent one with nobody deciding it.

    So the rule is stated in the direction that can fail: a name recorded as **unrecorded** must be
    absent from the contract. The moment the contract lists it, this fails and says which set it
    belongs in — which is the whole difference between recording a gap and keeping one.
    """
    document = (
        _PACKAGE.parents[1]
        / "specs"
        / "004-multichannel-integration"
        / "contracts"
        / "interaction-port.md"
    )
    assert document.is_file(), f"{document} is missing, so this list is held to nothing"

    text = document.read_text(encoding="utf-8")
    now_listed = sorted(name for name in DISCOVERED_UNRECORDED if f"`{name}`" in text)
    assert not now_listed, (
        f"the contract now lists {now_listed}, which this gate still records as unrecorded. The "
        "decision the contract says is new has been taken, so move each of these out of "
        "`DISCOVERED_UNRECORDED` and into `PERMITTED_READING` or `PERMITTED_CONSTRUCTION_ONLY` — "
        "leaving it here would keep a closed gap open in the record while the name is permitted "
        "by two routes"
    )


def test_the_unrecorded_check_reads_the_contract_the_same_way_the_permitted_one_does() -> None:
    """Anti-vacuity: the absence above must be an absence the same lookup could have found.

    A backtick lookup that matched nothing at all would make the node above pass over any contract,
    including one that lists every unrecorded name. So the identical `f"`{name}`"` form is required
    to find the names that *are* listed — and `DISCOVERED_UNRECORDED` must be non-empty, because an
    empty set is trivially absent from everything.
    """
    document = (
        _PACKAGE.parents[1]
        / "specs"
        / "004-multichannel-integration"
        / "contracts"
        / "interaction-port.md"
    )
    text = document.read_text(encoding="utf-8")

    assert DISCOVERED_UNRECORDED, "an empty set is absent from every contract, so the node is moot"
    found = [name for name in PERMITTED_READING if f"`{name}`" in text]
    assert found, (
        "the backtick lookup finds none of the permitted names either, so the absence asserted "
        "above is a property of the lookup rather than of the contract"
    )


def test_src_imports_no_upstream_name_outside_the_reading_allowlist() -> None:
    """The production half. Construction-only names are **not** permitted here."""
    found: dict[str, list[str]] = {}
    for source in _python_files(_SRC):
        extra = _upstream_names_bound_by(source) - PERMITTED_READING
        if extra:
            found[str(source.relative_to(_PACKAGE))] = sorted(extra)
    assert not found, (
        f"src imports upstream names outside the reading allowlist: {found}. A twenty-second "
        "name is a new decision, exactly as the eighth and the twentieth were — record it in "
        "`contracts/interaction-port.md` first"
    )


def test_tests_import_no_upstream_name_outside_the_full_allowlist() -> None:
    """The fixture half. Reading names plus the two construction-only ones, and nothing more."""
    permitted = PERMITTED_READING | PERMITTED_CONSTRUCTION_ONLY | frozenset(DISCOVERED_UNRECORDED)
    found: dict[str, list[str]] = {}
    for source in _python_files(_TESTS):
        extra = _upstream_names_bound_by(source) - permitted
        if extra:
            found[str(source.relative_to(_PACKAGE))] = sorted(extra)
    assert not found, f"tests import upstream names outside the allowlist: {found}"


def test_the_construction_only_names_are_absent_from_src() -> None:
    """The narrower half of the split, asserted from the direction that can fail.

    The reading gate above already excludes them, so this would be redundant — except that it states
    the rule as its own sentence, and a future edit that folded the two sets together would pass the
    gate above and fail here.
    """
    found: dict[str, list[str]] = {}
    for source in _python_files(_SRC):
        reached = _upstream_names_bound_by(source) & PERMITTED_CONSTRUCTION_ONLY
        if reached:
            found[str(source.relative_to(_PACKAGE))] = sorted(reached)
    assert not found, (
        f"src reaches a construction-only name: {found}. Those exist because constructing a "
        "fixture answer needs the types of its required fields; production receives the answer "
        "already built"
    )


def test_the_gate_is_not_vacuous() -> None:
    """Upstream names are actually imported somewhere, and the parser sees them.

    A parser that silently returned nothing would make every assertion above pass over an empty set.
    So at least one `src` module and one `tests` module must bind at least one allowlisted name.
    """
    src_bound: set[str] = set()
    for source in _python_files(_SRC):
        src_bound |= _upstream_names_bound_by(source)
    test_bound: set[str] = set()
    for source in _python_files(_TESTS):
        test_bound |= _upstream_names_bound_by(source)

    assert src_bound, "no src module imports any upstream name, so the src gate proves nothing"
    assert test_bound, "no test module imports any upstream name, so the tests gate proves nothing"
    assert src_bound <= PERMITTED_READING
    assert test_bound <= (
        PERMITTED_READING | PERMITTED_CONSTRUCTION_ONLY | frozenset(DISCOVERED_UNRECORDED)
    )
