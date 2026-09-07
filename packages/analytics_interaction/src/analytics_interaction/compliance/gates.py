"""Fail-closed capability gates — T062-T065.

Four external capabilities, ten governed surfaces, and one rule: **a surface is
reachable only when the capability that governs it is ``READY``.** Everything
else refuses with the code that capability's readiness record already names.

| Capability | Governs | Fail-closed code | Task |
|---|---|---|---|
| `D-18` | relative periods, comparison formulas, claim wording |
  ``INTERPRETATION_VOCABULARY_UNRESOLVABLE`` | T062 |
| `D-19` | ambiguity, governed bound, screening, clarification policy,
  disclosure | ``INTERPRETATION_POLICY_UNRESOLVABLE`` | T063 |
| `D-20` | model narrowing | ``MODEL_SURFACE_UNAVAILABLE`` | T064 |
| `D-21` | clarification sealing | ``CLARIFICATION_UNAVAILABLE`` | T065 |

**Surfaces are named individually, not folded into their capability.** That is
what makes capability isolation checkable: `D-19` being unavailable must block
screening and leave relative periods exactly as blocked as `D-18` already left
them — no more, no less. A single per-capability gate would still be correct and
would prove nothing about the boundary between them.

**The codes come from the record, not from this module.** Each capability's
``fail_closed`` field is authored in
`docs/readiness/nl-analytics-external-readiness.yaml`, and the mapping here
mirrors it. A test asserts the two agree, so a record that changed its
fail-closed behaviour could not leave this module quietly disagreeing.

**No override exists.** No flag, no environment variable, no argument, no
deployment mode and no debugging path can make an unavailable capability
available. The only input is the readiness records, and the only way to change
them is to change them.

These gates **read**. They do not mark, close, satisfy, reinterpret or work
around any record — `FR-057`'s prohibition, which applies with particular force
to `001`'s and `002`'s eleven inherited records.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum
from types import MappingProxyType

from ..contracts._base import ContractViolation
from ..contracts.reason_codes import InterpretationReasonCode
from .readiness import (
    CapabilityState,
    ReadinessRecord,
    capability_state,
)

__all__ = [
    "CAPABILITY_FAIL_CLOSED",
    "SURFACE_CAPABILITY",
    "CapabilitySurface",
    "InteractionCapability",
    "available_capabilities",
    "available_surfaces",
    "capability_for",
    "is_capability_available",
    "is_surface_available",
    "require_capability",
    "require_surface",
]


class InteractionCapability(StrEnum):
    """The four external capabilities this feature adds.

    Values match the identifiers in the readiness record exactly, so a lookup
    cannot drift from the file it reads.
    """

    D_18 = "d_18"
    D_19 = "d_19"
    D_20 = "d_20"
    D_21 = "d_21"


class CapabilitySurface(StrEnum):
    """A governed behaviour that some capability gates.

    Enumerated at this granularity so "each unavailable dependency blocks only
    its own capability surface" is a property with something to assert against.
    """

    # --- D-18 ---------------------------------------------------------------
    RELATIVE_PERIOD = "relative_period"
    COMPARISON_FORMULA = "comparison_formula"
    CLAIM_WORDING = "claim_wording"
    # --- D-19 ---------------------------------------------------------------
    AMBIGUITY_JUDGEMENT = "ambiguity_judgement"
    GOVERNED_LENGTH_BOUND = "governed_length_bound"
    UNTRUSTED_TEXT_SCREENING = "untrusted_text_screening"
    CLARIFICATION_POLICY = "clarification_policy"
    DISCLOSURE_EVALUATION = "disclosure_evaluation"
    # --- D-20 ---------------------------------------------------------------
    MODEL_NARROWING = "model_narrowing"
    # --- D-21 ---------------------------------------------------------------
    CLARIFICATION_SEALING = "clarification_sealing"


_FAIL_CLOSED: dict[InteractionCapability, InterpretationReasonCode] = {
    InteractionCapability.D_18: InterpretationReasonCode.INTERPRETATION_VOCABULARY_UNRESOLVABLE,
    InteractionCapability.D_19: InterpretationReasonCode.INTERPRETATION_POLICY_UNRESOLVABLE,
    InteractionCapability.D_20: InterpretationReasonCode.MODEL_SURFACE_UNAVAILABLE,
    InteractionCapability.D_21: InterpretationReasonCode.CLARIFICATION_UNAVAILABLE,
}

#: Read-only. The governed code each capability refuses with while unavailable.
CAPABILITY_FAIL_CLOSED: Mapping[InteractionCapability, InterpretationReasonCode] = MappingProxyType(
    _FAIL_CLOSED
)


_SURFACES: dict[CapabilitySurface, InteractionCapability] = {
    CapabilitySurface.RELATIVE_PERIOD: InteractionCapability.D_18,
    CapabilitySurface.COMPARISON_FORMULA: InteractionCapability.D_18,
    CapabilitySurface.CLAIM_WORDING: InteractionCapability.D_18,
    CapabilitySurface.AMBIGUITY_JUDGEMENT: InteractionCapability.D_19,
    CapabilitySurface.GOVERNED_LENGTH_BOUND: InteractionCapability.D_19,
    CapabilitySurface.UNTRUSTED_TEXT_SCREENING: InteractionCapability.D_19,
    CapabilitySurface.CLARIFICATION_POLICY: InteractionCapability.D_19,
    CapabilitySurface.DISCLOSURE_EVALUATION: InteractionCapability.D_19,
    CapabilitySurface.MODEL_NARROWING: InteractionCapability.D_20,
    CapabilitySurface.CLARIFICATION_SEALING: InteractionCapability.D_21,
}

#: Read-only. Which capability governs each surface.
SURFACE_CAPABILITY: Mapping[CapabilitySurface, InteractionCapability] = MappingProxyType(_SURFACES)


def capability_for(surface: CapabilitySurface) -> InteractionCapability:
    """The capability that gates ``surface``.

    Raises rather than defaulting: an ungated surface would be one this module
    silently permitted, and a missing entry means the two enums have drifted.
    """
    try:
        return SURFACE_CAPABILITY[surface]
    except KeyError as exc:  # pragma: no cover - guarded by the contract test
        raise ValueError(f"surface {surface!r} is governed by no capability") from exc


def is_capability_available(
    capability: InteractionCapability,
    *,
    records: Iterable[ReadinessRecord] | None = None,
) -> bool:
    """Whether ``capability`` is ``READY`` across every record that declares it.

    ``DECLARED_WITHOUT_EVIDENCE`` and ``EVIDENCE_WITHOUT_DECLARATION`` are both
    false. A flag with nothing behind it and a reference nobody declared are
    different governance failures and identical permissions: neither unlocks.

    ``records`` is injectable for tests only — no runtime path supplies it.
    """
    return capability_state(capability.value, records=records) is CapabilityState.READY


def is_surface_available(
    surface: CapabilitySurface, *, records: Iterable[ReadinessRecord] | None = None
) -> bool:
    return is_capability_available(capability_for(surface), records=records)


def require_capability(
    capability: InteractionCapability,
    *,
    records: Iterable[ReadinessRecord] | None = None,
) -> None:
    """Refuse unless ``capability`` is ready.

    The refusal names no governed value — no threshold, no bound, no formula, no
    key. A principal refused by an unavailable capability learns that it is
    unavailable and nothing about what it would have contained.
    """
    if is_capability_available(capability, records=records):
        return
    raise ContractViolation(
        CAPABILITY_FAIL_CLOSED[capability],
        f"the governed capability {capability.value} is unavailable",
    )


def require_surface(
    surface: CapabilitySurface, *, records: Iterable[ReadinessRecord] | None = None
) -> None:
    """Refuse unless the capability governing ``surface`` is ready.

    This is the call every dependent path makes. Naming the surface rather than
    the capability keeps the dependency direction right: a caller knows what it
    is about to do, not which external record happens to gate it.
    """
    require_capability(capability_for(surface), records=records)


def available_capabilities(
    *, records: Iterable[ReadinessRecord] | None = None
) -> frozenset[InteractionCapability]:
    """The capabilities that are ready. **Empty in the shipped repository.**"""
    return frozenset(
        capability
        for capability in InteractionCapability
        if is_capability_available(capability, records=records)
    )


def available_surfaces(
    *, records: Iterable[ReadinessRecord] | None = None
) -> frozenset[CapabilitySurface]:
    """The surfaces that are reachable. **Empty in the shipped repository.**"""
    ready = available_capabilities(records=records)
    return frozenset(
        surface for surface in CapabilitySurface if SURFACE_CAPABILITY[surface] in ready
    )


# --- T064: the model port is not constructible ---------------------------------


def require_model_participation(*, records: Iterable[ReadinessRecord] | None = None) -> None:
    """Refuse while `D-20` is undeclared. **Attempting construction raises.**

    The port *type* is `T084`'s and does not exist yet; what exists now is the
    gate every future construction path must pass. That ordering is deliberate:
    the guard lands before the thing it guards, so the port cannot arrive
    unguarded.

    While this refuses, interpretation is deterministic-only and an ambiguous
    question clarifies or refuses — it never waits for a model that is not there.
    There is no flag, mode or debugging path that reopens it (`FR-094`,
    `SC-055`).
    """
    require_capability(InteractionCapability.D_20, records=records)


# --- T065: no clarification contract can be issued -----------------------------


def require_clarification_sealing(*, records: Iterable[ReadinessRecord] | None = None) -> None:
    """Refuse while `D-21` is undeclared.

    A caller-transported contract cannot be tamper-evident without key material,
    and an unsealed one would make the rounds consumed, the round bound, the
    expiry, the candidate set and the principal binding caller-editable — which
    is to say absent. So an ambiguous question refuses with
    ``CLARIFICATION_UNAVAILABLE`` instead of clarifying.

    That is a real capability loss, stated rather than engineered around. No key
    is invented, generated, hardcoded, defaulted or silently provisioned here or
    anywhere in this package.
    """
    require_capability(InteractionCapability.D_21, records=records)
