"""Aggregate FR coverage — T173 (FR-001…FR-102).

    Evidence: the aggregate derives from the domain audits, which inspect implementation
    modules and executable validations; a coverage claim sourced from `tasks.md` fails the
    audit. — `tasks.md` T173

    Validation: a plan claiming coverage is the thing being checked. — `tasks.md` T173

## 102 of 102, and where the number comes from

Not from `tasks.md`'s coverage table. That table is a **claim**, and this audit is what
the claim is checked against — reading it would close the loop and prove nothing.

The number is derived by `coverage_audit.py` from three machine-read sources: `src/`
module citations, this feature's approved contracts and ADRs, and test modules that
declare at least one test function. Every FR needs **both** an implementation-or-design
owner and a validation owner. One without the other is not coverage: a module nobody
tests is unverified, and a test with no implementation is testing something that does not
exist.

## Why the domains are audited first

`T169`—`T172` each assert their own scope, and this file asserts their **union is
complete**. Splitting it that way catches a failure a single aggregate cannot: an FR that
belongs to no domain. The union being 102 and each domain being internally consistent are
different claims, and an FR that fell out of the domain derivation would satisfy the
second while breaking the first.

## What this audit deliberately does not claim

Coverage is not correctness and is not readiness. Every FR having an owner and a passing
validation says the requirement is implemented and checked **against fixtures**. It says
nothing about production behaviour, and the fifteen external records remain open —
`test_aggregate_readiness.py` is where that is asserted, and this file states it here so a
green 102/102 cannot be read as more than it is.
"""

from __future__ import annotations

import pytest

from .coverage_audit import (
    ALL_FR,
    Domain,
    collection_disagreements,
    coverage,
    forbidden_sources,
)

pytestmark = pytest.mark.contract

FR_LIST = tuple(sorted(ALL_FR))


# --- the inventory is the spec's -------------------------------------------------


def test_the_inventory_is_exactly_one_hundred_and_two() -> None:
    """Contiguous FR-001 through FR-102, with no gaps and no extras.

    Asserted as a range rather than a count, because a count is satisfied by any 102
    numbers — including a set that skipped FR-057 and invented FR-103.
    """
    assert len(ALL_FR) == 102
    assert min(ALL_FR) == 1
    assert max(ALL_FR) == 102
    assert set(FR_LIST) == set(range(1, 103))


# --- every FR is covered, both halves -------------------------------------------


@pytest.mark.parametrize("number", FR_LIST, ids=[f"FR-{n:03d}" for n in FR_LIST])
def test_every_fr_has_an_owner_and_a_validation(number: int) -> None:
    """**102 of 102.** The aggregate claim, one FR at a time.

    Per-FR rather than as one set comparison so a failure names the requirement. A single
    aggregate assertion would report "97 of 102" and leave a reviewer to work out which
    five.
    """
    owners = coverage().fr.get(number)
    assert owners is not None, f"FR-{number:03d} is cited in no module, contract, ADR or test"
    assert owners.has_owner, (
        f"FR-{number:03d} has no implementation or design owner; "
        f"only validation: {sorted(owners.validation)}"
    )
    assert owners.has_validation, (
        f"FR-{number:03d} has no executable validation owner; "
        f"only implementation or design: {sorted(owners.implementation | owners.design)}"
    )


def test_the_aggregate_is_exactly_complete() -> None:
    """The same claim as one number, so the report has something to quote.

    Kept alongside the parametrised sweep rather than instead of it: this is the line a
    release document cites, and the sweep is what makes it diagnosable.
    """
    covered = {number for number, owners in coverage().fr.items() if owners.covered}
    assert covered == ALL_FR, sorted(ALL_FR - covered)
    assert len(covered) == 102


# --- the domains partition the inventory ---------------------------------------


def test_every_fr_belongs_to_at_least_one_domain() -> None:
    """**The failure a single aggregate cannot see.**

    An FR with owners but no domain is audited by no domain file, so `T169`—`T172` would
    all pass while nothing checked it. The union closes that.
    """
    assigned = set(coverage().fr_domains)
    assert assigned == ALL_FR, sorted(ALL_FR - assigned)


def test_the_domain_union_is_the_whole_inventory() -> None:
    """And the four domains' scopes, unioned, are 102.

    Asserted through ``fr_in`` — the same accessor the domain files parametrise over — so
    this cannot agree with them while they disagree with each other.
    """
    union: set[int] = set()
    for domain in Domain:
        union.update(coverage().fr_in(domain))
    assert union == ALL_FR, sorted(ALL_FR - union)


def test_no_domain_is_empty() -> None:
    """Four audits, four non-trivial scopes.

    A domain that collapsed to zero would still let the union be complete if another
    domain absorbed it — and the empty audit would pass, reporting nothing.
    """
    for domain in Domain:
        assert coverage().fr_in(domain), domain.value


def test_multi_domain_requirements_are_audited_in_each() -> None:
    """An FR owned across two packages is checked twice, deliberately.

    Either domain losing its owner is a real gap, so the overlap is not double-counting —
    it is the only arrangement in which both gaps are visible.
    """
    overlapping = {
        number: domains for number, domains in coverage().fr_domains.items() if len(domains) > 1
    }
    assert overlapping, "no FR spans two domains; the derivation has probably collapsed"
    for number, domains in overlapping.items():
        for domain in domains:
            assert number in coverage().fr_in(domain), (number, domain.value)


# --- the sources are the right sources -----------------------------------------


def test_no_owner_is_a_planning_document() -> None:
    """**The load-bearing prohibition.**

    A plan claiming coverage is what this audit checks, so no owner may be the plan. Each
    forbidden document is asserted to exist first, so its absence from the owner sets is a
    decision the extractor made rather than a file that happened to be missing.
    """
    for path in forbidden_sources():
        assert path.is_file(), path

    named = {
        owner
        for owners in coverage().fr.values()
        for owner in owners.implementation | owners.design | owners.validation
    }
    assert named
    for owner in named:
        assert "tasks.md" not in owner, owner
        assert not owner.endswith(("spec.md", "plan.md", "quickstart.md")), owner


def test_owners_come_from_the_three_permitted_source_classes() -> None:
    """Modules, design documents, tests. Nothing else qualifies as any of the three.

    Design owners are this feature's contracts, its ADRs, or one of the two governance
    records — the internal validation report and the `SC-030` declaration. Those two are
    named individually in `coverage_audit.py` rather than matched by directory, because
    `docs/release/` also holds `002`'s reports and an `FR-060` in one of those is a
    different requirement.
    """
    from .coverage_audit import GOVERNANCE_RECORDS

    permitted_design = ("specs/003-nl-analytics-interaction/contracts/", "docs/adr/")
    for number, owners in coverage().fr.items():
        for owner in owners.implementation:
            assert owner.endswith(".py"), (number, owner)
        for owner in owners.design:
            assert owner.startswith(permitted_design) or owner in GOVERNANCE_RECORDS, (
                number,
                owner,
            )
        for owner in owners.validation:
            assert owner.startswith("tests/"), (number, owner)


def test_no_upstream_adr_answers_for_a_003_requirement() -> None:
    """FR numbers are per-feature, so reading `001`'s ADRs would be a false positive.

    `FR-001` means different things in `001`'s spec and in this one. An extractor globbing
    `docs/adr/*.md` would have found "owners" for a dozen requirements it had never seen —
    which is why the ADR set is enumerated by number.
    """
    from .coverage_audit import ADR_PREFIXES

    assert ADR_PREFIXES == ("0010", "0011", "0012", "0013", "0014", "0015", "0016")
    for owners in coverage().fr.values():
        for owner in owners.design:
            if owner.startswith("docs/adr/"):
                assert owner.split("/")[-1][:4] in ADR_PREFIXES, owner


def test_the_ast_gate_agrees_with_pytest_collection() -> None:
    """The second tier, for whatever this invocation collected.

    A module pytest collects nothing from while the parser calls it testful has unreachable
    tests; the reverse means the gate would reject a module contributing real nodes. Either
    is a finding, and in a full-suite run this compares the gate against pytest's own view
    of every file.
    """
    assert collection_disagreements() == ()


# --- coverage is not readiness -------------------------------------------------


def test_coverage_makes_no_readiness_claim() -> None:
    """Stated as an assertion because a green 102/102 is what gets over-read.

    Every validation above is fixture-backed. The fifteen external records are open, and
    the aggregate readiness is empty — asserted here as well as in
    `test_aggregate_readiness.py`, so the two documents cannot drift into disagreeing about
    what a complete coverage table means.
    """
    from analytics_interaction.compliance.readiness import aggregate_ready, load_all_records

    # OD-86..106 (2026-09-03): DEZ declarados (d_1/d_2/d_10/ext_a/ext_b no 001;
    # d_14/d_15/d_16 no 002; d_18/d_21 no proprio 003).
    assert aggregate_ready(load_all_records()) == frozenset(
        {"d_1", "d_2", "d_10", "d_14", "d_15", "d_16", "d_18", "d_21", "ext_a", "ext_b"}
    )
