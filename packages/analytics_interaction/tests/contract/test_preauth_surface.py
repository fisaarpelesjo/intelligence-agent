"""The pre-authorization import boundary — T049 (FR-087; SC-050).

`intake-contract.md` §6: **steps 1-2 are the entire pre-authorization surface.**
Neither reads the catalog, calls a model, resolves a candidate, issues a
clarification, nor discloses a limit.

`T047` proves that by counting calls. This file proves the complementary half —
that the cost surfaces are not even **reachable** from the modules that run
before authorization. The two are genuinely different claims: counting shows
nothing was called on the paths the test drove, and reachability shows there is
no path at all. A counted test can miss a branch; a reachability test cannot.

**Reachable, not merely imported.** A direct-import check would pass for a
preflight that imported a helper that imported the execution port, so the closure
is walked transitively through this package.

**Callables, not types.** ``contracts/comparison.py`` legitimately imports
``semantic_catalog.validation.decision`` for the ``CatalogDecision`` *type* — a
frozen record, not an evaluation. Banning the module would ban a type annotation
and teach the next author to work around the guard. What must not appear is a
**call** to ``evaluate``, ``search``, ``execute_analytics_query`` or their kin,
and that is what is asserted.

Step 1 is Phase 4 and does not exist yet, so today the pre-authorization surface
is `authorization/` alone. The closure walk means this file starts guarding
`intake/` the day it appears, with nothing to remember.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

import analytics_interaction

pytestmark = pytest.mark.contract

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent
PACKAGE = "analytics_interaction"

#: The modules that run before authorization completes. `intake/` joins them in
#: Phase 4; naming it now means the guard covers it on arrival.
PREAUTH_ROOTS = ("authorization", "intake")

#: Subpackages of this feature that own a cost surface. None may be reachable
#: from the pre-authorization closure.
FORBIDDEN_LOCAL = ("execution", "clarification", "interpretation", "comparison", "answer")

#: Upstream entry points that perform work. Modules, matched on the dotted
#: prefix — these are the callables' homes, not type modules.
FORBIDDEN_UPSTREAM = (
    "semantic_catalog.search",
    "semantic_catalog.validation.pipeline",
    "semantic_catalog.provenance",
    "semantic_catalog.freshness",
    "analytics_query.execute",
    "analytics_query.pipeline",
    "analytics_query.execution",
    "analytics_query.adapters",
    "analytics_query.observations",
)

#: Functions whose call is work. A pre-authorization module may not invoke one,
#: whatever it imported to get there.
FORBIDDEN_CALLS = (
    "evaluate",
    "evaluate_fully",
    "search",
    "get_metric",
    "resolve_outcome",
    "execute_analytics_query",
    "execute_bounded",
    "run_until_evaluation",
    "narrow",
    "submit",
    "issue",
)


def _module_path(module: str) -> Path | None:
    """The file backing a dotted `analytics_interaction` module, if any."""
    relative = module.removeprefix(PACKAGE + ".").replace(".", "/")
    for candidate in (SRC / f"{relative}.py", SRC / relative / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _imports(path: Path) -> set[str]:
    """Absolute module names this file imports, relatives resolved.

    Relative imports are resolved rather than skipped: inside a package they are
    the *usual* way one module reaches another, so a closure that ignored them
    would walk almost nothing.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = path.parent.relative_to(SRC).as_posix().replace("/", ".")
    base = f"{PACKAGE}.{package}" if package != "." else PACKAGE

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                found.add(node.module or "")
            else:
                parts = base.split(".")
                anchor = ".".join(parts[: len(parts) - node.level + 1])
                found.add(f"{anchor}.{node.module}" if node.module else anchor)
    return {module for module in found if module}


def _closure() -> dict[str, Path]:
    """Every module transitively reachable from the pre-authorization roots."""
    pending = [
        path
        for root in PREAUTH_ROOTS
        if (SRC / root).is_dir()
        for path in sorted((SRC / root).rglob("*.py"))
        if "__pycache__" not in path.parts
    ]
    seen: dict[str, Path] = {}
    while pending:
        path = pending.pop()
        key = path.relative_to(SRC).as_posix()
        if key in seen:
            continue
        seen[key] = path
        for module in _imports(path):
            if module.split(".")[0] != PACKAGE:
                continue
            local = _module_path(module)
            if local is not None:
                pending.append(local)
    return seen


CLOSURE = _closure()


def test_the_closure_is_non_empty_and_contains_the_preflight() -> None:
    """A reachability guard over nothing passes for the wrong reason."""
    assert CLOSURE, "the pre-authorization closure is empty"
    assert "authorization/context_preflight.py" in CLOSURE
    assert "authorization/refusal.py" in CLOSURE


@pytest.mark.parametrize("subpackage", FORBIDDEN_LOCAL)
def test_no_pre_authorization_module_reaches_a_local_cost_surface(subpackage: str) -> None:
    offenders = sorted(name for name in CLOSURE if name.startswith(f"{subpackage}/"))
    assert not offenders, f"{subpackage}/ is reachable before authorization: {offenders}"


@pytest.mark.parametrize("module", FORBIDDEN_UPSTREAM)
def test_no_pre_authorization_module_imports_an_upstream_entry_point(module: str) -> None:
    offenders = [
        f"{name} imports {imported}"
        for name, path in sorted(CLOSURE.items())
        for imported in _imports(path)
        if imported == module or imported.startswith(module + ".")
    ]
    assert not offenders, f"an upstream entry point is reachable: {offenders}"


def _compiled_patterns(tree: ast.Module) -> set[str]:
    """Module-level names bound to ``re.compile(...)``.

    ``re.Pattern`` also has a ``search`` method, and `intake/parse.py`
    legitimately calls it to reject embedded markup. Banning the bare name would
    fail on a structural check that reads no catalog — so the receiver is
    resolved, and only calls on something that is *not* a local compiled pattern
    count. Narrowing the guard this way keeps a real ``catalog.search(...)``
    banned, which is the thing it exists for.
    """
    bound: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        if "re.compile" not in ast.unparse(node.value.func):
            continue
        bound.update(target.id for target in node.targets if isinstance(target, ast.Name))
    return bound


@pytest.mark.parametrize("function", FORBIDDEN_CALLS)
def test_no_pre_authorization_module_calls_a_work_performing_function(function: str) -> None:
    """The claim that survives a helper import: nothing is *invoked*."""
    offenders: list[str] = []
    for name, path in sorted(CLOSURE.items()):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        patterns = _compiled_patterns(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Attribute):
                called = node.func.attr
                receiver = node.func.value
                if isinstance(receiver, ast.Name) and receiver.id in patterns:
                    continue  # a local regex, not an upstream surface
            elif isinstance(node.func, ast.Name):
                called = node.func.id
            else:
                continue
            if called == function:
                offenders.append(f"{name}:{node.lineno} calls {function}()")
    assert not offenders, f"work is performed before authorization: {offenders}"


def test_the_regex_exemption_does_not_exempt_a_real_catalog_call() -> None:
    """The narrowing must not become a hole.

    A compiled pattern's ``search`` is skipped; a collaborator's is not. Both
    directions asserted, so a future edit that widened the exemption to every
    ``search`` would fail here.
    """
    planted = "\n".join(
        (
            "import re",
            "_P = re.compile('x')",
            "def f(catalog, text):",
            "    _P.search(text)",
            "    return catalog.search(text)",
        )
    )
    tree = ast.parse(planted)
    patterns = _compiled_patterns(tree)
    assert patterns == {"_P"}

    receivers = [
        (node.func.value.id, node.func.attr)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
    ]
    banned = [
        (recv, call) for recv, call in receivers if call in FORBIDDEN_CALLS and recv not in patterns
    ]
    assert banned == [("catalog", "search")]


def test_the_closure_follows_relative_imports() -> None:
    """The walk must be transitive, or it proves only the direct edge.

    `context_preflight.py` reaches `contracts/intake.py` through two relative
    hops; if the resolver stopped at direct imports, the closure would hold two
    files and the bans above would be vacuous.
    """
    assert "contracts/intake.py" in CLOSURE
    assert "contracts/reason_codes.py" in CLOSURE
    assert len(CLOSURE) > 3


def test_the_guard_detects_a_planted_reach() -> None:
    """A boundary test never shown to fail proves nothing about the boundary."""
    planted = ast.parse("from analytics_query.execute import execute_analytics_query\n")
    modules = {
        node.module
        for node in ast.walk(planted)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert any(
        module == banned or module.startswith(banned + ".")
        for module in modules
        for banned in FORBIDDEN_UPSTREAM
    )

    planted_call = ast.parse("port.submit(request)\n")
    calls = {
        node.func.attr
        for node in ast.walk(planted_call)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert calls & set(FORBIDDEN_CALLS)


# --- no ambient authorizer, provider or credential ----------------------------


#: Distribution roots that would put an identity provider, a network client or a
#: store inside the pre-authorization path.
AMBIENT_IMPORTS = (
    "dotenv",
    "boto3",
    "requests",
    "httpx",
    "urllib",
    "socket",
    "sqlite3",
    "redis",
    "psycopg",
    "psycopg2",
    "asyncpg",
    "google.auth",
    "google.oauth2",
)

#: Names whose *call* is an ambient lookup — reading configuration, discovering a
#: credential, or opening a connection nobody injected.
AMBIENT_CALLS = (
    "getenv",
    "load_dotenv",
    "default",
    "default_credentials",
    "urlopen",
    "connect",
    "Session",
)


def _attribute_chains(path: Path) -> set[str]:
    """Dotted attribute expressions, so ``os.environ`` is visible as one name."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute | ast.Subscript)
    }


@pytest.mark.parametrize("root", AMBIENT_IMPORTS)
def test_no_pre_authorization_module_imports_an_ambient_source(root: str) -> None:
    """No network client, identity provider or store on the path.

    Read from imports rather than raw text: `contracts/reason_codes.py` says
    "malformed **requests**" in prose describing `002`'s ownership, and a text
    scan would fail on an accurate sentence. Banning the word would teach the
    next author to delete the explanation instead of the dependency.
    """
    offenders = [
        f"{name} imports {imported}"
        for name, path in sorted(CLOSURE.items())
        for imported in _imports(path)
        if imported == root or imported.startswith(root + ".")
    ]
    assert not offenders, f"an ambient source is reachable: {offenders}"


def test_no_pre_authorization_module_reads_the_environment() -> None:
    """A module that could read a credential could authorize without a resolver.

    That is the default-allow this phase forbids, arriving by the back door.
    """
    offenders = [
        f"{name}: {chain}"
        for name, path in sorted(CLOSURE.items())
        for chain in _attribute_chains(path)
        if "environ" in chain or chain.startswith("os.")
    ]
    assert not offenders, f"the environment is read before authorization: {offenders}"


@pytest.mark.parametrize("function", AMBIENT_CALLS)
def test_no_pre_authorization_module_calls_an_ambient_lookup(function: str) -> None:
    offenders: list[str] = []
    for name, path in sorted(CLOSURE.items()):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else node.func.id
                if isinstance(node.func, ast.Name)
                else ""
            )
            if called == function:
                offenders.append(f"{name}:{node.lineno} calls {function}()")
    assert not offenders, f"an ambient lookup is performed: {offenders}"


def test_the_ambient_scans_would_catch_a_planted_lookup() -> None:
    """Both halves, shown to fail on what a real violation looks like."""
    planted = ast.parse("import os\ntoken = os.environ['IDP_TOKEN']\n")
    chains = {
        ast.unparse(node)
        for node in ast.walk(planted)
        if isinstance(node, ast.Attribute | ast.Subscript)
    }
    assert any("environ" in chain for chain in chains)

    planted_import = ast.parse("import httpx\n")
    roots = {
        alias.name
        for node in ast.walk(planted_import)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert roots & set(AMBIENT_IMPORTS)


def test_the_resolver_has_no_default_and_must_be_passed() -> None:
    """`resolver` is keyword-only and required.

    A default would be a default answer to "who is asking". Asserted on the
    signature so an added default fails here rather than in review.
    """
    from analytics_interaction.authorization.context_preflight import (
        resolve_authorization_context,
    )

    signature = inspect.signature(resolve_authorization_context)
    resolver = signature.parameters["resolver"]
    assert resolver.kind is inspect.Parameter.KEYWORD_ONLY
    assert resolver.default is inspect.Parameter.empty


def test_the_package_ships_no_resolver_implementation() -> None:
    """A concrete resolver here would be an identity provider nobody approved."""
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = {ast.unparse(base) for base in node.bases}
            if any("Protocol" in base for base in bases):
                continue
            if any(
                isinstance(child, ast.FunctionDef) and child.name == "resolve"
                for child in node.body
            ) and "principal" in ast.unparse(node):
                offenders.append(f"{path.relative_to(SRC).as_posix()}: {node.name}")
    assert not offenders, f"a concrete resolver ships in src/: {offenders}"
