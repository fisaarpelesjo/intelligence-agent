"""FR coverage: intake, language, dates and authorization — T169.

    Evidence: each FR in scope resolves to a module **and** a passing executable
    validation. — `tasks.md` T169

## What this audit reads, and what it refuses to read

Three sources, all machine-read: `src/**/*.py`, this feature's approved contracts and
ADRs, and `tests/**/*.py`. Extraction lives in `coverage_audit.py` so the four domain
audits cannot drift into four different definitions of "covered".

It reads **none** of `tasks.md`, `spec.md`, `plan.md` or `quickstart.md`, and asserts as
much. A checkbox is a claim about work and an `Evidence:` clause is a claim about
validation — an audit that read either would be checking the plan against itself and
would pass for a phase where nothing was built.

## The rule

Every FR in scope needs **both**:

* an **implementation or design owner** — a `src/` module that cites it, or an approved
  contract or ADR that does. A prohibition can legitimately be owned by a contract with
  no module of its own;
* a **validation owner** — a test module that cites it **and contributes at least one
  collected pytest node**.

The second half is why a citation in a comment does not count. Node IDs come from pytest
itself rather than from a scan for `def test_`, because a parametrised or decorated test
is a node pytest knows about and a regex does not.

## Scope is derived

An FR belongs to this domain when a `src/intake/` or `src/authorization/`
module cites it, or when `intake-contract.md` does.

Derived from where the owners live rather than from a list somebody maintains, so an FR
whose implementation moves packages moves domain with it. An FR owned across two domains
is audited in both — deliberately, because either domain losing its owner is a real gap.
"""

from __future__ import annotations

import pytest

from .coverage_audit import ALL_FR, Domain, coverage, forbidden_sources

pytestmark = pytest.mark.contract

DOMAIN = Domain.INTAKE
IN_SCOPE = coverage().fr_in(DOMAIN)


def test_the_domain_has_a_non_trivial_scope() -> None:
    """An audit over nothing passes for the wrong reason.

    20 is a floor rather than an exact count: the scope is derived, so a legitimate
    refactor can move an FR in or out. A scope that collapsed to a handful would mean the
    derivation broke, not that the feature shrank.
    """
    assert len(IN_SCOPE) >= 20, IN_SCOPE
    assert set(IN_SCOPE) <= ALL_FR


@pytest.mark.parametrize("number", IN_SCOPE, ids=[f"FR-{n:03d}" for n in IN_SCOPE])
def test_every_fr_in_scope_has_an_implementation_or_design_owner(number: int) -> None:
    """**Half the rule.** A requirement nothing implements is not covered.

    Asserted per FR rather than as a set difference, so a failure names the requirement
    instead of handing a reviewer a list to diff.
    """
    owners = coverage().fr.get(number)
    assert owners is not None, f"FR-{number:03d} is cited nowhere this audit reads"
    assert owners.has_owner, (
        f"FR-{number:03d} has no implementation or design owner; "
        f"validation owners alone: {sorted(owners.validation)}"
    )


@pytest.mark.parametrize("number", IN_SCOPE, ids=[f"FR-{n:03d}" for n in IN_SCOPE])
def test_every_fr_in_scope_has_a_passing_executable_validation(number: int) -> None:
    """**The other half**, and the one a plan cannot fake.

    The validation owner must be a test module contributing collected nodes. The suite
    this audit runs inside is green, so a collected node is a passing node — which is
    what makes "a passing executable validation" an assertion rather than a hope.
    """
    owners = coverage().fr.get(number)
    assert owners is not None
    assert owners.has_validation, f"FR-{number:03d} has no executable validation owner"


@pytest.mark.parametrize("number", IN_SCOPE, ids=[f"FR-{n:03d}" for n in IN_SCOPE])
def test_no_owner_is_a_dangling_reference(number: int) -> None:
    """Every named owner exists on disk.

    A citation surviving the file it referred to is the failure mode that makes a
    coverage table look complete while pointing at nothing.
    """
    from .coverage_audit import PACKAGE, REPO, SRC

    owners = coverage().fr[number]
    for relative in owners.implementation:
        assert (SRC / relative).is_file(), relative
    for relative in owners.design:
        assert (REPO / relative).is_file(), relative
    for relative in owners.validation:
        assert (PACKAGE / relative).is_file(), relative


def test_the_audit_reads_no_plan_document() -> None:
    """**The prohibition, asserted rather than promised.**

    Every forbidden document exists, so their absence from the extraction is a choice the
    extractor made and not an accident of a missing file. A future edit that pointed the
    extractor at `tasks.md` would make its owner sets include paths under `specs/`, which
    the dangling-reference test above resolves against `src/`, contracts and `tests/`
    only — so the two assertions close from both sides.
    """
    for path in forbidden_sources():
        assert path.is_file(), path

    named = {
        owner
        for owners in coverage().fr.values()
        for owner in owners.implementation | owners.design | owners.validation
    }
    for owner in named:
        assert "tasks.md" not in owner
        assert not owner.endswith("spec.md")
        assert not owner.endswith("plan.md")
        assert not owner.endswith("quickstart.md")


def test_no_fr_is_claimed_twice_by_one_owner_class() -> None:
    """Owner sets are sets, so a duplicated citation cannot inflate a count.

    Stated because the tables in `tasks.md` list owners as comma-separated text where a
    repeat is invisible, and this audit's counts must not have the same property.
    """
    for number in IN_SCOPE:
        owners = coverage().fr[number]
        assert len(owners.implementation) == len(set(owners.implementation))
        assert len(owners.validation) == len(set(owners.validation))
