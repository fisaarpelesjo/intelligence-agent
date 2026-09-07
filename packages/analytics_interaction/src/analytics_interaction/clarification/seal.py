"""The seal port — T112 (FR-078; SC-044).

**Tamper-evidence over every field, key material injected, never embedded.**

A clarification contract is transported by the caller and resubmitted. Without a
seal, the rounds consumed, the round bound, the expiry, the candidate set and the
principal binding are all **caller-editable** — which is to say absent. The seal
is what makes a self-contained contract safe to hand out.

## No cryptographic choice is made here

`D-21` is undeclared and neither `contracts/clarification-contract.md` nor
ADR 0014 names an algorithm, a key length or a construction. So this module
declares a **provider-neutral port** and picks nothing:

```
SealPort
    seal(preimage: str, *, key_id: str) -> Seal
    verify(preimage: str, seal: Seal) -> bool
```

No default algorithm, no generated key, no hardcoded secret, no environment
lookup, no ambient secret store, and no fallback that seals with something
weaker. Choosing HMAC-SHA256 here would be inventing the governed decision `D-21`
exists to obtain — and a convenience default is exactly how a fail-closed gate
stops being one.

## What the seal covers

**Every semantically relevant field except the seal value itself.** Not a subset,
not "the important ones": a field outside the preimage is a field an attacker can
change without detection, and the fields most worth changing — ``rounds_consumed``,
``expires_at``, ``auth_fingerprint`` — are the ones a hand-picked subset tends to
omit last.

:data:`SEALED_FIELDS` is derived from the contract's own declared fields minus
``seal``, so a field added to ``ClarificationContract`` joins the preimage
automatically. `T112`'s suite asserts the derivation rather than trusting it.

``key_id`` and ``algorithm`` **are** covered: a contract resealed under a
different key or a downgraded algorithm is a different contract, and leaving
either outside the preimage would permit exactly that substitution.

## Canonical serialisation

Deterministic and unambiguous. Keys sorted, no whitespace, `null` for absent,
lists in declaration order, and every value rendered through the contract's own
JSON mode so a ``datetime`` has one spelling rather than two. Two structurally
identical contracts produce one preimage on every platform and in every process;
a preimage that varied with dict ordering would make verification fail at random,
which is worse than no seal because it would be diagnosed as flakiness.

The separators matter more than they look: without a delimiter that cannot occur
inside a value, ``{"a": "b|c"}`` and ``{"a|b": "c"}`` could render alike. JSON
with sorted keys has no such ambiguity, so JSON is what this uses.

## Fail-closed while `D-21` is undeclared

Both entry points call the gate **first**. With the shipped readiness records no
seal is constructible, no contract can be issued, and an ambiguous question
refuses instead of clarifying — a real capability loss, stated rather than
engineered around.

``DECLARED_WITHOUT_EVIDENCE`` and ``EVIDENCE_WITHOUT_DECLARATION`` are both
unavailable. A flag with nothing behind it and a reference nobody declared are
different governance failures and identical permissions.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from ..compliance.gates import CapabilitySurface, require_surface
from ..contracts._base import ContractViolation
from ..contracts.clarification import ClarificationContract, Seal
from ..contracts.reason_codes import InterpretationReasonCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterable

    from ..compliance.readiness import ReadinessRecord

__all__ = [
    "SEALED_FIELDS",
    "SealPort",
    "canonical_preimage",
    "issue_seal",
    "verify_seal",
]

#: Every contract field the seal covers, derived from the contract itself. The
#: seal cannot cover its own value, so ``seal`` is excluded and its ``key_id``
#: and ``algorithm`` are folded in separately by :func:`canonical_preimage`.
SEALED_FIELDS: tuple[str, ...] = tuple(
    name for name in ClarificationContract.model_fields if name != "seal"
)


@runtime_checkable
class SealPort(Protocol):
    """What this feature is allowed to ask of a `D-21` sealing provider.

    Two methods over an opaque string. The port cannot be asked to *generate* a
    key, to *choose* an algorithm, to weaken one, or to seal a partial preimage —
    none of those is a parameter.

    ``key_id`` names a key the deployment already holds. It is not a key, and
    nothing in this package can turn one into the other.
    """

    def seal(self, preimage: str, *, key_id: str) -> Seal:
        """Produce tamper-evidence over ``preimage`` using the named key."""
        ...

    def verify(self, preimage: str, seal: Seal) -> bool:
        """Whether ``seal`` still matches ``preimage``. **A bool, not a raise.**

        Returning a bool keeps the provider from deciding what a mismatch
        *means*: the governed refusal and its reason code belong to this feature,
        and a provider that raised its own exception would be issuing one.
        """
        ...


def canonical_preimage(contract: ClarificationContract, *, key_id: str, algorithm: str) -> str:
    """The exact bytes a seal is computed over. Deterministic, one spelling.

    Built from the contract's own JSON-mode dump, so a ``datetime`` renders the
    way the contract renders it and a nested ``CandidateRef`` renders the way the
    contract renders it. A hand-written serialiser here would be a second
    representation of the contract, free to drift from the first.

    ``key_id`` and ``algorithm`` are added under reserved keys the contract does
    not declare, so a contract field can never collide with them. Both are covered
    deliberately: a contract resealed under a different key, or under a downgraded
    algorithm, must not verify against the original.
    """
    payload = contract.model_dump(mode="json", exclude={"seal"})
    payload["__key_id__"] = key_id
    payload["__algorithm__"] = algorithm
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def issue_seal(
    contract: ClarificationContract,
    *,
    port: SealPort | None,
    key_id: str,
    algorithm: str,
    records: Iterable[ReadinessRecord] | None = None,
) -> Seal:
    """Seal a contract, or refuse. **The gate runs before the port is touched.**

    ``port`` has no default and may be ``None`` — the absence is a refusal, never
    a bypass. A defaulted port would be a sealing provider this package chose,
    which is the decision `D-21` exists to make.

    ``records`` is injectable for tests only; no runtime path supplies one.
    """
    require_surface(CapabilitySurface.CLARIFICATION_SEALING, records=records)
    if port is None:
        raise ContractViolation(
            InterpretationReasonCode.CLARIFICATION_UNAVAILABLE,
            "no sealing provider was supplied; a contract is not issued unsealed",
        )
    return port.seal(
        canonical_preimage(contract, key_id=key_id, algorithm=algorithm), key_id=key_id
    )


def verify_seal(
    contract: ClarificationContract,
    *,
    port: SealPort | None,
    records: Iterable[ReadinessRecord] | None = None,
) -> None:
    """Refuse unless the seal still covers the contract exactly.

    The preimage is rebuilt from the **submitted** contract and from the
    submitted seal's own ``key_id`` and ``algorithm``. That is what makes a
    downgrade detectable: a caller who reseals under a weaker algorithm changes
    the preimage, and the original seal no longer matches it.

    Verification is gated too. A build where `D-21` is unavailable cannot verify
    a contract issued when it was — which is correct, because it cannot establish
    that the key is still the governed one.
    """
    require_surface(CapabilitySurface.CLARIFICATION_SEALING, records=records)
    if port is None:
        raise ContractViolation(
            InterpretationReasonCode.CLARIFICATION_UNAVAILABLE,
            "no sealing provider was supplied; a contract is not honoured unverified",
        )

    preimage = canonical_preimage(
        contract, key_id=contract.seal.key_id, algorithm=contract.seal.algorithm
    )
    if not port.verify(preimage, contract.seal):
        # Never repaired, never partially honoured, never downgraded to a fresh
        # question. A contract that failed its seal is one whose fields no longer
        # all mean what the issuer meant, and there is no subset worth keeping.
        raise ContractViolation(
            InterpretationReasonCode.CLARIFICATION_TAMPERED,
            "the clarification contract does not match its seal",
        )
