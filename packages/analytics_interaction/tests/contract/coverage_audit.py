"""Shared coverage extraction for T169—T174. **Not a test module.**

No ``test_`` prefix, so pytest does not collect it. The four domain audits and the two
aggregates share one extractor because four hand-written extractors would eventually
disagree, and the one that disagreed would be the one reporting coverage.

## Where a requirement's owners come from — and where they must not

Three sources, all machine-read:

* **implementation owners** — `FR-nnn` / `SC-nnn` cited in a `src/**/*.py` module. The
  module is the owner; the citation is how it says so;
* **design owners** — cited in an approved contract under
  `specs/003-nl-analytics-interaction/contracts/`, in one of this feature's ADRs
  (0010—0016), or in one of its **governance records**: the internal validation report and
  the `SC-030` measurement declaration. A prohibition can legitimately be owned by a
  document with no module of its own — "do not represent fixture-backed validation as
  production evidence" is discharged by the report that refuses to, not by a function;
* **validation owners** — cited in a `tests/**/*.py` module **that has at least one
  collected pytest node**.

`tasks.md`, `spec.md` and `plan.md` are **never** consulted. That is not a stylistic
choice: a checkbox is a claim about work, an `Evidence:` clause is a claim about
validation, and an audit that read either would be checking the plan against itself.
:func:`forbidden_sources` names them so the audits can assert they were not read.

## Why the collected-node requirement is load-bearing

Without it, every assertion in the audits could be satisfied by adding `FR-047` to a
comment. With it, a citation only counts when the file carrying it **declares at least
one test function**, found by parsing the module rather than by trusting its name.

Two tiers, because one alone is wrong either way:

* the **AST tier** is the gate. It holds in any invocation, including
  `pytest tests/contract/test_fr_coverage_intake.py` — an audit that only worked in a
  full-suite run would fail when somebody ran it alone and would read as a defect;
* the **collection tier** strengthens it. `tests/conftest.py` records this session's node
  IDs through `pytest_collection_modifyitems`, and :func:`collection_disagreements`
  reports any module pytest collected nothing from while the AST found tests, or the
  reverse. Asserted for whatever the session did collect, so a full run cross-checks the
  gate against pytest's own view of the same files.

Shelling out to `pytest --collect-only` was the third option and *recurses*: the child
imports these audit modules, which resolve their scope at import, which shells out
again.

## Domains are derived, not tabulated

A requirement's domain comes from **where its owners live** — the `src/` sub-package or
the contract file — rather than from a list somebody maintains. So an FR whose
implementation moves between packages moves domain with it, and an FR owned across two
domains is audited in both.
"""

from __future__ import annotations

import ast
import functools
import inspect
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import analytics_interaction

__all__ = [
    "ALL_FR",
    "ALL_SC",
    "CONTRACTS",
    "GOVERNANCE_RECORDS",
    "Coverage",
    "Domain",
    "Owners",
    "collected_modules",
    "collected_nodes",
    "collection_disagreements",
    "coverage",
    "forbidden_sources",
]

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent
PACKAGE = SRC.parents[1]
TESTS = PACKAGE / "tests"
REPO = SRC.parents[3]
SPEC = REPO / "specs" / "003-nl-analytics-interaction"
CONTRACTS = SPEC / "contracts"
ADRS = REPO / "docs" / "adr"

#: This feature's ADRs. Numbered rather than globbed: `001` and `002` own 0001—0009, and
#: reading those would let an upstream document answer for a `003` requirement.
ADR_PREFIXES = ("0010", "0011", "0012", "0013", "0014", "0015", "0016")

#: This feature's governance records, named individually.
#:
#: Named rather than globbed for the same reason as the ADRs: `docs/release/` also holds
#: `002`'s reports, and an `FR-060` in one of those is a different requirement.
#:
#: Both own prohibitions. The internal validation report owns "no fixture result is
#: production evidence" and "no readiness is claimed" by being the document that would
#: otherwise carry such a claim; the measurement declaration owns "no interpretation
#: quality is claimed" by recording that it is unmeasured.
GOVERNANCE_RECORDS = (
    "docs/release/nl-analytics-internal-validation.md",
    "docs/measurement/sc-030-interpretation-quality.md",
)

#: The complete requirement inventories, from the spec's own numbering.
ALL_FR: frozenset[int] = frozenset(range(1, 103))
ALL_SC: frozenset[int] = frozenset(range(1, 60))

_FR = re.compile(r"\bFR-(\d{3})\b")
_SC = re.compile(r"\bSC-(\d{3})\b")


class Domain(StrEnum):
    """The four audit domains, matching `T169`—`T172`.

    Values are the task identifiers so a failure message names the audit that owns the
    gap rather than a prose label somebody has to look up.
    """

    INTAKE = "T169"
    INTERPRETATION = "T170"
    ANSWER = "T171"
    GOVERNANCE = "T172"


#: `src/` sub-package to domain. Derived from the package layout, so a module moved
#: between packages moves domain with it.
#:
#: ``contracts/``, ``identity/`` and ``messages/`` are deliberately absent: they are
#: cross-cutting and their requirements are claimed by whichever behavioural package
#: also cites them. An FR owned *only* by a cross-cutting module falls to
#: :data:`FALLBACK_DOMAIN`, and the aggregate asserts that set is small and named.
PACKAGE_DOMAIN: dict[str, Domain] = {
    "intake": Domain.INTAKE,
    "authorization": Domain.INTAKE,
    "interpretation": Domain.INTERPRETATION,
    "execution": Domain.INTERPRETATION,
    "comparison": Domain.ANSWER,
    "answer": Domain.ANSWER,
    "clarification": Domain.GOVERNANCE,
    "governance": Domain.GOVERNANCE,
    "compliance": Domain.GOVERNANCE,
    "audit": Domain.GOVERNANCE,
    "telemetry": Domain.GOVERNANCE,
    "cli": Domain.GOVERNANCE,
}

#: Design-document name to domain, for requirements a document owns without a module.
#:
#: The two governance records are governance by definition — they own prohibitions on this
#: feature's own claims, which is `T172`'s scope.
CONTRACT_DOMAIN: dict[str, Domain] = {
    "nl-analytics-internal-validation.md": Domain.GOVERNANCE,
    "sc-030-interpretation-quality.md": Domain.GOVERNANCE,
    "intake-contract.md": Domain.INTAKE,
    "interpretation-contract.md": Domain.INTERPRETATION,
    "comparison-contract.md": Domain.ANSWER,
    "answer-contract.md": Domain.ANSWER,
    "clarification-contract.md": Domain.GOVERNANCE,
    "governed-content.md": Domain.GOVERNANCE,
    "audit-and-observability.md": Domain.GOVERNANCE,
    "reason-codes.md": Domain.GOVERNANCE,
}

#: Where a requirement lands when only a cross-cutting module or an ADR cites it.
#:
#: Governance, because that is `T172`'s scope and because every such requirement so far
#: is a prohibition, a reason-code rule or a readiness rule.
FALLBACK_DOMAIN = Domain.GOVERNANCE


def forbidden_sources() -> tuple[Path, ...]:
    """Documents an audit must never read to establish coverage.

    Returned so each audit can assert it did not open them, rather than the prohibition
    living only in prose. A checkbox is a claim about work and an ``Evidence:`` clause is
    a claim about validation; reading either would make the audit check the plan against
    itself.
    """
    return (SPEC / "tasks.md", SPEC / "spec.md", SPEC / "plan.md", SPEC / "quickstart.md")


@dataclass(frozen=True, slots=True)
class Owners:
    """Who owns one requirement, by source class.

    Three sets rather than one, because the rule is a **conjunction**: a requirement
    needs an implementation-or-design owner *and* a validation owner, and a single
    merged set could satisfy it twice from the same side.
    """

    implementation: frozenset[str] = frozenset()
    design: frozenset[str] = frozenset()
    validation: frozenset[str] = frozenset()

    @property
    def has_owner(self) -> bool:
        return bool(self.implementation or self.design)

    @property
    def has_validation(self) -> bool:
        return bool(self.validation)

    @property
    def covered(self) -> bool:
        return self.has_owner and self.has_validation


@dataclass(frozen=True, slots=True)
class Coverage:
    """The whole extraction: FR and SC owners, and each requirement's domains."""

    fr: dict[int, Owners] = field(default_factory=dict[int, Owners])
    sc: dict[int, Owners] = field(default_factory=dict[int, Owners])
    fr_domains: dict[int, frozenset[Domain]] = field(default_factory=dict[int, frozenset[Domain]])

    def fr_in(self, domain: Domain) -> tuple[int, ...]:
        """Every FR this domain is responsible for, ascending."""
        return tuple(
            sorted(number for number, domains in self.fr_domains.items() if domain in domains)
        )


def _sources(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _design_documents() -> list[Path]:
    contracts = sorted(CONTRACTS.glob("*.md")) if CONTRACTS.is_dir() else []
    adrs = sorted(p for p in ADRS.glob("*.md") if p.name[:4] in ADR_PREFIXES)
    records = [REPO / relative for relative in GOVERNANCE_RECORDS]
    return contracts + adrs + [p for p in records if p.is_file()]


def collected_nodes() -> frozenset[str]:
    """Every node ID this session collected, from pytest's own collection.

    Read through the ``conftest.py`` hook rather than gathered here, so it describes the
    run the audit is part of. **Not cached**: the set is populated during collection and
    the audits read it during execution, so caching an early read would freeze an empty
    one.
    """
    from ..conftest import COLLECTED_NODE_IDS

    return frozenset(COLLECTED_NODE_IDS)


def collected_modules() -> frozenset[str]:
    """Test modules this session collected at least one node from.

    Node IDs arrive relative to the rootdir with OS-native separators on Windows, so they
    are normalised — a comparison that worked on one platform and not the other would
    make the cross-check silently agree with everything.
    """
    return frozenset(node.replace("\\", "/").split("::", 1)[0] for node in collected_nodes())


@functools.cache
def _declares_a_test(path: Path) -> bool:
    """Whether a module declares at least one test function, by parsing it.

    ``ast`` rather than a regex: a decorated or indented ``def test_`` is a function
    definition either way, and a regex over source would also match one inside a
    docstring — which is exactly the "citation in a comment" this gate exists to reject.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return any(
        isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test_")
        for node in ast.walk(tree)
    )


def _test_modules_with_nodes() -> frozenset[str]:
    """Test modules that count as validation owners.

    The AST tier: a module declaring at least one test function. Independent of which
    files the current invocation happened to select, so running one audit alone audits the
    same thing a full run does.
    """
    return frozenset(
        f"tests/{path.relative_to(TESTS).as_posix()}"
        for path in _sources(TESTS)
        if _declares_a_test(path)
    )


def collection_disagreements() -> tuple[str, ...]:
    """Modules where pytest's collection and the AST gate disagree, for this session.

    Only modules the session actually collected from are compared — a module the
    invocation did not select is absent from the node IDs for a reason that says nothing
    about it.

    A disagreement in either direction is a real finding: pytest collecting nothing from a
    module the AST calls testful means the tests are unreachable, and the reverse means the
    gate would reject a module contributing real nodes.
    """
    declared = _test_modules_with_nodes()
    collected = collected_modules()
    if not collected:
        return ()
    every = frozenset(f"tests/{path.relative_to(TESTS).as_posix()}" for path in _sources(TESTS))
    return tuple(
        sorted(
            module for module in collected & every if (module in collected) != (module in declared)
        )
    )


def _cite(path: Path, pattern: re.Pattern[str]) -> set[int]:
    return {int(match.group(1)) for match in pattern.finditer(path.read_text(encoding="utf-8"))}


def _domain_for_implementation(relative: str) -> Domain | None:
    head = relative.split("/", 1)[0]
    return PACKAGE_DOMAIN.get(head)


def _domain_for_design(name: str) -> Domain | None:
    return CONTRACT_DOMAIN.get(name)


@functools.cache
def _cited() -> tuple[dict[int, Owners], dict[int, Owners], dict[int, frozenset[Domain]]]:
    """Citations from `src/`, the design documents and `tests/`, without the node gate.

    Split from :func:`coverage` and cached separately because the file reads are the
    expensive half and are genuinely invariant, while the node gate depends on which
    modules the current session collected and must not be frozen with them.
    """
    fr: dict[int, dict[str, set[str]]] = {}
    sc: dict[int, dict[str, set[str]]] = {}
    domains: dict[int, set[Domain]] = {}

    def record(table: dict[int, dict[str, set[str]]], number: int, bucket: str, owner: str) -> None:
        table.setdefault(number, {"implementation": set(), "design": set(), "validation": set()})[
            bucket
        ].add(owner)

    for path in _sources(SRC):
        relative = path.relative_to(SRC).as_posix()
        domain = _domain_for_implementation(relative)
        for number in _cite(path, _FR):
            record(fr, number, "implementation", relative)
            domains.setdefault(number, set()).add(domain or FALLBACK_DOMAIN)
        for number in _cite(path, _SC):
            record(sc, number, "implementation", relative)

    for path in _design_documents():
        owner = path.relative_to(REPO).as_posix()
        domain = _domain_for_design(path.name)
        for number in _cite(path, _FR):
            record(fr, number, "design", owner)
            domains.setdefault(number, set()).add(domain or FALLBACK_DOMAIN)
        for number in _cite(path, _SC):
            record(sc, number, "design", owner)

    for path in _sources(TESTS):
        relative = f"tests/{path.relative_to(TESTS).as_posix()}"
        for number in _cite(path, _FR):
            record(fr, number, "validation", relative)
        for number in _cite(path, _SC):
            record(sc, number, "validation", relative)

    def freeze(table: dict[int, dict[str, set[str]]]) -> dict[int, Owners]:
        return {
            number: Owners(**{key: frozenset(value) for key, value in buckets.items()})
            for number, buckets in table.items()
        }

    return freeze(fr), freeze(sc), {number: frozenset(found) for number, found in domains.items()}


def coverage() -> Coverage:
    """Every requirement's owners and domains, with the node gate applied.

    Reads `src/`, this feature's contracts and ADRs, and `tests/`. Reads none of
    :func:`forbidden_sources`.

    A validation citation only counts when its module declares at least one test
    function. Applied here rather than inside the cached extraction, so the gate stays a
    property of the files on disk rather than of one cached read.
    """
    fr, sc, domains = _cited()
    runnable = _test_modules_with_nodes()

    def gate(owners: Owners) -> Owners:
        return Owners(
            implementation=owners.implementation,
            design=owners.design,
            validation=frozenset(name for name in owners.validation if name in runnable),
        )

    return Coverage(
        fr={number: gate(owners) for number, owners in fr.items()},
        sc={number: gate(owners) for number, owners in sc.items()},
        fr_domains=domains,
    )
