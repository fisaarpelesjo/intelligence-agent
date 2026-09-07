"""No metric-level decision is made here — T048 (FR-088; SC-053).

`FR-088` is one of the sharper boundaries in the specification:

    The authorization-context preflight is **not** a metric-level authorization
    decision and MUST NOT be presented, reused or relied on as one. [...] This
    feature MUST NOT re-implement, anticipate, cache, pre-compute or shortcut
    that decision. Resolving *who is asking* is a precondition; deciding *what
    they may see* stays upstream.

Four verbs, four distinct failure modes, so the checks are separated rather than
folded into one "no authorization logic here" assertion:

* **re-implement** — no tag/metric matching exists in this package;
* **anticipate** — the preflight's return type cannot express a verdict;
* **cache** — nothing stores a decision between calls;
* **shortcut** — a principal with zero tags is *resolved*, not denied, because
  denying them here would be answering the upstream question early.

The last is the subtle one and the one worth a test of its own. Refusing an
untagged principal at step 2 looks like defence in depth and is actually this
feature deciding what somebody may see, three steps before the metric is known.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from semantic_catalog.contracts.access_tag import PrincipalType

import analytics_interaction
from analytics_interaction.authorization import context_preflight
from analytics_interaction.authorization.context_preflight import (
    AuthorizationContextResolver,
    AuthorizedContext,
    resolve_authorization_context,
)
from analytics_interaction.contracts.intake import PrincipalContext

pytestmark = pytest.mark.contract

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent
AUTHORIZATION = SRC / "authorization"


def _sources(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _identifiers(path: Path) -> set[str]:
    """Names the module binds or reads — never docstrings or comments.

    A module that *documents* the boundary is doing the right thing; a module
    that *implements* the decision is not, and only an identifier-level scan
    distinguishes them.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            found.add(node.name)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
    return found


# --- not re-implemented -------------------------------------------------------


#: Names that would mean this package decided what a principal may see. Not
#: "authorization" in general — resolving a context is authorization work — but
#: specifically the *metric-level* verdict.
VERDICT_NAMES = (
    "may_see",
    "can_see",
    "is_permitted",
    "permits",
    "permitted_metrics",
    "allowed_metrics",
    "visible_metrics",
    "authorize_metric",
    "check_access",
    "has_access",
    "access_allowed",
    # Not bare "grant": ``granted_access_tags`` is the resolved fact this
    # preflight carries, and banning the word would ban the field the
    # identity system answers with.
    "grants_access",
    "deny_metric",
    "filter_by_tags",
    "tags_allow",
    "required_tags",
)


@pytest.mark.parametrize("name", VERDICT_NAMES)
def test_no_module_declares_a_metric_level_verdict(name: str) -> None:
    offenders = [
        f"{path.relative_to(SRC).as_posix()}: {identifier}"
        for path in _sources(SRC)
        for identifier in _identifiers(path)
        if name in identifier.lower()
    ]
    assert not offenders, f"a metric-level decision surface exists: {offenders}"


def test_no_module_compares_a_tag_set_against_anything() -> None:
    """Tag arithmetic is how a metric-level decision gets made by accident.

    Set operations over ``granted_access_tags`` — intersection, subset,
    difference — are the shape that decision takes. The preflight compares the
    caller's assertion against the resolver's answer for **equality only**, which
    is an escalation check, not an access check.
    """
    offenders: list[str] = []
    for path in _sources(SRC):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare) and any(
                isinstance(op, ast.In | ast.NotIn | ast.LtE | ast.GtE | ast.Lt | ast.Gt)
                for op in node.ops
            ):
                rendered = ast.unparse(node)
                if "access_tags" in rendered:
                    offenders.append(f"{path.relative_to(SRC).as_posix()}: {rendered}")
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitAnd | ast.Sub):
                rendered = ast.unparse(node)
                if "access_tags" in rendered:
                    offenders.append(f"{path.relative_to(SRC).as_posix()}: {rendered}")
    assert not offenders, f"tag-set arithmetic found: {offenders}"


def test_the_authorization_package_never_imports_the_catalog_gate() -> None:
    """`001`'s gate 3 is the owner. A second implementation is a second truth."""
    forbidden = ("semantic_catalog.validation", "semantic_catalog.search")
    offenders: list[str] = []
    for path in _sources(AUTHORIZATION):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom) and node.level == 0
                else []
            )
            offenders.extend(
                f"{path.name} imports {module}"
                for module in modules
                for root in forbidden
                if module == root or module.startswith(root + ".")
            )
    assert not offenders, f"the preflight reaches the catalog gate: {offenders}"


# --- not anticipated ----------------------------------------------------------


def test_the_preflight_return_type_cannot_express_a_verdict() -> None:
    """One field, and it is the context. There is nowhere to put a decision."""
    assert tuple(AuthorizedContext.model_fields) == ("context",)
    assert AuthorizedContext.model_fields["context"].annotation is PrincipalContext


@pytest.mark.parametrize(
    "field", ["allowed", "permitted", "verdict", "decision", "metrics", "scopes", "grants"]
)
def test_the_preflight_result_declares_no_verdict_field(field: str) -> None:
    assert field not in AuthorizedContext.model_fields


def test_the_resolver_protocol_cannot_be_asked_an_access_question() -> None:
    """One method, taking a principal reference and nothing else.

    A port that accepted a metric id would be a port through which this feature
    could ask — and eventually answer — the upstream question.
    """
    methods = [
        name
        for name in dir(AuthorizationContextResolver)
        if not name.startswith("_") and callable(getattr(AuthorizationContextResolver, name, None))
    ]
    assert methods == ["resolve"]

    # `eval_str` because the module uses postponed annotations, so the raw
    # signature would carry the string "str" and the assertion below would
    # compare text rather than the type it is about.
    signature = inspect.signature(AuthorizationContextResolver.resolve, eval_str=True)
    assert list(signature.parameters) == ["self", "principal_ref"]
    assert signature.parameters["principal_ref"].annotation is str


# --- not cached ---------------------------------------------------------------


def test_the_preflight_module_holds_no_mutable_state() -> None:
    """A cached verdict is a stored authorization.

    Module-level mutable containers are how one appears. Immutable constants and
    type definitions are fine; a dict, list or set at module scope is not.
    """
    offenders = [
        name
        for name, value in vars(context_preflight).items()
        if not name.startswith("__") and isinstance(value, dict | list | set)
    ]
    assert not offenders, f"module-level mutable state: {offenders}"


def test_no_module_in_this_package_memoises_an_authorization_answer() -> None:
    """``lru_cache`` over anything principal-shaped would be a stored grant.

    The message registry legitimately caches governed *content*, which is the
    same for every caller. Anything taking a principal is different in kind.
    """
    offenders: list[str] = []
    for path in _sources(SRC):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            decorated = any("cache" in ast.unparse(d).lower() for d in node.decorator_list)
            takes_principal = any(
                "principal" in arg.arg or "context" in arg.arg for arg in node.args.args
            ) or any("principal" in arg.arg or "context" in arg.arg for arg in node.args.kwonlyargs)
            if decorated and takes_principal:
                offenders.append(f"{path.relative_to(SRC).as_posix()}: {node.name}")
    assert not offenders, f"an authorization answer is memoised: {offenders}"


def test_two_calls_with_different_answers_do_not_influence_each_other() -> None:
    """Observable proof that nothing survives between calls."""
    from analytics_interaction.authorization.refusal import AuthorizationRefused

    from ..fixtures.counters import CountingResolver, Surfaces

    full = PrincipalContext(
        principal_ref="p-1",
        principal_type=PrincipalType.USER,
        authorization_scope="tenant-a",
        granted_access_tags=frozenset({"installs:read"}),
        authorization_policy_pin="authpol-1",
    )
    supplied = PrincipalContext(principal_ref="p-1", principal_type=PrincipalType.USER)

    assert resolve_authorization_context(
        supplied, resolver=CountingResolver(Surfaces(), answer=full)
    )
    with pytest.raises(AuthorizationRefused):
        resolve_authorization_context(supplied, resolver=CountingResolver(Surfaces(), answer=None))
    assert resolve_authorization_context(
        supplied, resolver=CountingResolver(Surfaces(), answer=full)
    )


# --- not shortcut -------------------------------------------------------------


def test_a_principal_holding_no_tags_resolves_rather_than_being_denied() -> None:
    """The subtle one. Refusing here would answer the upstream question early.

    "This principal holds no access tags" is a **complete** answer to who is
    asking. Whether that means they may see a particular metric is `001`'s gate 3
    and `002`'s preflight, evaluated once the metric is known. Denying them at
    step 2 would look like defence in depth and would in fact be this feature
    pre-computing a metric-level decision (`FR-088`).
    """
    from ..fixtures.counters import CountingResolver, Surfaces

    untagged = PrincipalContext(
        principal_ref="p-2",
        principal_type=PrincipalType.SERVICE_PRINCIPAL,
        authorization_scope="tenant-a",
        granted_access_tags=frozenset(),
        authorization_policy_pin="authpol-1",
    )
    authorized = resolve_authorization_context(
        PrincipalContext(principal_ref="p-2", principal_type=PrincipalType.SERVICE_PRINCIPAL),
        resolver=CountingResolver(Surfaces(), answer=untagged),
    )
    assert authorized.context.granted_access_tags == frozenset()


def test_the_preflight_does_not_narrow_or_widen_the_resolved_tag_set() -> None:
    """Carried whole. Not filtered to a subset, not topped up to a superset."""
    from ..fixtures.counters import CountingResolver, Surfaces

    tags = frozenset({"installs:read", "sessions:read", "revenue:read"})
    resolved = PrincipalContext(
        principal_ref="p-3",
        principal_type=PrincipalType.USER,
        authorization_scope="tenant-b",
        granted_access_tags=tags,
        authorization_policy_pin="authpol-2",
    )
    authorized = resolve_authorization_context(
        PrincipalContext(principal_ref="p-3", principal_type=PrincipalType.USER),
        resolver=CountingResolver(Surfaces(), answer=resolved),
    )
    assert authorized.context.granted_access_tags == tags
