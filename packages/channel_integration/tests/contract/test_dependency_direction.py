"""Dependency direction and the Phase A import surface — T028 (FR-035; SC-045 partial).

Two claims, and the distinction between them matters:

* **Direction.** `semantic_catalog`, `analytics_query` and `analytics_interaction` never
  import `channel_integration`. A reverse edge would make the upstream packages depend
  on the one reachable from the public internet, and would let a change here break a
  merged feature's suite.
* **Surface, as far as Phase A can claim it.** No module in this package imports an
  upstream **internal**. The full enumerated allowlist is `T119` in Phase D, when the
  interaction port exists; asserting it here would mean asserting a boundary against a
  port that has not been written, so this test asserts what is true now — the upstream
  imports are exactly the two published enums Phase A needs — and names `T119` as the
  place the allowlist itself is pinned.

Both are read from **source text**, not from import machinery: a module that is never
imported by a test would otherwise never be checked.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

_UPSTREAM_PACKAGES = ("semantic_catalog", "analytics_query", "analytics_interaction")

#: What Phase A legitimately imports from upstream, and nothing else.
#:
#: ``semantic_catalog.contracts.reason_codes`` supplies ``Outcome`` — one enum shared by
#: four namespaces, because four enums naming the same three outcome classes would
#: eventually disagree. The three reason-code enums are imported by **tests** for the
#: disjointness assertion, which is what those imports are for.
_PERMITTED_UPSTREAM_MODULES = frozenset(
    {
        "semantic_catalog.contracts.reason_codes",
        "analytics_query.contracts.reason_codes",
        "analytics_interaction.contracts.reason_codes",
        # Added by ADR 0026 (2026-08-17) when the outbound boundary arrived. Rendering has to read
        # the payload it must preserve, and the nineteen-name allowlist in
        # `contracts/interaction-port.md` §3 enumerates exactly what it may read. These are the two
        # published contract modules those names live in — no upstream internal is reachable through
        # either, which `test_this_package_imports_no_upstream_internal` still proves independently.
        "analytics_interaction.contracts.answer",
        "analytics_interaction.contracts.clarification",
        # `ResultProvenance` and `SourceUpdate` live here. Listed separately from the two above
        # because they belong to `002`, not `003`.
        "analytics_query.contracts.result_provenance",
        # The public contracts package. `LocalizedRef` is re-exported from it, which is why the
        # fixture imports it from here rather than from the underscore-named module it is defined
        # in — an authorized name reached by a private-looking path would read as a boundary breach
        # even though it is not one.
        "analytics_interaction.contracts",
        # Added by `T118` (2026-08-19) when the interaction port arrived and `004` first had to
        # **construct** a `QuestionIntake`. `QuestionIntake`, `PrincipalContext` and
        # `DeclaredLanguage` all live here and all three are rows of the authoritative name table in
        # `contracts/interaction-port.md` §3 — the module is new to this set, the names are not.
        #
        # This is a `test_maintenance_policy` correction, and the proof it requires is stated rather
        # than assumed. **The permanent property**: this stays an allowlist, no upstream internal
        # becomes reachable, and `test_this_package_imports_no_upstream_internal` still proves that
        # independently. **The expired premise**: this set was Phase A's, and Phase A never built an
        # intake, so the module it lives in had no reason to appear. **Strictly stronger, not
        # weaker**: `tests/contract/test_import_allowlist.py` (`T119`) now enforces the same
        # boundary at **name** granularity across `src/` and `tests/`, which is narrower than any
        # module list — permitting a module here no longer permits every name inside it.
        "analytics_interaction.contracts.intake",
        # Construction-only, authorized 2026-08-17: `ResolvedIntent` and `CostProvenance` are
        # required fields of `AnalyticsAnswer` and `ResultProvenance`, so a fixture that builds one
        # needs them. `test_no_src_module_imports_a_construction_only_name` keeps them out of `src`.
        "analytics_interaction.contracts.intent",
        "analytics_query.contracts.provenance",
    }
)

#: The two names authorized for **construction only**. Only the fixture corpus may reach them: in
#: production `003` assembles the answer, so `src` never constructs one. Keeping the reading surface
#: at nineteen is what makes the twenty-one-name allowlist tighter than a flat twenty-one.
_CONSTRUCTION_ONLY_MODULES = frozenset(
    {
        "analytics_interaction.contracts.intent",
        "analytics_query.contracts.provenance",
    }
)

#: Upstream module prefixes that are internals to this feature. Importing any of them
#: would be reaching past a published contract into another feature's machinery.
_FORBIDDEN_UPSTREAM_PREFIXES = (
    "semantic_catalog.decision",
    "semantic_catalog.catalog",
    "semantic_catalog.loader",
    "analytics_query.compile",
    "analytics_query.execution",
    "analytics_query.results",
    "analytics_query.decision",
    "analytics_query.policy",
    "analytics_query.observations",
    "analytics_query.identity",
    "analytics_interaction.intake",
    "analytics_interaction.interpretation",
    "analytics_interaction.authorization",
    "analytics_interaction.governance",
    "analytics_interaction.clarification",
    "analytics_interaction.comparison",
    "analytics_interaction.execution",
    "analytics_interaction.answer",
    "analytics_interaction.identity",
    "analytics_interaction.audit",
    "analytics_interaction.messages",
    "analytics_interaction.telemetry",
    "analytics_interaction.compliance",
    "analytics_interaction.cli",
)

_IMPORT = re.compile(r"^\s*(?:from\s+([A-Za-z0-9_.]+)\s+import|import\s+([A-Za-z0-9_.]+))", re.M)


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "packages").is_dir() and (parent / "docs").is_dir():
            return parent
    raise AssertionError("repository root not found")


def _python_files(package: str) -> list[Path]:
    root = _repo_root() / "packages" / package
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _imported_modules(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    found: set[str] = set()
    for match in _IMPORT.finditer(text):
        module = match.group(1) or match.group(2)
        if module and not module.startswith("."):
            found.add(module)
    return found


@pytest.mark.parametrize("package", _UPSTREAM_PACKAGES)
def test_no_upstream_package_imports_this_one(package: str) -> None:
    offenders: list[str] = []
    for path in _python_files(package):
        if any(module.startswith("channel_integration") for module in _imported_modules(path)):
            offenders.append(str(path))
    assert not offenders, f"{package} imports channel_integration in: {offenders}"


def test_this_package_imports_no_upstream_internal() -> None:
    offenders: list[tuple[str, str]] = []
    for path in _python_files("channel_integration"):
        for module in _imported_modules(path):
            for prefix in _FORBIDDEN_UPSTREAM_PREFIXES:
                if module == prefix or module.startswith(prefix + "."):
                    offenders.append((path.name, module))
    assert not offenders, f"forbidden upstream internals imported: {offenders}"


def test_the_upstream_imports_are_exactly_what_phase_a_needs() -> None:
    """An allowlist, not a denylist: a new upstream import fails rather than passing.

    The name-level allowlist is now pinned by `T119`, which landed 2026-08-19 with the interaction
    port: `tests/contract/test_import_allowlist.py` parses every import with `ast` and holds each
    bound name against `contracts/interaction-port.md` §3. This node asserts the coarser
    module-level fact, which remains worth asserting on its own — a module reachable at all is a
    larger fact than a name being read from it.

    The name count was six when this file was written, became seven with the `Outcome`
    reconciliation of 2026-08-17, and the contract's table now holds twenty-one entries across
    nineteen rows. `T119` records why the row count and the name count differ. It is stated rather
    than omitted because a stale count in a docstring is how the code and the contract start
    disagreeing quietly.
    """
    used: set[str] = set()
    for path in _python_files("channel_integration"):
        for module in _imported_modules(path):
            if module.split(".")[0] in _UPSTREAM_PACKAGES:
                used.add(module)
    unexpected = sorted(used - _PERMITTED_UPSTREAM_MODULES)
    assert not unexpected, f"unexpected upstream imports in Phase A: {unexpected}"


def test_no_forbidden_runtime_surface_is_imported() -> None:
    """No warehouse client, HTTP client, HTTP server or provider SDK (`FR-092`, `FR-106`)."""
    forbidden_roots = {
        "google",
        "google.cloud",
        "bigquery",
        "httpx",
        "requests",
        "aiohttp",
        "flask",
        "fastapi",
        "starlette",
        "uvicorn",
        "django",
        "socket",
        "socketserver",
        "http.server",
        "slack_sdk",
        "telegram",
        "twilio",
        "boto3",
    }
    offenders: list[tuple[str, str]] = []
    for path in _python_files("channel_integration"):
        for module in _imported_modules(path):
            root = module.split(".")[0]
            if module in forbidden_roots or root in forbidden_roots:
                offenders.append((path.name, module))
    assert not offenders, f"forbidden runtime surface imported: {offenders}"


def test_no_src_module_imports_a_construction_only_name() -> None:
    """The split the twenty-one-name allowlist rests on (`contracts/interaction-port.md` §3).

    Nineteen names are for **reading** a payload; two exist only so a fixture can **construct** one.
    If `src` ever imported either, the reading surface would silently become twenty-one and the
    distinction recorded in the contract would be prose rather than a rule.
    """
    src = _repo_root() / "packages" / "channel_integration" / "src"
    offenders: list[str] = []
    for path in sorted(src.rglob("*.py")):
        for module in _imported_modules(path):
            if module in _CONSTRUCTION_ONLY_MODULES:
                offenders.append(f"{path.name}: {module}")
    assert not offenders, offenders


def test_the_construction_only_names_are_reachable_from_the_fixtures() -> None:
    """The complement: a split nobody exercises would be a rule with no subject.

    Without this, the assertion above would also pass if the fixture corpus stopped constructing an
    `AnalyticsAnswer` at all — at which point the preservation tests would be exercising a double
    instead of the object the port returns.
    """
    fixtures = _repo_root() / "packages" / "channel_integration" / "tests" / "fixtures"
    used: set[str] = set()
    for path in sorted(fixtures.rglob("*.py")):
        used |= _imported_modules(path)
    assert used >= _CONSTRUCTION_ONLY_MODULES, (
        "the fixture corpus no longer constructs an upstream answer"
    )
