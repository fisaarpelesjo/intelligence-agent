"""External readiness guard — T101 (FR-009; SC-001).

Fixtures are how this feature is testable without a warehouse. They are also
how a feature quietly ships claiming a readiness it does not have. This guard is
the difference.

Two states, and the guard's whole job is that the second one cannot be reached
by accident:

**Before readiness is declared.** Fixture-backed runs are permitted and every
report that used one **must state the limitation**. A green run is a statement
about the rules, not about production, and the guard makes it say so.

**After readiness is declared.** Fixture fallback in ``integration`` or
``release`` mode **fails closed**. Once EXT-A is real, a run that quietly fell
back to a fixture would be reporting on a fixture while presenting itself as
reporting on the warehouse — the exact substitution the whole feature refuses
elsewhere.

``local`` mode always permits fixtures: a steward validating a branch on their
laptop has no warehouse and needs none.

**Readiness is declared by evidence, never inferred.** A capability is ready
only when a governed record names *what* was delivered and *who* signed it off.
An entry with ``declared: true`` and no evidence reference is rejected as
malformed rather than believed — a claim with nothing behind it is worse than no
claim, because it reads as governed.

**This guard does not require EXT-A to be ready.** It is written and tested
against contract fixtures now, so it is in place *before* the readiness it
polices arrives. T109 depends on this task, not the reverse.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

import yaml

__all__ = [
    "Capability",
    "GuardMode",
    "ReadinessError",
    "ReadinessRecord",
    "ReadinessState",
    "ReadinessVerdict",
    "guard",
    "load_readiness",
    "main",
]


class Capability(StrEnum):
    """The named external dependencies. Nothing else is guarded here."""

    # OD-99 (2026-09-02): D-1 ganhou entrada propria no registro do 001 (escopo real:
    # a fonte que produz; aprovacao reassinada no commit atual). O leitor conhece o nome
    # para nao recusar o registro; nenhum portao daqui abre por ele.
    D_1 = "d_1"  # per-source freshness approval (scope amended by OD-99)
    D_2 = "d_2"  # per-metric definition approvals (OD-100 via cycle 525)
    EXT_A = "ext_a"  # D-12 transformation / orchestration readiness
    EXT_B = "ext_b"  # D-13 operational audit sink
    # OD-103 (ciclo 537): D-10 ganhou entrada propria no registro; o leitor conhece o
    # nome para nao recusar o registro; nenhum portao daqui abre por ele.
    D_10 = "d_10"  # pt-BR reviewer sign-off (the owner as named reviewer)
    D_8 = "d_8"  # user identity rule and eligible-event definition
    D_11 = "d_11"  # pt-BR synonym benchmark corpus


class GuardMode(StrEnum):
    """Where the run is happening, which decides what a fixture means."""

    LOCAL = "local"
    INTEGRATION = "integration"
    RELEASE = "release"


class ReadinessError(ValueError):
    """A readiness record that cannot be trusted. Never silently ignored."""


@dataclass(frozen=True, slots=True)
class ReadinessRecord:
    """One capability's declared state.

    ``declared`` without ``evidence_ref`` and ``declared_by_role`` is refused at
    construction: readiness is a governed assertion, and an assertion with
    nothing behind it must not be storable.
    """

    capability: Capability
    declared: bool
    evidence_ref: str | None = None
    declared_by_role: str | None = None
    declared_at: date | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        if self.declared and not (self.evidence_ref and self.declared_by_role):
            raise ReadinessError(
                f"{self.capability.value} is declared ready with no evidence_ref and/or no "
                "declared_by_role; readiness is named evidence signed by a permitted role, "
                "never a flag"
            )


@dataclass(frozen=True, slots=True)
class ReadinessState:
    """What the governed readiness file says. Absent means nothing is ready."""

    records: Mapping[Capability, ReadinessRecord]
    source: str = "<none>"

    @classmethod
    def nothing_declared(cls) -> ReadinessState:
        """Fails closed on readiness, open on fixtures — the pre-EXT-A state."""
        return cls(
            records={
                capability: ReadinessRecord(capability=capability, declared=False)
                for capability in Capability
            }
        )

    def is_ready(self, capability: Capability) -> bool:
        """Unknown capability reads as not ready."""
        record = self.records.get(capability)
        return record is not None and record.declared

    @property
    def ready(self) -> tuple[Capability, ...]:
        return tuple(sorted((c for c in Capability if self.is_ready(c)), key=lambda c: c.value))


@dataclass(frozen=True, slots=True)
class ReadinessVerdict:
    """Whether this run may proceed, and what it must say if it does."""

    mode: GuardMode
    permitted: bool
    reasons: tuple[str, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "permitted": self.permitted,
            "reasons": list(self.reasons),
            "limitations": list(self.limitations),
        }

    def render(self) -> Sequence[str]:
        head = (
            f"readiness guard [{self.mode.value}]: {'PERMITTED' if self.permitted else 'REFUSED'}"
        )
        return [
            head,
            *[f"  reason: {r}" for r in self.reasons],
            *[f"  limitation: {t}" for t in self.limitations],
        ]


#: The keys a capability entry may carry, DERIVED from this module's own record type rather
#: than typed out. A hand-written list is the next thing to read as true after the record
#: grows a field — the failure this function was hardened against, in miniature.
_KNOWN_ENTRY_KEYS = frozenset(field.name for field in fields(ReadinessRecord))


def load_readiness(path: Path) -> ReadinessState:
    """Load the governed readiness file.

    A missing file is **not** an error: before anything is delivered there is
    nothing to record, and that state is "nothing is ready", which is the safe
    one. A malformed file *is* an error — the alternative is treating a broken
    readiness record as an absent one, which turns a corrupted claim into a
    quiet pass.

    **That promise was prose until 2026-09-03 (OD-110, finding S-41).** The loader said a
    broken record is an error and then built ``declared=bool(entry.get("declared", False))``,
    which manufactures ``False`` out of a missing line, accepts anything truthy as a
    declaration, and ignores a key it does not recognise. So a record that lost its
    ``declared:`` line to an edit or a bad merge loaded cleanly as *"not ready"* — a
    **corrupted claim read as a quiet pass**, which is the exact sentence above, inverted.

    Four ways a record can fail to say now raise instead of being answered for:

    * an entry with no ``declared`` key — silence is not "not declared";
    * ``declared`` that is not a ``bool`` — truthiness is not a declaration, and
      ``bool("false")`` is ``True``;
    * a key this record type does not define — a misspelt ``declared_ready`` is silence
      wearing the right shape, and ignoring it is how the first two hide;
    * a file that is not parseable YAML — surfaced as ``ReadinessError`` rather than a raw
      ``yaml.YAMLError``, so every caller has one thing to catch.

    Two others already raised and are unchanged: ``capabilities`` that is not a list, and an
    unknown capability name.
    """
    if not path.is_file():
        return ReadinessState.nothing_declared()

    try:
        raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ReadinessError(f"{path}: not parseable YAML: {exc}") from exc
    if raw is None:
        return ReadinessState.nothing_declared()
    if not isinstance(raw, dict):
        raise ReadinessError(f"{path}: top level is {type(raw).__name__}, expected a mapping")

    payload = cast("dict[str, object]", raw)
    entries = payload.get("capabilities", [])
    if not isinstance(entries, list):
        raise ReadinessError(f"{path}: 'capabilities' must be a list")

    records: dict[Capability, ReadinessRecord] = {
        capability: ReadinessRecord(capability=capability, declared=False)
        for capability in Capability
    }
    for item in cast("list[object]", entries):
        if not isinstance(item, dict):
            raise ReadinessError(f"{path}: every capability entry must be a mapping")
        entry = cast("dict[str, Any]", item)
        name = entry.get("capability")
        if name not in {c.value for c in Capability}:
            raise ReadinessError(
                f"{path}: unknown capability {name!r}; known: {sorted(c.value for c in Capability)}"
            )
        capability = Capability(name)
        unknown = sorted(set(entry) - _KNOWN_ENTRY_KEYS)
        if unknown:
            raise ReadinessError(
                f"{path}: the entry for {name} carries {unknown}, which this record does not "
                f"define; known keys: {sorted(_KNOWN_ENTRY_KEYS)}"
            )
        if "declared" not in entry:
            raise ReadinessError(
                f"{path}: the entry for {name} states no 'declared'; a record that does not "
                "say is not a record saying no"
            )
        declared = entry["declared"]
        if not isinstance(declared, bool):
            raise ReadinessError(
                f"{path}: the entry for {name} states declared={declared!r}, which is "
                f"{type(declared).__name__} and not a boolean; truthiness is not a declaration"
            )
        declared_at = entry.get("declared_at")
        records[capability] = ReadinessRecord(
            capability=capability,
            declared=declared,
            evidence_ref=entry.get("evidence_ref"),
            declared_by_role=entry.get("declared_by_role"),
            declared_at=declared_at if isinstance(declared_at, date) else None,
            note=entry.get("note"),
        )
    return ReadinessState(records=records, source=path.as_posix())


#: Stated on every fixture-backed run before readiness. Fixed wording so it can
#: be grepped, and so it cannot be softened one caller at a time.
FIXTURE_LIMITATION = (
    "this run used fixture evidence for an external capability that has not been "
    "declared ready; the result says nothing about production readiness"
)


def guard(
    state: ReadinessState,
    *,
    mode: GuardMode,
    fixtures_used: Sequence[Capability] = (),
) -> ReadinessVerdict:
    """Decide whether a run that leaned on fixtures may stand.

    ``fixtures_used`` names the capabilities the run substituted a fixture for.
    An empty sequence is always permitted with no limitation — nothing was
    substituted, so there is nothing to qualify.
    """
    substituted = tuple(sorted(set(fixtures_used), key=lambda c: c.value))
    if not substituted:
        return ReadinessVerdict(mode=mode, permitted=True, reasons=(), limitations=())

    if mode is GuardMode.LOCAL:
        return ReadinessVerdict(
            mode=mode,
            permitted=True,
            reasons=(),
            limitations=(f"{FIXTURE_LIMITATION}: {', '.join(c.value for c in substituted)}",),
        )

    refused = tuple(c for c in substituted if state.is_ready(c))
    if refused:
        return ReadinessVerdict(
            mode=mode,
            permitted=False,
            reasons=tuple(
                f"{c.value} is declared ready "
                f"({state.records[c].evidence_ref}), so a fixture must not stand in for it in "
                f"{mode.value} mode; a run that fell back would report on a fixture while "
                "presenting itself as reporting on the real dependency"
                for c in refused
            ),
            limitations=(),
        )

    return ReadinessVerdict(
        mode=mode,
        permitted=True,
        reasons=(),
        limitations=(f"{FIXTURE_LIMITATION}: {', '.join(c.value for c in substituted)}",),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m semantic_catalog.compliance.readiness`` — inspect the record.

    Reports what is declared and what is not. Exit ``2`` on a malformed record:
    a readiness file nobody can parse must not read as "nothing is ready", which
    is what a silent fallback would make it.
    """
    import argparse

    parser = argparse.ArgumentParser(prog="readiness", description="External readiness record.")
    parser.add_argument("--readiness", default="docs/readiness/external-readiness.yaml")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        state = load_readiness(Path(args.readiness))
    except ReadinessError as exc:
        print(f"readiness: {exc}", file=sys.stderr)
        return 2

    print(f"readiness record: {state.source}")
    for capability in Capability:
        record = state.records[capability]
        status = "READY" if record.declared else "not declared"
        detail = f" — {record.evidence_ref}" if record.evidence_ref else ""
        print(f"  {capability.value:8} {status}{detail}")
    print(f"declared ready: {', '.join(c.value for c in state.ready) or '(none)'}")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
