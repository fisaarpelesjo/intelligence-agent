"""Additive readiness aggregation — T026 (FR-096, FR-097; SC-053, SC-056).

Overall readiness is the **conjunction of every record**. A capability is ready only
when its own record declares it ready *and* names evidence, and an operation is
permitted only when every contributing record permits it.

The load-bearing rule is what happens when a record is **missing**: it reads *not
ready*, never *no constraint*. That is what makes aggregation additive — a record can
only ever narrow what is permitted, so a new feature cannot widen an existing one's
readiness by arriving. `002` established the pattern, `003` followed it, and this
follows both. The reader is **re-implemented rather than imported** because the import
allowlist (`contracts/interaction-port.md` §3) enumerates nineteen upstream names — seven
originally, twelve added by ADR 0026 — and ``analytics_interaction.compliance`` is not among
any of them.

**Four records, named rather than globbed.** A file appearing in the directory would
otherwise silently join the conjunction, and a record nobody reviewed must not be able
to change what is permitted.

**Malformed data raises rather than resolving.** An unreadable record, an unknown field
or a wrong type is a defect, and a defect must not look like a governed "not ready".

**Nothing is cached.** Every call re-reads, so a withdrawal of readiness takes effect
immediately rather than at the next process restart.

This module **reads**. It never writes, never mutates a record, and offers no path —
flag, environment variable, argument or override — by which a capability could be
marked declared, evidenced or ready.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

import yaml

from ..contracts.descriptor import ChannelDescriptor, ChannelId, CredentialRecord

__all__ = [
    "CHANNEL_CAPABILITIES",
    "IDEMPOTENCY_SCOPE_STATEMENT",
    "OWN_RECORD",
    "READINESS_RECORDS",
    "Capability",
    "CapabilityState",
    "MultiInstanceRefused",
    "ReadinessMalformed",
    "UnknownCapability",
    "aggregate_ready",
    "capabilities_in_own_record",
    "capability_state",
    "channel_enabled",
    "descriptor_with_derived_enablement",
    "load_all_records",
    "readiness_root",
    "require_single_instance",
]

#: The four records this feature aggregates, in dependency order.
READINESS_RECORDS: tuple[str, ...] = (
    "external-readiness.yaml",
    "analytics-query-external-readiness.yaml",
    "nl-analytics-external-readiness.yaml",
    "multichannel-external-readiness.yaml",
)

#: This feature's own capabilities, **named rather than derived, and that is deliberate.**
#:
#: Deriving them from the record would make this a second reading of one file, and a record
#: that LOST an entry would silently shrink both sides. Named, the tuple is an independent
#: statement of what must be there, and `test_the_channel_locks_are_exactly_these` compares
#: the two — which is the only arrangement where either direction of drift is visible.
#:
#: **`d_34` was missing from here for one day, and that is the defect this comment now
#: records.** It was created on 2026-08-28 under `OD-17`, in this feature's own file, and
#: never listed — so it governed nothing while reading as governed, it fell into the
#: `inherited` bucket beside `001`'s capabilities, and the CLI reported eleven of twelve
#: while its docstring said *every*. Three faces, one root: a hand-written enumeration that
#: nothing forced to stay complete.
#:
#: The comparison is an EQUALITY now. It was a subset, which is why nothing failed.
CHANNEL_CAPABILITIES: tuple[str, ...] = (
    "d_22",
    "d_23",
    "d_24",
    "d_25",
    "d_26",
    "d_27",
    "d_28",
    "d_29",
    "d_30",
    "d_31",
    "d_32",
    "d_34",
)

#: The file this feature owns. Everything in the other three belongs to `001`, `002` and
#: `003`, and `inherited` means **from another file** — not *absent from the tuple above*,
#: which is what let `d_34` read as somebody else's record.
OWN_RECORD: str = "multichannel-external-readiness.yaml"

#: Which credential record gates which channel.
_CHANNEL_CREDENTIAL: Mapping[ChannelId, CredentialRecord] = {
    ChannelId.WHATSAPP: CredentialRecord.D_22_WHATSAPP,
    ChannelId.SLACK: CredentialRecord.D_23_SLACK,
    ChannelId.TELEGRAM: CredentialRecord.D_24_TELEGRAM,
    ChannelId.GENERIC_WEBHOOK: CredentialRecord.D_25_GENERIC,
}

_ALLOWED_DOCUMENT_KEYS = frozenset({"capabilities", "schema_version", "kind", "feature"})

_ALLOWED_ENTRY_KEYS = frozenset(
    {
        "id",
        "capability",
        "declared",
        "evidence_ref",
        "name",
        "note",
        "owner_role",
        "declared_by_role",
        "required_evidence",
        "capability_unavailable",
        "fail_closed",
        "carry_forward",
    }
)


class ReadinessMalformed(ValueError):  # noqa: N818 - the record is malformed, not the reader
    """A readiness record cannot be read as written."""


class UnknownCapability(KeyError):  # noqa: N818 - named for the governed concept
    """A capability identifier no record declares.

    Refused rather than reported unavailable: "unavailable" is a statement about a
    governed capability, and a name nobody governs has no state to report.
    """


class CapabilityState(StrEnum):
    """The four distinguishable states. Only ``READY`` unlocks."""

    UNDECLARED = "UNDECLARED"
    DECLARED_WITHOUT_EVIDENCE = "DECLARED_WITHOUT_EVIDENCE"
    EVIDENCE_WITHOUT_DECLARATION = "EVIDENCE_WITHOUT_DECLARATION"
    READY = "READY"


class Capability:
    """One external capability, as one record states it."""

    __slots__ = ("declared", "declared_by_role", "evidence_ref", "identifier", "owner_role")

    def __init__(
        self,
        identifier: str,
        declared: bool,
        evidence_ref: str | None,
        owner_role: str,
        declared_by_role: str | None = None,
    ) -> None:
        self.identifier = identifier
        self.declared = declared
        self.evidence_ref = evidence_ref
        self.owner_role = owner_role
        self.declared_by_role = declared_by_role

    @property
    def state(self) -> CapabilityState:
        evidenced = bool(self.evidence_ref and self.evidence_ref.strip())
        if self.declared and evidenced:
            return CapabilityState.READY
        if self.declared:
            return CapabilityState.DECLARED_WITHOUT_EVIDENCE
        if evidenced:
            return CapabilityState.EVIDENCE_WITHOUT_DECLARATION
        return CapabilityState.UNDECLARED

    @property
    def ready(self) -> bool:
        """Declared **and** evidenced. A declaration alone is not readiness."""
        return self.state is CapabilityState.READY

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Capability({self.identifier!r}, {self.state.value})"


def readiness_root() -> Path:
    """``docs/readiness/`` at the repository root, located by walking up.

    Located rather than configured. A settable path would let a deployment point
    readiness at a file of its own making.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "docs" / "readiness"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(f"docs/readiness/ not found above {here}")


def _entry_identity(entry: Mapping[str, Any], source: str) -> str:
    """``id`` on the newer records, ``capability`` on `001`'s.

    `001`'s record predates the schema header and names the field differently. Read
    rather than normalised: normalising would mean editing an approved artifact of a
    merged feature, which this feature may not do.
    """
    for key in ("id", "capability"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value
    raise ReadinessMalformed(f"{source}: a capability entry declares no identifier")


def _read_record(path: Path) -> dict[str, Capability]:
    if not path.is_file():
        raise ReadinessMalformed(f"{path.name} does not exist; a missing record is not permission")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, Mapping):
        raise ReadinessMalformed(f"{path.name} is not a mapping")
    document = cast(Mapping[str, Any], loaded)
    unknown = sorted(set(document) - _ALLOWED_DOCUMENT_KEYS)
    if unknown:
        raise ReadinessMalformed(f"{path.name} declares unknown keys: {', '.join(unknown)}")
    entries = document.get("capabilities")
    if not isinstance(entries, Iterable) or isinstance(entries, str | bytes | Mapping):
        raise ReadinessMalformed(f"{path.name} declares a non-list `capabilities`")

    capabilities: dict[str, Capability] = {}
    for raw in cast(Iterable[Any], entries):
        if not isinstance(raw, Mapping):
            raise ReadinessMalformed(f"{path.name}: a capability entry is not a mapping")
        entry = cast(Mapping[str, Any], raw)
        extra = sorted(set(entry) - _ALLOWED_ENTRY_KEYS)
        if extra:
            raise ReadinessMalformed(f"{path.name} entry declares unknown keys: {', '.join(extra)}")
        identifier = _entry_identity(entry, path.name)
        declared = entry.get("declared", False)
        if not isinstance(declared, bool):
            raise ReadinessMalformed(f"{path.name}: {identifier} `declared` is not a boolean")
        evidence = entry.get("evidence_ref")
        if evidence is not None and not isinstance(evidence, str):
            raise ReadinessMalformed(f"{path.name}: {identifier} `evidence_ref` is not a string")
        signer = entry.get("declared_by_role")
        if signer is not None and not isinstance(signer, str):
            raise ReadinessMalformed(
                f"{path.name}: {identifier} `declared_by_role` is not a string"
            )
        owner = entry.get("owner_role", "")
        capabilities[identifier] = Capability(
            identifier,
            declared,
            evidence,
            owner if isinstance(owner, str) else "",
            declared_by_role=signer,
        )
    return capabilities


def load_all_records() -> dict[str, Capability]:
    """Every capability across the four records, keyed by identifier.

    A duplicate identifier across two records is malformed rather than merged: two
    features declaring the same capability would make readiness depend on read order.
    """
    root = readiness_root()
    merged: dict[str, Capability] = {}
    for name in READINESS_RECORDS:
        for identifier, capability in _read_record(root / name).items():
            if identifier in merged:
                raise ReadinessMalformed(f"{identifier} is declared by more than one record")
            merged[identifier] = capability
    return merged


def capabilities_in_own_record() -> dict[str, Capability]:
    """The capabilities **this feature's own file** declares, keyed by identifier.

    `load_all_records` merges the four files and the provenance is gone by the time it
    returns — which is why *inherited* came to mean *absent from `CHANNEL_CAPABILITIES`*,
    and why `d_34` read as somebody else's record the day it was created.

    **Provenance is a fact about the file, so it is read from the file.**
    """
    return _read_record(readiness_root() / OWN_RECORD)


def capability_state(identifier: str) -> CapabilityState:
    """The state of one capability, across every record."""
    capabilities = load_all_records()
    try:
        return capabilities[identifier].state
    except KeyError as exc:
        raise UnknownCapability(identifier) from exc


def aggregate_ready(identifiers: Iterable[str]) -> bool:
    """Are **all** of ``identifiers`` ready?

    Conjunction, and an unknown identifier raises rather than reading as ready.
    """
    capabilities = load_all_records()
    for identifier in identifiers:
        try:
            capability = capabilities[identifier]
        except KeyError as exc:
            raise UnknownCapability(identifier) from exc
        if not capability.ready:
            return False
    return True


def channel_enabled(channel: ChannelId) -> bool:
    """**The credential half**, and it is no longer the whole answer.

    Enabled only when its credential record is READY. Derived here rather than
    configured anywhere, which is what makes `FR-097` structural: no file, flag or
    environment variable can enable a channel whose record is undeclared.

    ## Why this is not the question a caller should ask any more

    Until 2026-08-28 this WAS the switch, and both directions read it. That made two
    different questions share one answer: *may a message arrive from this channel* and
    *may a message be sent to it*. They are not the same question and they are not
    governed by the same decision.

    **The owner's decision of 2026-08-18** blocks Telegram and WhatsApp because their
    schemes sign no timestamp, so a captured request can be **presented again** and
    conversion cannot tell — a property of what ARRIVES. **His decision of 2026-08-28**
    (`OD-20-A`) splits the switch rather than weakening that one: the inbound block stands
    **in full**, and what opens is sending.

    **Callers ask :func:`may_receive_from` or :func:`may_send_to`**, and on 2026-08-28 this
    sentence was false for one commit: the split existed here and NOWHERE that consumes it,
    while this docstring already described the world it was supposed to create. The reviewer
    measured eight call sites and zero of either half.

    `test_the_split_key_is_asked_by_its_callers` now walks the tree and fails if anything
    outside this module calls this function, so the sentence cannot go false again quietly.

    This stays because both halves are built on it, and because a credential nobody declared
    authorizes neither direction.
    """
    return aggregate_ready([_CHANNEL_CREDENTIAL[channel].value])


def may_receive_from(channel: ChannelId) -> bool:
    """May a message **arrive** from ``channel``?

    Two conditions, both required: the credential record is READY, **and** the channel's
    scheme evaluates an instant. The second is the owner's decision of 2026-08-18, and it
    is **derived from the scheme itself** — never from a list written here, so a scheme
    that gained a signed timestamp would widen this by its own evidence and a scheme that
    lost one would narrow it.

    **Absence of a governed cross-process duplicate-suppression store is why the second
    condition exists.** Duplicate suppression is process-local; on a scheme that binds no
    instant, a replayed request is indistinguishable from a new one.
    """
    return channel_enabled(channel) and _scheme_evaluates_an_instant(channel)


def may_send_to(channel: ChannelId) -> bool:
    """May a message be **sent** to ``channel``?

    The credential record, and nothing else. A replayed **inbound** request is not a risk
    that outbound delivery carries: nothing arrives, so nothing can be presented twice.

    **This is the half `OD-20-A` opened**, and it opened it by splitting the question
    rather than by excusing the inbound rule.
    """
    return channel_enabled(channel)


def _scheme_evaluates_an_instant(channel: ChannelId) -> bool:
    """Does this channel's verification scheme bind a signed timestamp?

    Read from the **scheme registry itself**, through the canonical channel-to-scheme map
    that `inbound.verify` already owns. Not from a descriptor: a descriptor is something a
    caller supplies, and the question *what does this channel's scheme guarantee* is not a
    caller's to answer.

    Imported inside the function because `inbound.verify` imports contracts this module
    also serves; asking at call time keeps the dependency one-directional.

    **A scheme that cannot be resolved answers `False`.** Not measuring is never passing,
    and an unresolvable scheme is exactly the case where a replay could not be detected.
    """
    from ..inbound.verify import EXPECTED_SCHEME, SCHEMES

    named = EXPECTED_SCHEME.get(channel)
    if named is None:  # pragma: no cover - every channel is mapped
        return False
    scheme = SCHEMES.get(named)
    if scheme is None:  # pragma: no cover - every named scheme is implemented
        return False
    return bool(scheme.provides_signed_timestamp)


def descriptor_with_derived_enablement(descriptor: ChannelDescriptor) -> ChannelDescriptor:
    """``descriptor`` with ``enabled`` recomputed from the readiness records.

    Returns a new frozen instance; nothing is mutated. The credential record named by
    the descriptor must be the one this module maps to that channel — a mismatch is a
    malformed descriptor, not a channel that is enabled by a different lock.

    ## Which half `enabled` means, answered rather than left ambiguous

    **It means SENDING.** `OD-20-A` split the key on 2026-08-28 and this field kept a name
    from before the split, so the question *which of the two does it answer* had no stated
    answer for one commit — and a field whose meaning nobody wrote down is a field two
    readers understand differently.

    The answer is sending because that is what this descriptor is used for: the delivery
    adapters read it. **Nothing here answers whether the channel may RECEIVE**, and a caller
    that needs to know asks :func:`may_receive_from`, which is the only thing that carries
    the 2026-08-18 rule.
    """
    expected = _CHANNEL_CREDENTIAL[descriptor.channel]
    if descriptor.credential_record is not expected:
        raise ReadinessMalformed(
            f"{descriptor.channel.value} must be gated by {expected.value}, "
            f"not {descriptor.credential_record.value}"
        )
    return descriptor.model_copy(update={"enabled": may_send_to(descriptor.channel)})


# --------------------------------------------------------------------------- #
# T083 — the multi-process refusal (ADR 0021; FR-067; SC-029, SC-064)          #
# --------------------------------------------------------------------------- #

#: The one sentence every report, every CLI output and every docstring about duplicate suppression
#: must be able to point at. Written once so the claim cannot drift between surfaces (`SC-064`).
IDEMPOTENCY_SCOPE_STATEMENT = (
    "Duplicate suppression is process-local: one process, one instance, one governed window. "
    "Nothing is replicated, shared, synchronised or coordinated, so no cross-process deduplication "
    "is claimed."
)


class MultiInstanceRefused(RuntimeError):  # noqa: N818 - a governed refusal, not an error
    """A multi-instance configuration was declared, and no governed shared store exists.

    Refusing is the honest response, and it is worth stating why rather than only doing it. With
    several instances and a process-local window, a redelivery that lands on a different instance is
    not recognised, so the sender receives a governed answer **twice**. Degrading silently would
    give an operator the words "duplicate suppression" and none of the behaviour, and the gap would
    surface as a doubled answer rather than as a refusal.

    `NG-4` records that this feature does not build the governed shared store that would make
    cross-process suppression real, so there is nothing to fall back to.
    """


def require_single_instance(declared_instances: int) -> int:
    """``declared_instances`` when it is exactly one, or refuse.

    The count is **passed in**, never discovered. Reading it from an environment variable or a
    configuration file would be an ambient read on the request path, and the leak and env scans
    (`T064`, `T101`) forbid one — so the deployment declares its own shape and this function judges
    it.

    Zero refuses too. A declared count of zero is a malformed declaration, and treating it as "not
    running yet" would let a caller pass zero to bypass the check entirely.
    """
    if declared_instances != 1:
        raise MultiInstanceRefused(
            f"{declared_instances} instances were declared and duplicate suppression is "
            f"process-local. {IDEMPOTENCY_SCOPE_STATEMENT}"
        )
    return declared_instances
