"""The execution port — T097 (FR-028; SC-003).

**The sole submission path.** ADR 0010 authorised exactly one upstream change —
an additive composed entry point owned entirely by `packages/analytics_query/` —
and this is the narrow port over it:

```
ExecutionPort
    submit(request, *, authorized, auth_fingerprint, correlation_id)
        -> ExecutedAnswer
        |  a governed refusal carrying exactly one upstream reason code
```

**`003` composes nothing.** It calls the port and receives a result or a refusal.
Every ordering decision — authorization before cost, policy resolution, range
limits, execution-key derivation, the atomic observation read, full evaluation,
compile, guards, dry run, bounded execution, shape verification, the mid-flight
catalog-change check, assembly, suppression, revision resolution, ``finalise()``
and audit-before-release — belongs to `002` and happens inside its entry point.

**No `002` internal is imported.** Not `compile`, `execution`, `results`,
`decision`, `policy`, `observations` or `identity`; not `pipeline`; not any
private name. `T019`'s blocking gate asserts it, and this module's only upstream
imports are `analytics_query.execute` and `analytics_query.contracts`.

## The exported surface is four values wide

``submit`` takes **the request, who is asking, the binding that proves they
asked, and what to correlate the execution with.** Nothing else. Not a
collaborator, not a limit, not a policy, not a stage selector — the minimum
governed submission information this feature needs, and every annotation on it is
a concrete public type.

## Why the environment is opaque

An earlier draft held `002`'s fifteen collaborators as public fields, seven of
them typed ``Any``. That was wrong twice over, and both are worth naming:

* it **republished `002`'s internal collaborator list as this feature's own
  API**. A consumer coding against it would be coupled to `002`'s composition —
  the exact coupling ADR 0010's single entry point exists to prevent — and a
  collaborator added upstream would become a breaking change *here*;
* a public ``Any`` is a hole in the boundary, not a description of one. It would
  accept a result set, a warehouse response, rendered SQL, a query plan, a
  credential or an audit payload, and let each be handed onward as though the
  type system had approved it.

So the collaborators live inside :class:`ExecutionEnvironment`, which is
**opaque**: it validates at construction, exposes no public attribute, and cannot
be read back. The composition root binds one and passes it to the port; nobody
else can get anything out of it. What this feature publishes is a *token* meaning
"a governed environment was wired", not a description of what `002` needs.

The parameters that construct one are typed as precisely as the boundary allows.
`001`'s bundle, snapshot and metric version and `002`'s public ``ResultColumn``
are named. The seven whose declared types live behind ADR 0010's import ban are
typed ``object`` — **not** ``Any``: ``object`` accepts a value and permits
nothing to be done with it, so it cannot become a path to a result. There is
exactly one ``Any`` in this module, it is private, it is applied at the single
call site, and :func:`_opaque` is where it lives.

**One call per side, none speculative** (`FR-031`). Exactly one entry-point call
per ``submit``; no retry, no widening, no fallback — a second attempt with
different parameters would be gate-shopping.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from types import MappingProxyType
from typing import Any, Protocol, final, runtime_checkable

from analytics_query.contracts.request import AnalyticsQuery
from analytics_query.contracts.result import ResultColumn
from analytics_query.execute import ExecutedAnswer, execute_analytics_query
from semantic_catalog.contracts.metric import MetricVersion
from semantic_catalog.freshness.external import FreshnessSnapshot
from semantic_catalog.loader.bundle import Bundle

from ..authorization.context_preflight import AuthorizedContext
from ..contracts._base import ContractViolation
from ..contracts.reason_codes import InterpretationReasonCode
from ..identity.authorization_fingerprint import derive_authorization_fingerprint

__all__ = [
    "ExecutionEnvironment",
    "ExecutionPort",
    "GovernedExecutionPort",
]


@runtime_checkable
class ExecutionPort(Protocol):
    """What this feature is allowed to ask of the execution boundary.

    One method, four values. It cannot be asked to compile, to dry-run, to skip a
    gate, to reuse a previous execution or to widen a limit, because none of those
    is a parameter — the narrowness is the guarantee, not a rule about how to
    call it.

    No annotation on this Protocol is ``Any`` or ``object``. The whole point of a
    port is that what crosses it is named, and a permissive annotation on the one
    method that reaches the warehouse would make the port a hole with a docstring.
    """

    def submit(
        self,
        request: AnalyticsQuery,
        *,
        authorized: AuthorizedContext,
        auth_fingerprint: str,
        correlation_id: str,
    ) -> ExecutedAnswer:
        """Submit one governed request. One call, one result or one refusal.

        ``correlation_id`` is **supplied, never derived here.** Deriving it from
        the fingerprint would put a value constant across every request by one
        principal into `002`'s audit trail — a persistent pseudonymous tracker
        that correlates a *person* rather than an interaction, which is both the
        wrong grain and a disclosure nobody asked for. The caller passes the
        interpretation identity, which is what actually correlates the two sides
        of one comparison.
        """
        ...


#: What `002`'s entry point requires, named once. Used to validate a binding and
#: to unpack it — so a collaborator cannot be present at construction and absent
#: at the call, which is the failure a hand-written unpack eventually produces.
_REQUIRED: tuple[str, ...] = (
    "evaluate",
    "catalog_bundle",
    "ledger",
    "observations",
    "adapter",
    "sink",
    "context",
    "sample_catalog",
    "on",
    "catalog_release_id",
    "required_sources",
    "columns",
    "metric_version_ids",
    "freshness_snapshot",
    "metric_version",
)

#: Genuinely optional upstream: absent means "no dimension columns", which is a
#: real configuration rather than an incomplete one.
_OPTIONAL: tuple[str, ...] = ("dimension_columns",)


@final
class ExecutionEnvironment:
    """A bound governed environment. **Opaque by construction.**

    Holds what `002`'s entry point needs and offers **no way to read any of it
    back**: no public attribute, no accessor, no ``asdict``, no iteration. A
    consumer can pass one to a port and can do nothing else with it, which is
    what stops this feature's API from becoming a restatement of `002`'s
    internals.

    ``__slots__`` closes the other half: a collaborator cannot be attached to an
    instance after validation, so "bound" and "validated" are the same moment.

    Constructing one is not authorization and not readiness. It is wiring, and
    wiring an environment while every external record is open produces a port
    that refuses exactly as loudly as no port at all.
    """

    __slots__ = ("_bound",)

    def __init__(
        self,
        *,
        # --- typed as precisely as the boundary allows ------------------------
        catalog_bundle: Bundle,
        on: date,
        catalog_release_id: str,
        required_sources: frozenset[str],
        columns: tuple[ResultColumn, ...],
        metric_version_ids: tuple[str, ...],
        freshness_snapshot: FreshnessSnapshot,
        metric_version: MetricVersion,
        # --- declared by modules ADR 0010 forbids this feature to import ------
        #
        # ``object``, never ``Any``: it accepts the collaborator and permits
        # nothing to be done with it here. A value passed as one of these cannot
        # be called, indexed or attribute-accessed by this feature, so none of
        # them can become a path to a result value, a plan or a credential.
        evaluate: object,
        ledger: object,
        observations: object,
        adapter: object,
        sink: object,
        context: object,
        sample_catalog: Callable[[], object],
        dimension_columns: dict[str, str] | None = None,
    ) -> None:
        bound: dict[str, object] = {
            "evaluate": evaluate,
            "catalog_bundle": catalog_bundle,
            "ledger": ledger,
            "observations": observations,
            "adapter": adapter,
            "sink": sink,
            "context": context,
            "sample_catalog": sample_catalog,
            "on": on,
            "catalog_release_id": catalog_release_id,
            "required_sources": required_sources,
            "columns": columns,
            "metric_version_ids": metric_version_ids,
            "freshness_snapshot": freshness_snapshot,
            "metric_version": metric_version,
            "dimension_columns": dimension_columns,
        }
        missing = [name for name in _REQUIRED if bound[name] is None]
        if missing:
            # Fail at wiring time, not at the warehouse. A half-bound environment
            # that raised inside `002` would surface as an execution failure and
            # be read as a governance one.
            raise ContractViolation(
                InterpretationReasonCode.INTAKE_MALFORMED,
                f"the execution environment is incompletely bound: {sorted(missing)}",
            )
        self._bound = MappingProxyType(bound)

    def __repr__(self) -> str:
        """Deliberately says nothing.

        The default would print every collaborator — the ledger, the adapter, the
        policy context — into any traceback, log line or test failure that
        rendered one. An opaque object whose repr is transparent is not opaque.
        """
        return "ExecutionEnvironment(<bound>)"


@final
class GovernedExecutionPort:
    """The port, over one bound environment.

    Takes the environment as a single opaque value, so two sides of a comparison
    cannot be submitted against different catalog releases or different ledgers:
    there is one binding and no way to substitute part of it.
    """

    __slots__ = ("_environment",)

    def __init__(self, environment: ExecutionEnvironment) -> None:
        self._environment = environment

    def submit(
        self,
        request: AnalyticsQuery,
        *,
        authorized: AuthorizedContext,
        auth_fingerprint: str,
        correlation_id: str,
    ) -> ExecutedAnswer:
        """Submit through ADR 0010's composed entry point. **One call.**

        The fingerprint is checked first, so a request resolved under a different
        authorization context refuses **before** the warehouse is reached and the
        counted zero-call assertion has something true to observe.

        Nothing is caught and retried. `002`'s refusals carry exactly one
        upstream reason code and are passed through verbatim — restating one in
        this layer's vocabulary would let a consumer tell which layer refused
        from message style, which `FR-021` forbids.
        """
        if auth_fingerprint != derive_authorization_fingerprint(authorized):
            raise ContractViolation(
                InterpretationReasonCode.AUTHORIZATION_CONTEXT_UNRESOLVABLE,
                "the request was resolved under a different authorization context",
            )

        return execute_analytics_query(
            request,
            correlation_id=correlation_id,
            principal_ref=authorized.context.principal_ref,
            **_opaque(self._environment),
        )


def _opaque(environment: ExecutionEnvironment) -> Any:
    """Re-widen the bound collaborators for the one call that consumes them.

    **The only ``Any`` in this module, and it is private.** It appears on no
    exported signature, no Protocol, no contract and no reusable type — a reader
    of `003`'s API cannot encounter it, and a caller cannot route a value through
    it.

    It is unavoidable rather than convenient: `002` types these parameters with
    modules ADR 0010 forbids this feature to import, so there is no annotation
    this package may legally write that pyright would accept. The choice is
    between one contained widening at the call site and importing the internals
    the ADR exists to keep out. This is the smaller compromise, and it is stated
    where it happens.

    Nothing is decided, transformed or re-ordered here. The mapping goes out
    exactly as it was validated in.
    """
    # The adapter owns this binding: ``_bound`` is private to keep every *other*
    # module out, and this function is the environment's one sanctioned reader.
    bound: Any = environment._bound  # pyright: ignore[reportPrivateUsage]
    return dict(bound)
