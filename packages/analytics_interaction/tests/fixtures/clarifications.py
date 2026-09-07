"""Phase 11 test support: **fixture-only** readiness, key material and policy.

## The key here is synthetic, and defined once under ``fixtures/seal/``

`D-21` is undeclared, so no clarification contract can be sealed today. A sealing
suite therefore has nothing to exercise unless it supplies its own key — and the
whole risk of doing that is a reader, or a future edit, mistaking it for
provisioned key material.

The material itself lives in ``tests/fixtures/seal/`` — `T147`'s home for it —
and is re-exported here rather than redeclared. Two definitions of one synthetic
key is exactly what the containment scan exists to catch: the copy that drifts is
the copy nobody is scanning.

So :data:`FIXTURE_KEY` is:

* **explicitly injected**, never defaulted, never read from an environment
  variable, never derived from a hostname, a build hash, a config value or any
  identity field;
* **marked at every level** — the name, the value, the ``key_id`` and the
  ``algorithm`` all say ``fixture``, and `T113`'s static scan asserts the marker
  appears in no `src/` module. One marker string covers both this module and
  ``fixtures/seal/``, so no half of the key material goes unscanned;
* **not a cryptographic choice.** ``FixtureSealPort`` computes a plain SHA-256
  over ``key || preimage``. That is a stand-in that makes tampering detectable in
  a test, and explicitly **not** a proposal for what `D-21` should govern. The
  production port declares no algorithm precisely because that decision is not
  this feature's to make.

Nothing here is readiness evidence. The synthetic records below carry a
``fixture`` evidence ref and an ``owner_role`` that says so, and they are passed
through the ``records`` parameter that exists for tests — no runtime path
supplies one.

## The synthetic policy

`D-19` ships empty. ``fixture_policy`` declares a round bound, an expiry and an
ambiguity threshold **as fixture values**, so the round-accounting and expiry
tests have something to run against. They are not proposals either: the real
values are `D-19` content and this feature invents none.

TEST-ONLY. Never production data, never evidence for any external record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from analytics_interaction.compliance.gates import InteractionCapability
from analytics_interaction.compliance.readiness import Capability, ReadinessRecord
from analytics_interaction.contracts._base import LocalizedRef
from analytics_interaction.contracts.clarification import CandidateRef, ClarificationContract, Seal
from analytics_interaction.contracts.intent import SlotKind
from analytics_interaction.governance.schemas import (
    ContentApproval,
    DisclosureRule,
    InterpretationPolicy,
    RedactionRule,
)

from .seal import FIXTURE_ALGORITHM, FIXTURE_KEY, FIXTURE_KEY_ID, FIXTURE_MARKER
from .seal import SyntheticSeal as FixtureSealPort

__all__ = [
    "FIXTURE_ALGORITHM",
    "FIXTURE_KEY",
    "FIXTURE_KEY_ID",
    "FIXTURE_MARKER",
    "CountingSealPort",
    "FixtureSealPort",
    "candidate",
    "fixture_policy",
    "issued_contract",
    "ready_records",
    "unready_records",
]

ISSUED_AT = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
EXPIRY = timedelta(minutes=15)


@dataclass
class CountingSealPort:
    """Records every call, and answers nothing.

    The zero-call gates are **counts**, not inspections: a scan proves a module
    does not import the port, and proves nothing about whether some other path
    reached it at runtime. Fail-loud on use rather than on construction, so a
    test asserting zero has something that *would* have been counted.
    """

    seal_calls: list[str] = field(default_factory=list[str])
    verify_calls: list[str] = field(default_factory=list[str])

    def seal(self, preimage: str, *, key_id: str) -> Seal:
        self.seal_calls.append(key_id)
        raise AssertionError("the counting seal port produces no seal")

    def verify(self, preimage: str, seal: Seal) -> bool:
        self.verify_calls.append(seal.key_id)
        raise AssertionError("the counting seal port verifies nothing")

    @property
    def calls(self) -> int:
        return len(self.seal_calls) + len(self.verify_calls)


def _record(
    *, declared: bool, evidenced: bool, capabilities: tuple[InteractionCapability, ...]
) -> ReadinessRecord:
    return ReadinessRecord(
        feature="003-nl-analytics-interaction",
        source=FIXTURE_MARKER,
        capabilities={
            capability.value: Capability(
                identifier=capability.value,
                declared=declared,
                evidence_ref=f"{FIXTURE_MARKER}-evidence" if evidenced else None,
                owner_role="fixture",
            )
            for capability in capabilities
        },
    )


def ready_records(*capabilities: InteractionCapability) -> tuple[ReadinessRecord, ...]:
    """Synthetic records marking ``capabilities`` READY. **Fixture-only.**

    Passed through the ``records`` parameter that exists for tests. The shipped
    files are never edited, and this never becomes evidence for an external
    record — the source and the evidence ref both say ``fixture``.
    """
    return (_record(declared=True, evidenced=True, capabilities=capabilities),)


def unready_records(
    *capabilities: InteractionCapability, declared: bool = False
) -> tuple[ReadinessRecord, ...]:
    """Synthetic records in a **non**-ready state.

    ``declared=True`` produces ``DECLARED_WITHOUT_EVIDENCE`` — a flag with nothing
    behind it. It must unlock exactly as much as ``UNDECLARED`` does, which is
    nothing, and having both shapes here is what lets that be asserted.
    """
    return (_record(declared=declared, evidenced=False, capabilities=capabilities),)


def fixture_policy(
    *,
    round_bound: int = 2,
    expiry_seconds: int = 900,
    ambiguity_threshold: int = 2,
    version: str = f"{FIXTURE_MARKER}-pol-1",
    effective_from: date = date(2026, 1, 1),
    effective_to: date | None = None,
) -> tuple[InterpretationPolicy, ...]:
    """One synthetic `D-19` instance. **Fixture values, not proposals.**

    Returns a tuple because ``resolve_effective`` resolves *exactly one effective*
    instance from a collection — so a test can pass zero (the shipped state), one
    (usable) or two overlapping (ambiguous, refuses) without a helper for each.
    """
    return (
        InterpretationPolicy(
            version=version,
            effective_from=effective_from,
            effective_to=effective_to,
            approval=ContentApproval(
                approver_role="fixture",
                evidence_ref=FIXTURE_MARKER,
                approved_on=date(2026, 1, 1),
            ),
            ambiguity_threshold=ambiguity_threshold,
            clarification_round_bound=round_bound,
            clarification_expiry_seconds=expiry_seconds,
            question_length_bound=512,
            redaction_rule=RedactionRule(
                rule_id=f"{FIXTURE_MARKER}-redaction",
                patterns=(f"{FIXTURE_MARKER}-pattern",),
                on_match="refuse",
            ),
            cross_question_disclosure=DisclosureRule(
                rule_id=f"{FIXTURE_MARKER}-disclosure",
                window_questions=5,
                on_reconstruction_risk="refuse",
            ),
        ),
    )


def candidate(identifier: str, slot: SlotKind = SlotKind.METRIC) -> CandidateRef:
    """One governed candidate, distinguished by a governed pointer.

    ``distinguishing`` is a ``LocalizedRef`` rather than a sentence — the contract
    requires it, because a built string would put unreviewed text, possibly
    derived from the question, into a sealed artifact the caller transports.
    """
    return CandidateRef(
        identifier=identifier,
        slot=slot,
        distinguishing=LocalizedRef(
            code=f"candidate.{identifier}", language="pt-BR", content_version="v1"
        ),
    )


def issued_contract(
    *,
    port: FixtureSealPort | None = None,
    fingerprint: str,
    candidates: tuple[CandidateRef, ...] = (),
    rounds_consumed: int = 0,
    round_bound: int = 2,
    issued_at: datetime = ISSUED_AT,
    expiry: timedelta = EXPIRY,
    catalog_release: str = "r-1",
    policy_version: str = "pol-1",
    vocabulary_version: str = "voc-1",
    correlation_id: str = "corr-1",
    interpretation_id: str = "interp-1",
    unresolved: SlotKind = SlotKind.METRIC,
    nonce: str = "nonce-1",
) -> ClarificationContract:
    """A sealed contract, issued through the **real** issuance path.

    Not hand-built: it goes through ``issue_clarification``, so the `D-21` gate,
    the contract's own validators and the seal all run. A hand-built contract
    would let a resumption test pass against a shape issuance could never
    produce.
    """
    from analytics_interaction.clarification.issue import issue_clarification

    return issue_clarification(
        correlation_id=correlation_id,
        interpretation_id=interpretation_id,
        auth_fingerprint=fingerprint,
        unresolved=unresolved,
        candidates=candidates or (candidate("installs"), candidate("sessions")),
        rounds_consumed=rounds_consumed,
        round_bound=round_bound,
        issued_at=issued_at,
        expiry=expiry,
        nonce=nonce,
        catalog_release=catalog_release,
        policy_version=policy_version,
        vocabulary_version=vocabulary_version,
        port=port or FixtureSealPort(key=FIXTURE_KEY),
        key_id=FIXTURE_KEY_ID,
        algorithm=FIXTURE_ALGORITHM,
        records=ready_records(InteractionCapability.D_21),
    )
