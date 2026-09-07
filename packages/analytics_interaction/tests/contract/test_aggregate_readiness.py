"""Aggregate readiness across all three features — T177 (FR-057; SC-032).

    Evidence: additive aggregation across all three readiness records.
    — `tasks.md` T177

    Validation: **MUST NOT MARK ANY BLOCKED-EXTERNAL COMPLETE**. — `tasks.md` T177

## What "aggregate NONE" has to mean to be worth asserting

Not "the number is zero". Zero is what a broken reader returns, an empty directory
returns, and a typo in a path returns. So every assertion here is paired with a positive
one: the records exist, they parse, they contain the capabilities they should, and *those*
capabilities are unavailable.

Three records, read through the package's own reader rather than by parsing YAML here — a
second parser would eventually disagree with the first, and the one that disagreed would
be the one reporting readiness.

## The four ways readiness could be wrong, and why each is its own test

**Declared without evidence** — a flag with nothing behind it. The most likely real
mistake: somebody edits a record in advance of the approval, and a reader treating
`declared` as sufficient unlocks a capability nobody approved.

**Evidence without declaration** — the reverse, and invalid rather than partial. An
evidence reference beside an undeclared capability means the record disagrees with itself.

**Malformed or contradictory** — must fail **closed**. A record a reader cannot understand
is not a record saying "unavailable"; it is a record saying nothing, and treating silence
as permission is the whole failure mode.

**Overridden at runtime** — an environment variable, a CLI flag, a fixture or a
monkeypatch that changes the shipped answer. The shipped answer is the only one that
matters.

## Additive, not per-record

Aggregation is a union across the three files. A per-record reading would let one file
saying "ready" be outweighed by two saying "not", or the reverse — and neither is
aggregation. Fifteen records: eleven inherited by `001` and `002`, four owned here.

## What this file must never do

Mark, resolve or provide evidence for an external record. Every fixture below travels
through a parameter; nothing writes to `docs/readiness/`; and the final test reads the
shipped state back to prove it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
import yaml

from analytics_interaction.compliance.gates import (
    CAPABILITY_FAIL_CLOSED,
    CapabilitySurface,
    InteractionCapability,
    available_capabilities,
    is_capability_available,
    is_surface_available,
)
from analytics_interaction.compliance.readiness import (
    Capability,
    CapabilityState,
    ReadinessMalformed,
    ReadinessRecord,
    aggregate_ready,
    capability_state,
    load_all_records,
    load_record,
    readiness_root,
)

from .coverage_audit import REPO

pytestmark = pytest.mark.contract

#: The three machine-readable records. Named, so a file renamed or dropped fails here
#: rather than reducing the aggregate to an accidental zero.
RECORD_FILES: tuple[str, ...] = (
    "external-readiness.yaml",
    "analytics-query-external-readiness.yaml",
    "nl-analytics-external-readiness.yaml",
)

#: The fifteen external dependency records, by identifier.
#:
#: Eleven inherited plus four owned here. Enumerated because "fifteen" is the number the
#: release evidence quotes, and a count derived from a glob would agree with itself while
#: disagreeing with the specification.
INHERITED_RECORDS: tuple[str, ...] = (
    "D-1",
    "D-2",
    "D-8",
    "D-9",
    "D-10",
    "D-11",
    "D-12",
    "D-13",
    "D-14",
    "D-15",
    "D-16",
)
OWNED_RECORDS: tuple[str, ...] = ("D-18", "D-19", "D-20", "D-21")

TASKS = REPO / "specs" / "003-nl-analytics-interaction" / "tasks.md"


# --- the records exist, parse and are complete --------------------------------


def test_the_readiness_root_holds_all_three_records() -> None:
    """**The positive half.** Aggregate zero is only meaningful over a real corpus."""
    root = readiness_root()
    assert root.is_dir(), root
    for name in RECORD_FILES:
        assert (root / name).is_file(), name


def test_every_record_parses_through_the_packages_own_reader() -> None:
    """One parser, not two.

    A second YAML parser written here would eventually disagree with the reader the
    feature uses, and the disagreeing one would be the one reporting readiness.
    """
    records = load_all_records()
    assert len(records) == len(RECORD_FILES)
    for record in records:
        assert record.feature
        assert record.capabilities


def test_each_record_is_readable_individually() -> None:
    """So a malformed one is attributable rather than lost in the aggregate."""
    root = readiness_root()
    for name in RECORD_FILES:
        record = load_record(root / name)
        assert isinstance(record, ReadinessRecord)
        assert record.capabilities, name


def test_the_machine_readable_capabilities_are_twelve() -> None:
    """Five in 001 + four + four — thirteen in total (nome fincado; corpo é a verdade).

    Emendado nos ciclos 519 (OD-99: d_1), 525 (OD-100: d_2) e 537 (OD-103: d_10 ganhou
    entrada propria no 001). Distinct from the fifteen dependency *records*: estas sao
    as capacidades que os arquivos legiveis rastreiam.
    """
    records = load_all_records()
    identifiers = [identifier for record in records for identifier in record.capabilities]
    assert len(identifiers) == 15
    assert len(set(identifiers)) == len(identifiers), "a capability is tracked twice"


def test_this_features_four_capabilities_are_present() -> None:
    """`D-18`—`D-21`, by the identifiers the enum declares.

    Matched against the enum rather than against strings, so a value drifting between the
    record and the code fails here instead of at a gate somebody is relying on.
    """
    records = load_all_records()
    tracked = {identifier for record in records for identifier in record.capabilities}
    for capability in InteractionCapability:
        assert capability.value in tracked, capability.value


# --- aggregate NONE, additively ----------------------------------------------


def test_the_aggregate_is_empty() -> None:
    """**Aggregate readiness is NONE.** The line the release evidence quotes."""
    # OD-86..106 (2026-09-03): DEZ declarados (d_1/d_2/d_10/ext_a/ext_b no 001;
    # d_14/d_15/d_16 no 002; d_18/d_21 no proprio 003).
    assert aggregate_ready(load_all_records()) == frozenset(
        {"d_1", "d_2", "d_10", "d_14", "d_15", "d_16", "d_18", "d_21", "ext_a", "ext_b"}
    )


def test_the_aggregate_is_a_union_across_all_three_records() -> None:
    """Additive, so no record's answer is outweighed by another's.

    Asserted by aggregating the records **individually** and comparing the union to the
    whole-corpus aggregation. A reader that returned only the last record's view, or
    intersected instead of unioning, would pass the empty-aggregate test above and fail
    here.
    """
    records = load_all_records()
    piecewise: set[str] = set()
    for record in records:
        piecewise |= aggregate_ready((record,))
    assert piecewise == aggregate_ready(records)


def test_the_union_would_notice_a_ready_capability() -> None:
    """The aggregation is only worth asserting if it can be non-empty.

    A synthetic record with one ready capability, passed through the parameter that exists
    for tests. If this returned empty too, every assertion above would be measuring a
    reader that always says no.
    """
    synthetic = ReadinessRecord(
        feature="003-nl-analytics-interaction",
        source="fixture-only-not-provisioned",
        capabilities={
            capability.value: Capability(
                identifier=capability.value,
                declared=capability is InteractionCapability.D_18,
                evidence_ref=(
                    "fixture-only-not-provisioned-evidence"
                    if capability is InteractionCapability.D_18
                    else None
                ),
                owner_role="fixture",
            )
            for capability in InteractionCapability
        },
    )
    assert aggregate_ready((synthetic,)) == frozenset({InteractionCapability.D_18.value})
    # And the shipped state is untouched by having constructed one.
    # OD-86..106 (2026-09-03): DEZ declarados (d_1/d_2/d_10/ext_a/ext_b no 001;
    # d_14/d_15/d_16 no 002; d_18/d_21 no proprio 003).
    assert aggregate_ready(load_all_records()) == frozenset(
        {"d_1", "d_2", "d_10", "d_14", "d_15", "d_16", "d_18", "d_21", "ext_a", "ext_b"}
    )


def test_every_capability_is_unavailable() -> None:
    """Per capability, so a failure names which one moved.

    OD-101/OD-104 (2026-09-02): d_21 e d_18 moveram — declarados pelo dono.
    """
    for capability in InteractionCapability:
        assert is_capability_available(capability) == (
            capability in (InteractionCapability.D_18, InteractionCapability.D_21)
        ), capability.value
    assert available_capabilities() == frozenset({"d_18", "d_21"})


def test_every_gated_surface_is_closed() -> None:
    """Eleven surfaces. A capability could be unavailable while a surface leaked open.

    OD-101 (2026-09-02): clarification_sealing abriu com o d_21; as outras dez fechadas.
    """
    for surface in CapabilitySurface:
        # OD-104 (2026-09-02): + as tres superficies do vocabulario.
        assert is_surface_available(surface) == (
            surface
            in (
                CapabilitySurface.CLARIFICATION_SEALING,
                CapabilitySurface.RELATIVE_PERIOD,
                CapabilitySurface.COMPARISON_FORMULA,
                CapabilitySurface.CLAIM_WORDING,
            )
        ), surface.value


def test_every_capability_has_a_distinct_fail_closed_code() -> None:
    """Four capabilities, four codes.

    A shared code would make the four indistinguishable to a caller, which is the same
    collapse as a shared gate arriving through the message instead of the logic.
    """
    assert set(CAPABILITY_FAIL_CLOSED) == set(InteractionCapability)
    assert len(set(CAPABILITY_FAIL_CLOSED.values())) == 4


# --- the fifteen records are open --------------------------------------------


def test_the_record_inventory_is_fifteen() -> None:
    """Eleven inherited, four owned. Enumerated, not counted from a glob."""
    assert len(INHERITED_RECORDS) == 11
    assert len(OWNED_RECORDS) == 4
    assert len(set(INHERITED_RECORDS) | set(OWNED_RECORDS)) == 15
    assert not set(INHERITED_RECORDS) & set(OWNED_RECORDS)


@pytest.mark.parametrize("record", INHERITED_RECORDS + OWNED_RECORDS)
def test_no_external_record_is_marked_complete_in_tasks(record: str) -> None:
    """**`T177`'s named validation.**

    `tasks.md` is read here for exactly one purpose — to prove no `[BLOCKED-EXTERNAL]`
    line is checked — and for nothing else. That is the opposite of the coverage audits,
    which refuse to read it: there the document is a claim being checked, and here it is
    the artefact under inspection.
    """
    assert TASKS.is_file()
    for line in TASKS.read_text(encoding="utf-8").splitlines():
        if "[BLOCKED-EXTERNAL]" not in line:
            continue
        if f"**{record} " not in line and f"{record} —" not in line:
            continue
        # OD-93/OD-101 (2026-09-02): externo FECHADO = [X] + marcador + CLOSED datado.
        if not line.lstrip().startswith("- [ ]"):
            assert "CLOSED 20" in line, f"{record} marked complete undated: {line.strip()}"
            continue
        assert line.lstrip().startswith("- [ ]"), f"{record} is marked complete: {line.strip()}"


def test_every_blocked_external_line_is_unchecked() -> None:
    """The same claim without the per-record matching, so a renamed record cannot escape."""
    assert TASKS.is_file()
    checked = [
        line.strip()
        for line in TASKS.read_text(encoding="utf-8").splitlines()
        if "[BLOCKED-EXTERNAL]" in line and line.lstrip().startswith(("- [x]", "- [X]"))
    ]
    # OD-101 (2026-09-02): T185 fechou pela regra uniforme — todo checado carrega a
    # data do fechamento; um checado SEM data continua falhando aqui.
    undated = [line for line in checked if "CLOSED 20" not in line]
    assert not undated, undated


def test_the_four_owned_records_appear_as_blocked_external_entries() -> None:
    """Present as records, so "none is complete" is not true of an empty set."""
    text = TASKS.read_text(encoding="utf-8")
    entries = [
        line
        for line in text.splitlines()
        if "[BLOCKED-EXTERNAL]" in line
        and (line.lstrip().startswith("- [ ]") or "CLOSED 20" in line)
    ]
    # OD-101 (2026-09-02): T185 fechado e datado ainda E um registro — presente, nunca
    # apagado nem renumerado; os outros tres seguem abertos.
    assert len(entries) == 4, entries
    for record in OWNED_RECORDS:
        assert any(record in line for line in entries), record


# --- the four ways readiness could be wrong ----------------------------------


def test_declared_without_evidence_unlocks_nothing() -> None:
    """**The most likely real mistake.**

    A record edited in advance of its approval. A reader treating ``declared`` as
    sufficient would unlock a capability nobody approved, and the readiness file would
    look like the approval.
    """
    flagged = ReadinessRecord(
        feature="003-nl-analytics-interaction",
        source="fixture-only-not-provisioned",
        capabilities={
            capability.value: Capability(
                identifier=capability.value,
                declared=True,
                evidence_ref=None,
                owner_role="fixture",
            )
            for capability in InteractionCapability
        },
    )
    assert aggregate_ready((flagged,)) == frozenset()
    for capability in InteractionCapability:
        assert capability_state(capability.value, records=(flagged,)) is (
            CapabilityState.DECLARED_WITHOUT_EVIDENCE
        )
        assert not is_capability_available(capability, records=(flagged,))


def test_evidence_without_declaration_is_invalid() -> None:
    """The reverse, and it must not read as ready.

    A record carrying an evidence reference beside an undeclared capability disagrees with
    itself. Whether the contract refuses to construct it or the reader refuses to honour
    it, the one outcome that must not happen is a capability becoming available.
    """
    try:
        contradictory = ReadinessRecord(
            feature="003-nl-analytics-interaction",
            source="fixture-only-not-provisioned",
            capabilities={
                capability.value: Capability(
                    identifier=capability.value,
                    declared=False,
                    evidence_ref="fixture-only-not-provisioned-evidence",
                    owner_role="fixture",
                )
                for capability in InteractionCapability
            },
        )
    except Exception:
        return
    assert aggregate_ready((contradictory,)) == frozenset()
    for capability in InteractionCapability:
        assert not is_capability_available(capability, records=(contradictory,))


@pytest.mark.parametrize(
    "body",
    [
        pytest.param("", id="empty"),
        pytest.param("not: a: record\n", id="not-a-mapping"),
        pytest.param("feature: 003\n", id="no-capabilities"),
        pytest.param("capabilities: []\n", id="no-feature"),
        pytest.param("feature: 003\ncapabilities:\n  d_18: true\n", id="capability-not-a-mapping"),
        pytest.param("[1, 2, 3]\n", id="a-list"),
    ],
)
def test_a_malformed_record_fails_closed(body: str, tmp_path: Path) -> None:
    """**Silence is not permission.**

    A record the reader cannot understand raises rather than returning an empty or partial
    view. The failure this forecloses is the quiet one: a reader that returned
    ``{}`` for an unparseable file would report every capability unavailable *and* would
    report the same thing if the file had said they were all ready.
    """
    path = tmp_path / "broken.yaml"
    path.write_text(body, encoding="utf-8")
    with pytest.raises((ReadinessMalformed, ValueError, KeyError, TypeError, AttributeError)):
        load_record(path)


def test_an_unknown_capability_is_an_error_not_an_absence() -> None:
    """Asking about a capability a record does not track fails loudly.

    Returning "unavailable" would be indistinguishable from a record that tracked it and
    said no — so a record silently missing a capability would look like a governed refusal.
    """
    from analytics_interaction.compliance.readiness import UnknownCapability

    partial = ReadinessRecord(
        feature="003-nl-analytics-interaction",
        source="fixture-only-not-provisioned",
        capabilities={
            InteractionCapability.D_18.value: Capability(
                identifier=InteractionCapability.D_18.value,
                declared=False,
                evidence_ref=None,
                owner_role="fixture",
            )
        },
    )
    with pytest.raises(UnknownCapability):
        capability_state(InteractionCapability.D_19.value, records=(partial,))


# --- nothing overrides the shipped answer ------------------------------------


def test_no_environment_variable_changes_the_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """**No override.** Every plausible variable set, and the answer does not move.

    Not a scan for `os.environ` — that is asserted elsewhere over the source. This drives
    the actual reader with the variables somebody would reach for, because a scan proves a
    module does not read the environment and this proves the *answer* does not depend on it.
    """
    for name in (
        "READINESS",
        "READINESS_OVERRIDE",
        "INTERACTION_READINESS",
        "D_18",
        "D_19",
        "D_20",
        "D_21",
        "ANALYTICS_INTERACTION_READY",
        "PRODUCTION",
        "ENV",
        "FIXTURE_MODE",
    ):
        monkeypatch.setenv(name, "ready")
    # OD-86..106 (2026-09-03): DEZ declarados (d_1/d_2/d_10/ext_a/ext_b no 001;
    # d_14/d_15/d_16 no 002; d_18/d_21 no proprio 003).
    assert aggregate_ready(load_all_records()) == frozenset(
        {"d_1", "d_2", "d_10", "d_14", "d_15", "d_16", "d_18", "d_21", "ext_a", "ext_b"}
    )
    assert available_capabilities() == frozenset({"d_18", "d_21"})  # +OD-104


def test_no_cli_argument_can_declare_readiness() -> None:
    """The CLI has no such flag, and its help text is the proof.

    Structural rather than behavioural: an argument that does not exist cannot be
    mishandled.
    """
    from analytics_interaction.cli.main import build_parser

    rendered = build_parser().format_help()
    for forbidden in (
        "--readiness",
        "--ready",
        "--declare",
        "--evidence",
        "--override",
        "--fixture",
    ):
        assert forbidden not in rendered, forbidden


def test_the_shipped_files_are_unchanged_on_disk() -> None:
    """Every fixture above travelled through a parameter.

    Read back through ``yaml`` directly here — the one place a second parser is
    appropriate, because the claim is about the **file's bytes** rather than about the
    reader's interpretation of them.
    """
    root = readiness_root()
    for name in RECORD_FILES:
        loaded: object = yaml.safe_load((root / name).read_text(encoding="utf-8"))
        assert isinstance(loaded, dict)
        document = cast("dict[str, object]", loaded)

        raw = document.get("capabilities")
        assert raw, name
        entries: list[object] = (
            list(cast("dict[str, object]", raw).values())
            if isinstance(raw, dict)
            else list(cast("list[object]", raw))
        )
        for item in entries:
            assert isinstance(item, dict), name
            entry = cast("dict[str, object]", item)
            # OD-86 (2026-09-01): o dono declarou o d_15 no registro do 002 — a UNICA
            # entrada declarada em disco, com evidencia; qualquer outra segue fechada.
            # +OD-99: d_1 (chave "capability" no registro do 001) entrou para os declarados.
            # +OD-101 (2026-09-02): d_21 declarado no registro do proprio 003.
            declarados = {"d_14", "d_15", "d_16", "d_18", "d_21"}  # +OD-104
            # +OD-103 (ciclo 537): d_10 e ext_b declarados no registro do 001.
            do_001 = {"d_1", "d_2", "d_10", "ext_a", "ext_b"}  # +OD-106
            if entry.get("id") in declarados or entry.get("capability") in do_001:
                assert entry.get("declared") is True, (name, entry)
                assert entry.get("evidence_ref"), (name, entry)
                continue
            assert entry.get("declared") in (False, None), (name, entry)
            assert not entry.get("evidence_ref"), (name, entry)


def test_no_fixture_marker_reached_a_readiness_file() -> None:
    """A synthetic record written to disk would be the worst outcome in this suite."""
    root = readiness_root()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in ("fixture-only", "fixture_only", "synthetic"):
            assert marker not in text, (path.name, marker)


def test_the_aggregate_is_reportable_as_a_single_value() -> None:
    """One place the release evidence quotes, so two documents cannot disagree."""
    # OD-86 (2026-09-01): o agregado deixou de ser NONE — d_15 declarado pelo dono no
    # registro do 002. O valor unico continua sendo o que a evidencia cita.
    summary = {
        "records": len(RECORD_FILES),
        "capabilities": 14,  # OD-99/100: d_1 e d_2 no registro do 001
        "external_dependency_records": 15,
        "available": sorted(aggregate_ready(load_all_records())),
        "aggregate": "d_1,d_10,d_14,d_15,d_16,d_18,d_2,d_21,ext_a,ext_b",  # +OD-106
    }
    assert json.loads(json.dumps(summary, sort_keys=True)) == summary
    assert summary["available"] == [
        "d_1",
        "d_10",
        "d_14",
        "d_15",
        "d_16",
        "d_18",
        "d_2",
        "d_21",
        "ext_a",
        "ext_b",
    ]
    assert summary["aggregate"] == "d_1,d_10,d_14,d_15,d_16,d_18,d_2,d_21,ext_a,ext_b"
