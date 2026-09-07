"""Additive readiness aggregation — T061 (FR-057; SC-032).

Overall readiness is the **conjunction of every record**. A capability is ready
only when its own record declares it ready *and* names evidence, and an
operation is permitted only when every contributing record permits it.

The load-bearing rule is what happens when a record is **missing**: it reads
*not ready*, never *no constraint*. That is what makes aggregation additive — a
record can only ever narrow what is permitted, so a new feature cannot widen an
existing one's readiness by arriving. `002` established the pattern and this
follows it; the reader is re-implemented rather than imported because ADR 0010
places `analytics_query.compliance` off-limits to this feature.

**Five states, and the distinctions matter.**

| State | Meaning |
|---|---|
| ``UNDECLARED`` | Nobody has claimed the capability exists. The shipped state |
| ``DECLARED_WITHOUT_EVIDENCE`` | A flag was flipped and nothing was delivered. **Never unlocks** |
| ``EVIDENCE_WITHOUT_DECLARATION`` | An evidence reference with no
  declaration behind it. **Never unlocks** |
| ``READY`` | Declared **and** evidenced |
| *(malformed / contradictory)* | Raises. See below |

Only ``READY`` unlocks anything. The two invalid middles are separate states
rather than one, because they are different governance failures: one is a
premature flag, the other is a dangling reference, and collapsing them would
tell a steward the wrong thing about which they have.

**Malformed data raises rather than resolving.** An unreadable record, an
unknown field, an unknown capability id, a wrong type — each is a defect, and a
defect must not look like a governed "not ready". Silently reading a broken file
as unavailable would be safe today and dangerous the moment somebody fixes the
file badly.

**Nothing is cached.** Every call re-reads. A cached aggregate could outlive a
readiness-record change, which is the one kind of staleness that turns a
withdrawal of readiness into a capability that is still unlocked.

This module **reads**. It never writes, never mutates a record, and offers no
path — flag, environment variable, argument or override — by which a capability
could be marked declared, evidenced or ready.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum
from pathlib import Path
from typing import cast

import yaml

__all__ = [
    "READINESS_RECORDS",
    "Capability",
    "CapabilityState",
    "ReadinessMalformed",
    "ReadinessRecord",
    "UnknownCapability",
    "aggregate_ready",
    "capability_state",
    "load_all_records",
    "load_record",
    "readiness_root",
]

#: The three records this feature aggregates. Named rather than globbed: a file
#: that appeared in the directory would otherwise silently join the conjunction,
#: and a record nobody reviewed must not be able to change what is permitted.
READINESS_RECORDS: tuple[str, ...] = (
    "external-readiness.yaml",
    "analytics-query-external-readiness.yaml",
    "nl-analytics-external-readiness.yaml",
)

#: Top-level keys a readiness document may carry. `001`'s record predates the
#: schema header and carries `capabilities` alone; `002` and `003` carry the
#: header too. Anything else refuses.
_ALLOWED_DOCUMENT_KEYS = frozenset({"capabilities", "schema_version", "kind", "feature"})

#: Keys a capability entry may carry. The identity and status fields are the ones
#: this reader acts on; the rest are governance prose the record keeps for a
#: human reader. An unlisted key refuses, because a typo'd `evidence_reference`
#: would otherwise read as an undeclared capability rather than as a mistake.
_ALLOWED_ENTRY_KEYS = frozenset(
    {
        "id",
        "capability",
        "declared",
        # OD-99 (2026-09-02): o leitor do 001 EXIGE declared_by_role em entrada declarada
        # (readiness e evidencia assinada por papel permitido, nunca flag); o leitor do 004
        # ja conhecia a chave; este passa a conhece-la tambem — semantica identica.
        "declared_by_role",
        "evidence_ref",
        "name",
        "note",
        "owner_role",
        "required_evidence",
        "capability_unavailable",
        "fail_closed",
        "carry_forward",
    }
)


class ReadinessMalformed(ValueError):  # noqa: N818 - the record is malformed, not the reader
    """A readiness record cannot be read as written.

    Distinct from "not ready": this is a defect in the record, and treating it as
    unavailability would hide it behind the very behaviour it might have broken.
    """


class UnknownCapability(KeyError):  # noqa: N818 - named for the governed concept
    """A capability identifier no record declares.

    Refused rather than reported unavailable. "Unavailable" is a statement about
    a governed capability; a name nobody governs has no state to report, and
    answering "not ready" would invent one.
    """


class CapabilityState(StrEnum):
    """The five distinguishable states. Only ``READY`` unlocks."""

    UNDECLARED = "UNDECLARED"
    DECLARED_WITHOUT_EVIDENCE = "DECLARED_WITHOUT_EVIDENCE"
    EVIDENCE_WITHOUT_DECLARATION = "EVIDENCE_WITHOUT_DECLARATION"
    READY = "READY"


class Capability:
    """One external capability, as one record states it."""

    __slots__ = ("declared", "evidence_ref", "identifier", "owner_role")

    def __init__(
        self,
        identifier: str,
        declared: bool,
        evidence_ref: str | None,
        owner_role: str,
    ) -> None:
        self.identifier = identifier
        self.declared = declared
        self.evidence_ref = evidence_ref
        self.owner_role = owner_role

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


class ReadinessRecord:
    """One feature's readiness declarations."""

    __slots__ = ("capabilities", "feature", "source")

    def __init__(self, feature: str, source: str, capabilities: Mapping[str, Capability]) -> None:
        self.feature = feature
        self.source = source
        self.capabilities = dict(capabilities)

    def ready_capabilities(self) -> frozenset[str]:
        return frozenset(name for name, cap in self.capabilities.items() if cap.ready)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ReadinessRecord({self.feature!r}, {len(self.capabilities)} capabilities)"


def readiness_root() -> Path:
    """``docs/readiness/`` at the repository root, located by walking up.

    Located rather than configured. A settable path would be a runtime switch
    over governance evidence, which is the same defect as a settable governed
    content root — and a far worse one, because it would let a deployment point
    readiness at a file of its own making.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "docs" / "readiness"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("docs/readiness/ not found above " + str(here))


def _entry_identity(entry: Mapping[str, object], source: str) -> str:
    """``id`` on the newer records, ``capability`` on `001`'s.

    Both spellings are accepted because both are approved artifacts owned by
    other features. Renaming either to match would be editing a merged record.
    """
    identifier = entry.get("id", entry.get("capability"))
    if not isinstance(identifier, str) or not identifier.strip():
        raise ReadinessMalformed(f"{source}: each capability needs a non-empty `id`")
    return identifier


def load_record(path: Path) -> ReadinessRecord:
    """Parse one readiness record, or raise.

    Every failure mode here is a **defect**, not a state: a document that is not
    a mapping, an unknown key, a missing identifier, a non-boolean ``declared``,
    an ``evidence_ref`` that is not a string, a duplicate identifier. Each raises
    ``ReadinessMalformed`` so it surfaces as what it is.

    Note what is *not* rejected: ``declared: true`` with no evidence parses
    cleanly and reads ``DECLARED_WITHOUT_EVIDENCE``. It is a governance failure
    rather than a syntax one, and a steward needs to be able to see it stated
    rather than have the file refuse to load.

    A record carrying **no capabilities** *is* rejected. It was not, and the gap was
    quiet: an unparseable-but-loadable file contributed nothing to the aggregate and
    looked identical to a correct file whose capabilities were all unavailable. Three
    records, one silently empty, aggregate still ``NONE`` — and the missing constraint
    would never surface.
    """
    source = path.name
    if not path.is_file():
        # Missing reads NOT READY at the aggregate, but a record this feature
        # names and cannot find is a defect: the conjunction it was supposed to
        # contribute to would silently lose a constraint.
        raise ReadinessMalformed(f"{source}: readiness record is missing")

    try:
        raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as unparseable:
        # ``yaml.YAMLError`` is not a ``ValueError``, so it escaped this function's
        # declared failure mode entirely: a caller catching ``ReadinessMalformed`` --
        # which is every caller -- would not have caught an unparseable record. It fails
        # closed either way, and closed with the wrong exception is closed by accident.
        #
        # The parser's own message is not carried. It quotes the offending line, and a
        # readiness record's contents are governance data rather than something to echo
        # into an arbitrary caller's error path.
        raise ReadinessMalformed(f"{source}: the readiness record is not well-formed") from (
            unparseable
        )

    if not isinstance(raw, dict):
        raise ReadinessMalformed(f"{source}: expected a mapping at the document root")
    document = cast("dict[str, object]", raw)

    unknown = sorted(set(document) - _ALLOWED_DOCUMENT_KEYS)
    if unknown:
        raise ReadinessMalformed(f"{source}: unknown top-level keys: {unknown}")

    feature = document.get("feature", source)
    if not isinstance(feature, str) or not feature:
        raise ReadinessMalformed(f"{source}: `feature` must be a non-empty string")

    entries: object = document.get("capabilities", [])
    if not isinstance(entries, list):
        raise ReadinessMalformed(f"{source}: `capabilities` must be a list")

    capabilities: dict[str, Capability] = {}
    for raw_entry in cast("list[object]", entries):
        if not isinstance(raw_entry, dict):
            raise ReadinessMalformed(f"{source}: each capability must be a mapping")
        entry = cast("dict[str, object]", raw_entry)

        unknown_entry = sorted(set(entry) - _ALLOWED_ENTRY_KEYS)
        if unknown_entry:
            raise ReadinessMalformed(f"{source}: unknown capability keys: {unknown_entry}")

        identifier = _entry_identity(entry, source)
        if identifier in capabilities:
            raise ReadinessMalformed(f"{source}: {identifier} is declared more than once")

        declared = entry.get("declared")
        if not isinstance(declared, bool):
            raise ReadinessMalformed(f"{source}: {identifier} needs a boolean `declared`")

        evidence = entry.get("evidence_ref")
        if evidence is not None and not isinstance(evidence, str):
            raise ReadinessMalformed(
                f"{source}: {identifier} `evidence_ref` must be a string or null"
            )

        owner = entry.get("owner_role", "")
        capabilities[identifier] = Capability(
            identifier, declared, evidence, owner if isinstance(owner, str) else ""
        )

    if not capabilities:
        # An empty record is a defect, not a record saying "nothing is ready". The two
        # are indistinguishable in the aggregate, which is exactly why this must raise:
        # a file that lost its capabilities would keep the aggregate at NONE and take a
        # constraint with it.
        raise ReadinessMalformed(f"{source}: a readiness record declares no capabilities")

    return ReadinessRecord(feature, source, capabilities)


def load_all_records(root: Path | None = None) -> tuple[ReadinessRecord, ...]:
    """Every record this feature aggregates, in declaration order.

    ``root`` is injectable for tests only. It is not a runtime switch: nothing
    reads a flag or an environment setting to reach it, and the production path
    calls ``readiness_root()``.
    """
    directory = root or readiness_root()
    return tuple(load_record(directory / name) for name in READINESS_RECORDS)


def aggregate_ready(records: Iterable[ReadinessRecord]) -> frozenset[str]:
    """Capabilities ready across **every** record that knows them.

    A capability is ready only if the record that owns it says so. A record that
    does not mention it neither grants nor blocks it — but no record granting it
    means it is not ready, which is why an empty input yields an empty set rather
    than "everything".
    """
    materialised = list(records)
    ready: set[str] = set()
    for record in materialised:
        ready |= record.ready_capabilities()
    return frozenset(ready)


def capability_state(
    identifier: str, *, records: Iterable[ReadinessRecord] | None = None
) -> CapabilityState:
    """The state of one capability across the records that declare it.

    **The strictest state wins.** If two records mention the same identifier and
    disagree, the one that does *not* unlock decides — additive aggregation means
    a second opinion can only narrow.

    An identifier no record declares raises ``UnknownCapability`` rather than
    reporting ``UNDECLARED``: an ungoverned name has no state, and answering one
    would invent a governed fact.

    Re-reads on every call. See the module docstring on caching.
    """
    materialised = list(records) if records is not None else list(load_all_records())
    seen = [
        record.capabilities[identifier]
        for record in materialised
        if identifier in record.capabilities
    ]
    if not seen:
        raise UnknownCapability(identifier)

    states = {capability.state for capability in seen}
    for state in (
        CapabilityState.UNDECLARED,
        CapabilityState.DECLARED_WITHOUT_EVIDENCE,
        CapabilityState.EVIDENCE_WITHOUT_DECLARATION,
    ):
        if state in states:
            return state
    return CapabilityState.READY
