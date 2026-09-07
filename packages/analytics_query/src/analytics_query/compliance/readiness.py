"""Additive readiness aggregation — T030 (FR-061; SC-024).

Overall readiness is the **conjunction** of every record. A capability is ready
only when its own record declares it ready *and* names evidence; an operation is
permitted only when every contributing record permits it.

The load-bearing rule is what happens when a record is **missing**: it reads *not
ready*, never *no constraint*. That is what makes aggregation additive — adding a
record can only ever narrow what is permitted, so a new feature cannot widen an
existing one's readiness by arriving.

A declaration without an ``evidence_ref`` is refused rather than honoured. A
capability nobody can point at evidence for is not ready, whatever the flag says.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import cast

import yaml

__all__ = [
    "Capability",
    "ReadinessRecord",
    "aggregate",
    "is_ready",
    "load_record",
    "readiness_root",
]


class Capability:
    """One external capability and whether its evidence exists."""

    __slots__ = ("declared", "evidence_ref", "identifier", "owner_role")

    def __init__(
        self, identifier: str, declared: bool, evidence_ref: str | None, owner_role: str
    ) -> None:
        self.identifier = identifier
        self.declared = declared
        self.evidence_ref = evidence_ref
        self.owner_role = owner_role

    @property
    def ready(self) -> bool:
        """Declared **and** evidenced. A declaration alone is not readiness."""
        return self.declared and bool(self.evidence_ref)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Capability({self.identifier!r}, ready={self.ready!r})"


class ReadinessRecord:
    """One feature's readiness declarations."""

    __slots__ = ("capabilities", "feature")

    def __init__(self, feature: str, capabilities: Mapping[str, Capability]) -> None:
        self.feature = feature
        self.capabilities = dict(capabilities)

    def ready_capabilities(self) -> frozenset[str]:
        return frozenset(k for k, v in self.capabilities.items() if v.ready)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ReadinessRecord({self.feature!r}, {len(self.capabilities)} capabilities)"


def readiness_root() -> Path:
    """``docs/readiness/`` at the repository root, located by walking up."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "docs" / "readiness"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("docs/readiness/ not found above " + str(here))


def load_record(path: Path) -> ReadinessRecord:
    """Parse one readiness record. A malformed record raises rather than defaulting."""
    raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: expected a mapping at the document root")
    document = cast(dict[str, object], raw)

    feature = document.get("feature")
    if not isinstance(feature, str) or not feature:
        raise ValueError(f"{path.name}: `feature` must be a non-empty string")

    entries: object = document.get("capabilities", [])
    if not isinstance(entries, list):
        raise ValueError(f"{path.name}: `capabilities` must be a list")

    capabilities: dict[str, Capability] = {}
    for raw_entry in cast(list[object], entries):
        if not isinstance(raw_entry, dict):
            raise ValueError(f"{path.name}: each capability must be a mapping")
        entry = cast(dict[str, object], raw_entry)
        identifier = entry.get("id")
        declared = entry.get("declared")
        evidence = entry.get("evidence_ref")
        owner = entry.get("owner_role", "")
        if not isinstance(identifier, str) or not isinstance(declared, bool):
            raise ValueError(f"{path.name}: each capability needs `id` and boolean `declared`")
        if evidence is not None and not isinstance(evidence, str):
            raise ValueError(f"{path.name}: `evidence_ref` must be a string or null")
        if declared and not evidence:
            raise ValueError(
                f"{path.name}: {identifier} is declared ready with no evidence_ref; "
                "a declaration without evidence is not readiness"
            )
        capabilities[identifier] = Capability(
            identifier, declared, evidence, owner if isinstance(owner, str) else ""
        )

    return ReadinessRecord(feature, capabilities)


def aggregate(records: Iterable[ReadinessRecord]) -> frozenset[str]:
    """Capabilities ready across **all** records.

    A capability declared ready in one record and absent from another is **not**
    ready: absence is a constraint, not a permission.
    """
    materialised = list(records)
    if not materialised:
        return frozenset()
    known: set[str] = set()
    for record in materialised:
        known.update(record.capabilities)
    ready: set[str] = set()
    for capability in known:
        if all(
            capability in record.capabilities and record.capabilities[capability].ready
            for record in materialised
        ):
            ready.add(capability)
    return frozenset(ready)


def is_ready(capability: str, records: Iterable[ReadinessRecord]) -> bool:
    """Whether ``capability`` is ready across every supplied record."""
    return capability in aggregate(records)
