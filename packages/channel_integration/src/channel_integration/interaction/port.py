"""The interaction port and its single adapter — T118 (`FR-104`, `SC-055`; ADR 0017).

```
InteractionPort.ask(intake: QuestionIntake)
    -> AnalyticsAnswer | ClarificationContract | GovernedRefusal
```

**One operation.** No second entry, no batch form, no streaming form, no "explain" form, no options
bag. `004` constructs the `QuestionIntake` and nothing else.

## The adapter copies; it does not derive

`intake_from_envelope` fills `003`'s five intake fields **by copying**. It defaults nothing, infers
nothing and derives nothing:

* `as_of` absent stays absent. An absent pin means current-definition resolution upstream, and
  filling it from `reference_date` would silently pin every question to the day it was asked;
* `language` is **carried as written and decided upstream**. `contracts/envelope.py` types it as a
  plain string deliberately and says where the governed check belongs: "the governed check happens
  where the ``QuestionIntake`` is constructed, at the interaction boundary (Phase D, T118), which is
  the layer that owns it". `003` types the field as `DeclaredLanguage`, a closed enum with one
  member today, so the intake is built with `model_validate` and the string is handed to **`003`'s
  own model** to accept or reject. An unsupported declaration raises `003`'s `ValidationError`,
  from `003`'s code, against `003`'s set. Nothing here enumerates a supported language, compares
  against one, or classifies the failure — a local set or a local reason code would be exactly the
  re-implementation `FR-093` forbids, and picking a `ChannelReasonCode` for it would be this layer
  deciding what an upstream language refusal means;
* `text` is already normalised by the inbound sequence. Nothing here rewrites it — a question
altered
  on the way in is not the question that was asked.

## The principal context is required, not derived — and `004` has no source for one

`QuestionIntake.principal` is a `PrincipalContext`: a principal reference **plus** its type, its
authorization scope, its granted access tags and its authorization-policy pin. A `ChannelEnvelope`
carries only `principal_ref`, and `ChannelIdentityBinding` resolves only `principal_ref`. **Nothing
in this feature produces the other four fields**, measured across `src/` on 2026-08-19.

So `intake_from_envelope` takes the context as an argument with **no default**. It is not optional
and it is not constructible here:

* defaulting `principal_type`, `authorization_scope` or `granted_access_tags` would be this feature
  **inventing an authorization** it never resolved — the one thing every layer of this system is
  built to prevent;
* deriving them from the binding would be worse, because a binding is an identity mapping and says
  nothing about what that identity may see.

`contracts/interaction-port.md` §1 says the five fields are filled "from the `ChannelEnvelope`". For
four of them that is exact. For the principal context it is not achievable as written, and the gap
is recorded rather than closed by invention: whoever calls `submit` must already hold a resolved
context, and today no `004` surface holds one. Closing it needs a governed decision about where a
channel principal's authorization context comes from — the same class of decision `D-27` covers for
identity, and not one this module may take.

## Production has no port, and that is the shipped state

ADR 0017 was Accepted on 2026-08-17, and acceptance implements nothing. `submit` takes the port as
an argument and **refuses when none is supplied** with `INTERACTION_BOUNDARY_UNAVAILABLE`
(`FR-104`).

That refusal is not a placeholder awaiting a fallback. There is no locally composed substitute and
there must not be one: a second composition of `003`'s sixteen steps is exactly what ADR 0017
forbids, and it would be a second interpretation path no upstream gate could see.

**No flag, environment setting or deployment mode selects a port** (`FR-072`, `SC-034`). The
argument is the only way one arrives, which is what keeps the double reachable from `tests/` alone.

## What this module deliberately does not do

It does not interpret an outcome, classify one, or read a refusal beyond its code. It does not touch
the audit trail: emitting `SUBMITTED` belongs to the caller that owns the sequence, because a port
emitting its own stage would make the stage order a property of this module rather than of the
composition.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from analytics_interaction.contracts.answer import AnalyticsAnswer
from analytics_interaction.contracts.clarification import ClarificationContract
from analytics_interaction.contracts.intake import PrincipalContext, QuestionIntake

from channel_integration.contracts._base import ChannelViolation
from channel_integration.contracts.reason_codes import ChannelReasonCode

if TYPE_CHECKING:
    from channel_integration.contracts.envelope import ChannelEnvelope

__all__ = [
    "INTERACTION_BOUNDARY_DETAIL",
    "InteractionPort",
    "intake_from_envelope",
    "submit",
]

#: The operator-facing detail for a refusal at this boundary. A constant rather than a formatted
#: string: it names no channel, no principal and no question, so one refusal cannot be told from
#: another by reading it.
INTERACTION_BOUNDARY_DETAIL = (
    "the composed interaction entry point is not constructible, and no locally composed "
    "substitute exists"
)


@runtime_checkable
class InteractionPort(Protocol):
    """The one upstream operation this feature may reach.

    Declared as a `Protocol` rather than an abstract base so an implementation never inherits from
    `004`: the dependency points one way, and a base class would let this feature's shape reach
    upstream.

    Returning a union rather than raising is deliberate. A refusal is an **outcome** here, carried
    with its upstream code and its already-resolved wording, and a caller that had to catch it could
    forget to. The three members are the whole of what an interaction can be.
    """

    def ask(self, intake: QuestionIntake) -> AnalyticsAnswer | ClarificationContract | object:
        """Submit one question. One call, one outcome.

        The third member of the return union is `003`'s `GovernedRefusal`, which this feature does
        not name as a type: it is carried and rendered, never constructed here, so importing it
        would add an allowlist entry for a use that does not exist.
        """
        ...


def intake_from_envelope(envelope: ChannelEnvelope, principal: PrincipalContext) -> QuestionIntake:
    """`003`'s five intake fields, four copied from the envelope and one supplied.

    ``principal`` is positional and has **no default**, so a caller cannot omit it and receive an
    invented one. See this module's docstring for why `004` cannot construct it.

    Built through `model_validate` rather than by keyword so the declared language reaches `003`'s
    own field validator as the string the sender wrote. `QuestionIntake.language` is a
    `DeclaredLanguage`; coercing it here would put the supported set in this layer.

    The principal's own reference is asserted to agree with the envelope's. They are two statements
    about the same principal arriving by different routes — the binding resolved one, the caller
    resolved the other — and a disagreement means the question is about to be asked on behalf of
    somebody other than the sender.
    """
    if principal.principal_ref != envelope.principal_ref:
        raise ChannelViolation(
            ChannelReasonCode.CHANNEL_IDENTITY_UNMAPPED,
            "the supplied authorization context is for a different principal than the envelope",
        )

    return QuestionIntake.model_validate(
        {
            "text": envelope.text,
            "language": envelope.language,
            "reference_date": envelope.reference_date,
            "as_of": envelope.as_of,
            "principal": principal,
        }
    )


def submit(
    envelope: ChannelEnvelope,
    principal: PrincipalContext,
    *,
    port: InteractionPort | None,
) -> AnalyticsAnswer | ClarificationContract | object:
    """Convert the envelope and submit it, or refuse because no port exists.

    ``port`` has **no default**. An omission is a `TypeError` at the call site rather than a silent
    fall through to the refusal, because "nobody supplied a port" and "the deployment has none" are
    different facts and only the second is a governed outcome.

    Passing ``None`` is the second fact, and it is the shipped one: production constructs no port,
    so every message refuses. The refusal is raised rather than returned because it is `004`'s own
    governed violation, not an upstream outcome — the union this function returns carries only what
    the port itself produced.

    The boundary refusal is checked **before** the intake is built. A caller with no port learns
    nothing about whether its envelope would have converted, which keeps an unavailable boundary
    from becoming a validation oracle.
    """
    if port is None:
        raise ChannelViolation(
            ChannelReasonCode.INTERACTION_BOUNDARY_UNAVAILABLE,
            INTERACTION_BOUNDARY_DETAIL,
        )
    return port.ask(intake_from_envelope(envelope, principal))
