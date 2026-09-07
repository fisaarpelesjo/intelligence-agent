"""No speculative requests — T093 (FR-023, FR-031; SC-016).

    Only the requests the intent requires are constructed, and a refusal
    terminates the sequence. — `tasks.md` T093

    Evidence: no widening, narrowing, retry-with-different-parameters or
    gate-shopping path exists.

The failure mode has a name and a shape. A system that gets a denial and tries
again with a smaller date range, fewer dimensions, a different source or a
coarser grain is **probing the gates** — and each attempt that succeeds tells the
caller something about what the previous one was refused for. Done repeatedly, it
maps the authorization boundary from the outside.

So the property is counted, not asserted: **one intent, one request**, and a
refusal produces **zero**. The count is what makes "no retry path" observable —
a retry loop is invisible in a passing test that only checks the final answer.

`FR-031` adds the execution half: exactly one call per side, none speculative.
The count itself is `T099`'s, at the boundary. What is asserted here is the
structural half — that each governed entry point has exactly **one** call site in
this feature's source, and it is the module whose job that call is. A second
caller is a second path, and a second path is where a retry loop lives.
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pytest
from analytics_query.contracts.request import AnalyticsQuery

import analytics_interaction
from analytics_interaction.authorization.context_preflight import AuthorizedContext
from analytics_interaction.contracts._base import ContractViolation
from analytics_interaction.contracts.intake import DeclaredLanguage
from analytics_interaction.contracts.intent import ResolvedIntent, ResolvedPeriod
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode as Code
from analytics_interaction.contracts.request_build import build_analytics_query
from analytics_interaction.interpretation.assemble_intent import assemble_resolved_intent

from ..conftest import JULY, REFERENCE, authorize, governed_resolution
from ..fixtures.counters import SURFACES, Surfaces

pytestmark = pytest.mark.integration

SRC = Path(inspect.getfile(analytics_interaction)).resolve().parent


@dataclass
class CountingBuilder:
    """Counts every request this feature constructs.

    Wraps the real builder rather than replacing it, so the count is of actual
    constructions and not of a stand-in that might behave differently.
    """

    built: list[AnalyticsQuery] = field(default_factory=list[AnalyticsQuery])

    def build(
        self, intent: ResolvedIntent, *, authorized: AuthorizedContext, fingerprint: str
    ) -> AnalyticsQuery:
        request = build_analytics_query(intent, authorized=authorized, auth_fingerprint=fingerprint)
        self.built.append(request)
        return request


def _intent(
    period: ResolvedPeriod,
    pair: tuple[AuthorizedContext, str],
    *,
    identifiers: tuple[str, ...] = ("installs",),
) -> ResolvedIntent:
    authorized, fingerprint = pair
    return assemble_resolved_intent(
        tuple(governed_resolution(identifier) for identifier in identifiers),
        authorized=authorized,
        auth_fingerprint=fingerprint,
        period=period,
        language=DeclaredLanguage.PT_BR,
        reference_date=REFERENCE,
        as_of=None,
        catalog_release="r-1",
        policy_version="pol-1",
        vocabulary_version="voc-1",
    )


# --- one intent, one request ---------------------------------------------------


def test_one_intent_produces_exactly_one_request(
    resolved_intent: ResolvedIntent, authorized_pair: tuple[AuthorizedContext, str]
) -> None:
    authorized, fingerprint = authorized_pair
    builder = CountingBuilder()
    builder.build(resolved_intent, authorized=authorized, fingerprint=fingerprint)
    assert len(builder.built) == 1


def test_a_multi_metric_intent_still_produces_one_request(
    july_period: ResolvedPeriod, authorized_pair: tuple[AuthorizedContext, str]
) -> None:
    """`002`'s ``metrics`` takes a list, so several metrics are one request.

    Splitting them would double the bill and duplicate machinery `002` owns.
    """
    authorized, fingerprint = authorized_pair
    intent = _intent(july_period, authorized_pair, identifiers=("installs", "sessions"))
    builder = CountingBuilder()
    builder.build(intent, authorized=authorized, fingerprint=fingerprint)

    assert len(builder.built) == 1
    assert builder.built[0].metrics == ("installs", "sessions")


# --- a refusal constructs nothing ----------------------------------------------


def test_an_authorization_mismatch_constructs_no_request(
    resolved_intent: ResolvedIntent, authorized_pair: tuple[AuthorizedContext, str]
) -> None:
    """Counted zero, and the refusal comes before any request exists."""
    authorized, _ = authorized_pair
    builder = CountingBuilder()
    with pytest.raises(ContractViolation) as caught:
        builder.build(resolved_intent, authorized=authorized, fingerprint="not-the-fingerprint")

    assert caught.value.code is Code.AUTHORIZATION_CONTEXT_UNRESOLVABLE
    assert builder.built == []


def test_an_unresolved_slot_constructs_no_request(
    july_period: ResolvedPeriod, authorized_pair: tuple[AuthorizedContext, str]
) -> None:
    """The refusal happens at assembly, so there is no intent to build from."""
    authorized, fingerprint = authorized_pair
    builder = CountingBuilder()
    unresolved = governed_resolution("installs").model_copy(update={"resolved_to": None})

    with pytest.raises(ContractViolation) as caught:
        intent = assemble_resolved_intent(
            (unresolved,),
            authorized=authorized,
            auth_fingerprint=fingerprint,
            period=july_period,
            language=DeclaredLanguage.PT_BR,
            reference_date=REFERENCE,
            as_of=None,
            catalog_release="r-1",
            policy_version="pol-1",
            vocabulary_version="voc-1",
        )
        builder.build(intent, authorized=authorized, fingerprint=fingerprint)

    assert caught.value.code is Code.INTENT_AMBIGUOUS
    assert builder.built == []


def test_a_missing_period_constructs_no_request(
    authorized_pair: tuple[AuthorizedContext, str],
) -> None:
    authorized, fingerprint = authorized_pair
    builder = CountingBuilder()
    with pytest.raises(ContractViolation) as caught:
        intent = assemble_resolved_intent(
            (governed_resolution("installs"),),
            authorized=authorized,
            auth_fingerprint=fingerprint,
            period=None,
            language=DeclaredLanguage.PT_BR,
            reference_date=REFERENCE,
            as_of=None,
            catalog_release="r-1",
            policy_version="pol-1",
            vocabulary_version="voc-1",
        )
        builder.build(intent, authorized=authorized, fingerprint=fingerprint)

    assert caught.value.code is Code.PERIOD_EXPRESSION_NOT_GOVERNED
    assert builder.built == []


def test_a_refusal_returns_no_partial_intent_alongside_it(
    july_period: ResolvedPeriod, authorized_pair: tuple[AuthorizedContext, str]
) -> None:
    """A refusal that also handed back something usable would not be a refusal."""
    authorized, fingerprint = authorized_pair
    outcome: object = None
    try:
        outcome = assemble_resolved_intent(
            (governed_resolution("installs").model_copy(update={"resolved_to": None}),),
            authorized=authorized,
            auth_fingerprint=fingerprint,
            period=july_period,
            language=DeclaredLanguage.PT_BR,
            reference_date=REFERENCE,
            as_of=None,
            catalog_release="r-1",
            policy_version="pol-1",
            vocabulary_version="voc-1",
        )
    except ContractViolation as refusal:
        outcome = refusal
    assert not isinstance(outcome, ResolvedIntent)


def test_no_surface_is_touched_while_building_a_request(
    resolved_intent: ResolvedIntent, authorized_pair: tuple[AuthorizedContext, str]
) -> None:
    """Construction is not execution. Zero on all six cost surfaces."""
    surfaces = Surfaces()
    authorized, fingerprint = authorized_pair
    build_analytics_query(resolved_intent, authorized=authorized, auth_fingerprint=fingerprint)
    assert surfaces.counts() == dict.fromkeys(SURFACES, 0)


# --- no widening, narrowing or gate-shopping path exists -----------------------


RETRY_NAMES = (
    "retry",
    "reattempt",
    "widen",
    "narrow_range",
    "broaden",
    "shrink",
    "fallback_query",
    "alternative_request",
    "try_again",
    "backoff",
    "attempt_",
)


@pytest.mark.parametrize("name", RETRY_NAMES)
def test_no_module_declares_a_retry_or_widening_path(name: str) -> None:
    """A retry with different parameters is gate-shopping, however it is spelled."""
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            identifier = (
                node.name
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
                else node.id
                if isinstance(node, ast.Name)
                else node.arg
                if isinstance(node, ast.arg)
                else ""
            )
            if name in identifier.lower():
                offenders.append(f"{path.relative_to(SRC).as_posix()}: {identifier}")
    assert not offenders, f"a retry or widening path exists: {offenders}"


def test_the_builder_contains_no_loop() -> None:
    """One intent in, one request out. A loop is where a second attempt lives."""
    tree = ast.parse(inspect.getsource(build_analytics_query))
    loops = [
        ast.unparse(node)[:60]
        for node in ast.walk(tree)
        if isinstance(node, ast.For | ast.While | ast.AsyncFor)
    ]
    assert not loops, f"the builder loops: {loops}"


def test_the_builder_constructs_exactly_one_request_object() -> None:
    """Two construction sites would be two requests one call could emit."""
    tree = ast.parse(inspect.getsource(build_analytics_query))
    constructions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "AnalyticsQuery"
    ]
    assert len(constructions) == 1


#: Which module owns each governed call. A call to one of these names from
#: anywhere else is a second path to the thing it reaches.
#:
#: This replaces a Phase-8-era assertion that no execution entry point was called
#: **anywhere** in the source tree. That assertion was true only while Phase 9
#: was unwritten: the port and the verdict are exactly the modules whose job is
#: to make those calls, so the phase-scoped form would have had to be deleted the
#: moment they arrived — and a guard that expires the first time the code it
#: guards exists protects nothing. Ownership is the durable form of the same
#: property, and it is strictly stronger: the old check said "nobody calls this
#: yet", this one says "exactly one module ever may".
CALL_OWNERS: dict[str, str] = {
    # ADR 0010's composed entry point. One caller, forever.
    "execute_analytics_query": "execution/port.py",
    # `001`'s evaluation. One call site, so a comparison verdict cannot be
    # assembled from two single-side evaluations (`FR-065`).
    "evaluate": "comparison/verdict.py",
}

#: Called from nowhere in this feature's source, at any phase. ``pipeline`` is
#: `002`'s steps 1-7; reaching it directly yields a preflight decision with no
#: execution behind it, which is the single-path clause's exact failure mode.
NEVER_CALLED: frozenset[str] = frozenset({"run_until_evaluation"})


def _governed_calls(source: str, filename: str = "<test>") -> list[tuple[int, str]]:
    """Every call by callee name. AST, so a mention in prose is not a call."""
    tree = ast.parse(source, filename=filename)
    found: list[tuple[int, str]] = []
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
        if called in CALL_OWNERS or called in NEVER_CALLED:
            found.append((node.lineno, called))
    return found


def _source_files() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def test_each_governed_call_is_made_only_by_the_module_that_owns_it() -> None:
    """One caller per entry point, and it is the one whose job it is."""
    offenders: list[str] = []
    for path in _source_files():
        relative = path.relative_to(SRC).as_posix()
        for lineno, called in _governed_calls(path.read_text(encoding="utf-8"), str(path)):
            owner = CALL_OWNERS.get(called)
            if owner is None or owner != relative:
                offenders.append(f"{relative}:{lineno} calls {called}()")
    assert not offenders, f"a governed call was made outside its owning module: {offenders}"


def test_the_owning_modules_actually_make_their_calls() -> None:
    """An owner that calls nothing makes the ownership map a dead list.

    Without this, deleting the port's one call site would leave the guard above
    passing — vacuously, over a rule about a call nobody makes.
    """
    for called, owner in CALL_OWNERS.items():
        path = SRC / owner
        assert path.is_file(), f"{owner} owns {called}() but does not exist"
        names = [name for _, name in _governed_calls(path.read_text(encoding="utf-8"), str(path))]
        assert called in names, f"{owner} owns {called}() but never calls it"


@pytest.mark.parametrize(
    "planted",
    [
        "from analytics_query.execute import execute_analytics_query\n"
        "def go(r):\n    return execute_analytics_query(r)\n",
        "def go(evaluate, request, bundle):\n    return evaluate(request, bundle)\n",
        "def go(state):\n    return run_until_evaluation(state)\n",
        "def go(mod, r):\n    return mod.execute_analytics_query(r)\n",
    ],
)
def test_the_ownership_guard_catches_a_planted_call(planted: str) -> None:
    """The narrowing is not a hole.

    Each planted source is a real second path — a direct import and call, an
    injected evaluator invoked outside the verdict, `002`'s pipeline reached
    directly, and the attribute form the ``ast.Name``-only check would miss.
    """
    assert _governed_calls(planted), "a governed call was not detected"


def test_the_builder_imports_only_002s_public_request_contract() -> None:
    """ADR 0010: no compiler, pipeline, adapter, policy, ledger or execution module."""
    from analytics_interaction.contracts import request_build

    source = Path(inspect.getfile(request_build)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    upstream = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module
        and node.module.split(".")[0] in {"analytics_query", "semantic_catalog"}
    }
    assert upstream == {"analytics_query.contracts.request"}


# --- determinism ----------------------------------------------------------------


def test_the_same_intent_yields_a_byte_identical_request(
    resolved_intent: ResolvedIntent, authorized_pair: tuple[AuthorizedContext, str]
) -> None:
    authorized, fingerprint = authorized_pair
    first = build_analytics_query(
        resolved_intent, authorized=authorized, auth_fingerprint=fingerprint
    )
    second = build_analytics_query(
        resolved_intent, authorized=authorized, auth_fingerprint=fingerprint
    )
    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


def test_a_fresh_authorization_of_the_same_context_yields_the_same_request(
    july_period: ResolvedPeriod,
) -> None:
    """The fingerprint is of the context, not of the act of authorising.

    Two preflights over unchanged grants must agree, or a genuine retry would
    produce a different request from the first attempt.
    """
    from analytics_interaction.identity.authorization_fingerprint import (
        derive_authorization_fingerprint,
    )

    rendered: set[str] = set()
    for _ in range(3):
        authorized = authorize()
        fingerprint = derive_authorization_fingerprint(authorized)
        intent = _intent(july_period, (authorized, fingerprint))
        request = build_analytics_query(intent, authorized=authorized, auth_fingerprint=fingerprint)
        rendered.add(request.model_dump_json())
    assert len(rendered) == 1


def test_the_metric_order_the_question_used_is_preserved(
    july_period: ResolvedPeriod, authorized_pair: tuple[AuthorizedContext, str]
) -> None:
    """Question order, not sorted order — the intent records what was asked.

    The identity sorts them, because two orderings ask the same thing; the
    request does not, because it is the question as written.
    """
    authorized, fingerprint = authorized_pair
    reversed_intent = _intent(july_period, authorized_pair, identifiers=("sessions", "installs"))
    request = build_analytics_query(
        reversed_intent, authorized=authorized, auth_fingerprint=fingerprint
    )
    assert request.metrics == ("sessions", "installs")


def test_no_clock_or_randomness_participates_in_construction() -> None:
    """A request that varied with the clock would not be reproducible."""
    tree = ast.parse(inspect.getsource(build_analytics_query))
    calls = {
        node.func.attr if isinstance(node.func, ast.Attribute) else ast.unparse(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    for forbidden in ("today", "now", "utcnow", "random", "uuid4", "getpid"):
        assert forbidden not in calls


def test_the_period_boundaries_are_carried_exactly(
    resolved_intent: ResolvedIntent, authorized_pair: tuple[AuthorizedContext, str]
) -> None:
    """No widening by a day, no inclusive-exclusive reinterpretation."""
    authorized, fingerprint = authorized_pair
    request = build_analytics_query(
        resolved_intent, authorized=authorized, auth_fingerprint=fingerprint
    )
    assert (request.date_range.start, request.date_range.end) == JULY
    assert request.date_range.start == date(2026, 7, 1)
