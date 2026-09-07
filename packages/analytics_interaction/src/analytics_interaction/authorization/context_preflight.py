"""Authorization-context preflight — T044 (FR-029, FR-087, FR-088, FR-089; SC-053).

`FR-089` is this module's: an unauthenticated principal, and one whose context cannot be
resolved completely, are two of the six ways below — and all six produce the one governed
outcome, so which occurred is never disclosed.

**Step 2 of the sixteen-step sequence, and the entire pre-authorization surface
together with step 1.** Nothing downstream runs until this returns.

ADR 0009 established for `002` that no unauthorized principal may cause a
warehouse read, a ledger entry or a limit disclosure. This feature adds three new
cost surfaces — catalog reads, model tokens and candidate resolution — and the
same rule extends to them (`FR-087` to `FR-091`).

**What this is, and what it is emphatically not.**

| | |
|---|---|
| **Is** | Resolving **who is asking** — principal type, authorization scope,
  granted access tags, governed authorization-policy pin. Complete, or refuse |
| **Is not** | Deciding **what they may see.** Metric-level access stays with
  `001`'s authorization gate and `002`'s preflight, evaluated once the metric
  is known |

The distinction is not pedantic. Metric-level authorization *cannot* run before
interpretation, because the metric is not known until interpretation resolves it.
`FR-088` therefore forbids this feature from re-implementing, anticipating,
caching, pre-computing or shortcutting that decision — and this module makes,
stores and returns no access verdict of any kind. It returns a context.

**The context is passed through unchanged** (`FR-029`). No access tag is created,
named, inferred, elevated, translated or assembled here. The resolver's answer is
carried verbatim to the catalog surface and the execution port, and `T050`
compares it field by field at both boundaries.

**Everything is injected; nothing is ambient.** ``resolver`` is required and
keyword-only. There is no default implementation, no module-level singleton, no
environment lookup, no credential discovery and no fallback that admits a caller
when the collaborator is missing. A missing or failing resolver refuses.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..contracts._base import InteractionModel
from ..contracts.intake import PrincipalContext
from .refusal import AuthorizationRefused

__all__ = [
    "AuthorizationContextResolver",
    "AuthorizedContext",
    "resolve_authorization_context",
]


@runtime_checkable
class AuthorizationContextResolver(Protocol):
    """The identity system, as this feature is allowed to see it.

    One method, one direction: given an opaque principal reference, return the
    authorization context that principal actually holds — or ``None`` if it
    cannot be resolved.

    Deliberately narrow. It cannot be asked *whether a principal may see a
    metric*, because that question belongs upstream and a port that could ask it
    would be a port through which this feature could answer it.

    The implementation is supplied by the deployment. This package ships none:
    a default resolver would be a default answer to "who is asking", which is the
    one question that must never have one.
    """

    def resolve(self, principal_ref: str) -> PrincipalContext | None:
        """The context for ``principal_ref``, or ``None`` when unresolvable.

        Raising is also permitted and is treated identically — see
        ``resolve_authorization_context``.
        """
        ...


class AuthorizedContext(InteractionModel):
    """Proof that step 2 completed, carrying the context it resolved.

    A separate type rather than a bare ``PrincipalContext`` so that "this context
    was resolved" is expressible in a signature. A downstream function taking an
    ``AuthorizedContext`` cannot be handed an unresolved one by accident, and the
    ordering requirement stops being a convention somebody has to remember.

    It carries **no verdict**. There is no ``allowed``, no ``permitted_metrics``,
    no cached decision — deliberately, because any such field would be this
    feature holding a metric-level answer (`FR-088`).

    "Unchanged" here means **equal, field for field**, not the same object.
    ``PrincipalContext`` is frozen and the base revalidates instances, so
    assignment produces an equal value rather than the identical one. Value
    equality is the right notion anyway: `FR-029` is about the tag set not being
    widened, translated or reassembled, and object identity would make the
    property depend on pydantic's copying behaviour rather than on the
    authorization it describes.
    """

    context: PrincipalContext

    @property
    def principal_ref(self) -> str:
        """Convenience for audit and cost attribution (`FR-091`)."""
        return self.context.principal_ref


def _asserted_by_caller(supplied: PrincipalContext, resolved: PrincipalContext) -> list[str]:
    """Fields the caller supplied that disagree with the identity system.

    A caller supplying their own scope, tag set or policy pin is **asserting**
    authorization rather than holding it. The resolver's answer is authoritative,
    so the disagreement is not silently overwritten — it is refused, because a
    request that tried to widen its own authorization is not a request that
    should proceed under the narrower answer.

    A field the caller left unset is not an assertion, so it is not compared.
    """
    disagreements: list[str] = []
    if supplied.principal_type != resolved.principal_type:
        disagreements.append("principal_type")
    if supplied.authorization_scope is not None and (
        supplied.authorization_scope != resolved.authorization_scope
    ):
        disagreements.append("authorization_scope")
    if (
        supplied.granted_access_tags
        and supplied.granted_access_tags != resolved.granted_access_tags
    ):
        disagreements.append("granted_access_tags")
    if supplied.authorization_policy_pin is not None and (
        supplied.authorization_policy_pin != resolved.authorization_policy_pin
    ):
        disagreements.append("authorization_policy_pin")
    return disagreements


def _is_incomplete(resolved: PrincipalContext) -> bool:
    """Whether any of the four parts failed to resolve.

    ``authorization_scope`` and ``authorization_policy_pin`` are optional on the
    contract because the *caller* need not supply them; after resolution they are
    required, and absence means the identity system could not answer.

    **An empty tag set is resolved, not incomplete.** A principal who holds no
    access tags is a complete answer to "who is asking" — they simply hold
    nothing. Refusing them here would be deciding *what they may see*, which is
    `001`'s gate 3 and `002`'s preflight, and would be exactly the metric-level
    shortcut `FR-088` forbids. They will be denied upstream, once a metric is
    known, by the component that owns that decision.
    """
    return not resolved.authorization_scope or not resolved.authorization_policy_pin


def resolve_authorization_context(
    supplied: PrincipalContext,
    *,
    resolver: AuthorizationContextResolver | None,
) -> AuthorizedContext:
    """Resolve the principal's authorization context completely, or refuse.

    Six ways to fail, **one** governed outcome. Which one occurred is never
    disclosed to the caller — distinguishing them would describe the shape of the
    identity system to someone who has not authenticated to it
    (`contracts/reason-codes.md` §3).

    1. No resolver was supplied. The collaborator is required; its absence is a
       refusal, never a bypass.
    2. The resolver raised. Fail closed: an identity system that errored has not
       said the caller is anyone.
    3. The resolver returned ``None`` — the principal is unknown.
    4. The resolver returned something that is not a ``PrincipalContext``.
    5. The resolved context is incomplete — see ``_is_incomplete``.
    6. The resolver answered about a different principal, or the caller asserted
       an authorization they do not hold.

    Deterministic: the same supplied context and the same resolver answer always
    produce the same decision. No clock is read, no state is kept between calls,
    and nothing is cached — a cache here would be a stored authorization, which
    is the thing statelessness exists to avoid.

    Returns the resolver's context **unchanged**. Not a copy with normalised
    tags, not a merge with what the caller supplied, not a superset.
    """
    if resolver is None:
        raise AuthorizationRefused()

    try:
        resolved = resolver.resolve(supplied.principal_ref)
    except Exception as exc:
        # Deliberately broad. An identity system can fail in ways this package
        # cannot enumerate, and every one of them means the same thing: the
        # caller was never established. Narrowing this would let an
        # unanticipated failure propagate as something other than a refusal.
        raise AuthorizationRefused() from exc

    if not isinstance(resolved, PrincipalContext):
        raise AuthorizationRefused()

    if resolved.principal_ref != supplied.principal_ref:
        raise AuthorizationRefused()

    if _is_incomplete(resolved):
        raise AuthorizationRefused()

    if _asserted_by_caller(supplied, resolved):
        raise AuthorizationRefused()

    return AuthorizedContext(context=resolved)
