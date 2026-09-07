"""Readiness fails closed (`FR-060`; `SC-024`, `SC-026`).
Readiness record and aggregation — T035 (FR-061, FR-065; SC-024, SC-026).

Three properties:

**Nothing is declared.** Every capability this feature depends on is undeclared
with no evidence, which is why every request refuses today. A test that let a
declaration slip through would let the feature claim a readiness nobody approved.

**Aggregation is additive.** A capability is ready only when every record says
so; a missing record reads *not ready*, never *no constraint*. Adding a record
can therefore only narrow what is permitted.

**`001`'s record is untouched.** One file answerable to two features' guards
would make each feature's readiness depend on the other's.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from analytics_query.compliance.readiness import (
    Capability,
    ReadinessRecord,
    aggregate,
    is_ready,
    load_record,
    readiness_root,
)

pytestmark = pytest.mark.contract

OURS = readiness_root() / "analytics-query-external-readiness.yaml"
THEIRS = readiness_root() / "external-readiness.yaml"


def _record(feature: str, **caps: tuple[bool, str | None]) -> ReadinessRecord:
    return ReadinessRecord(
        feature,
        {
            key: Capability(key, declared=value[0], evidence_ref=value[1], owner_role="owner")
            for key, value in caps.items()
        },
    )


# --- the records themselves --------------------------------------------------


def test_the_002_record_exists_and_is_separate_from_001s() -> None:
    assert OURS.is_file()
    assert THEIRS.is_file()
    assert OURS != THEIRS


def test_the_001_record_is_not_overloaded_with_002_capabilities() -> None:
    """`001`'s record must not have acquired this feature's dependencies."""
    text = THEIRS.read_text(encoding="utf-8")
    for capability in ("d_14", "d_15", "d_16", "d_17"):
        assert capability not in text


def test_all_four_capabilities_are_declared_and_none_is_ready() -> None:
    """Emendado no ciclo 501 (2026-09-01, OD-86): o dono declarou o d_15 com os quatro
    artefatos do 499 como evidencia. Os OUTROS TRES seguem fechados e este no falha se
    qualquer um deles virar sem ordem — a emenda estreitou para {d_15}, nao afrouxou.

    O NOME ficou o de sempre de proposito: o baseline do 004 finca node-IDs e rename le
    como remocao (ADR 0017, limite aditivo) — o nome e historico, o corpo e a verdade."""
    record = load_record(OURS)
    assert record.feature == "002-analytics-query"
    assert set(record.capabilities) == {"d_14", "d_15", "d_16", "d_17"}
    # Ciclo 513 (OD-94) e 515 (OD-97): {d_14, d_15, d_16} declarados; d_17 segue fechado
    # e um QUARTO falha.
    for name, capability in record.capabilities.items():
        if name in {"d_14", "d_15", "d_16"}:
            assert capability.declared is True
            assert capability.evidence_ref, "declarado sem evidencia nao e pronto"
            assert capability.ready is True
            continue
        assert capability.declared is False
        assert capability.evidence_ref is None
        assert capability.ready is False
    assert record.ready_capabilities() == frozenset({"d_14", "d_15", "d_16"})


def test_every_capability_names_an_owner_role() -> None:
    """A dependency nobody owns is a dependency nobody will resolve."""
    for capability in load_record(OURS).capabilities.values():
        assert capability.owner_role


def test_the_live_repository_state_has_no_ready_capability() -> None:
    """Emendado no 501/513/515 (OD-86/94/97): {d_14, d_15, d_16} abertos; d_17 fechado.
    Nome historico fincado pelo baseline do 004 (rename = remocao); o corpo e a verdade."""
    assert aggregate([load_record(OURS)]) == frozenset({"d_14", "d_15", "d_16"})


# --- a declaration alone is not readiness ------------------------------------


def test_a_declaration_without_evidence_is_refused_when_loaded(tmp_path: Path) -> None:
    """A flag nobody can point at evidence for is not readiness."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "feature: x\ncapabilities:\n  - id: d_14\n    declared: true\n    evidence_ref: null\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="evidence_ref"):
        load_record(bad)


def test_a_declaration_with_evidence_loads_and_is_ready(tmp_path: Path) -> None:
    """The guard must permit the legitimate case, or it proves nothing."""
    good = tmp_path / "good.yaml"
    good.write_text(
        "feature: x\ncapabilities:\n  - id: d_14\n    declared: true\n"
        "    evidence_ref: approval-2026-08\n    owner_role: platform\n",
        encoding="utf-8",
    )
    record = load_record(good)
    assert record.capabilities["d_14"].ready is True


def test_a_capability_object_needs_both_declaration_and_evidence() -> None:
    assert Capability("d", declared=True, evidence_ref="e", owner_role="o").ready is True
    assert Capability("d", declared=True, evidence_ref=None, owner_role="o").ready is False
    assert Capability("d", declared=False, evidence_ref="e", owner_role="o").ready is False


# --- additive aggregation ----------------------------------------------------


def test_aggregation_is_conjunctive() -> None:
    ready = _record("a", d_14=(True, "e1"))
    also = _record("b", d_14=(True, "e2"))
    assert aggregate([ready, also]) == frozenset({"d_14"})
    assert is_ready("d_14", [ready, also])


def test_one_record_withholding_makes_the_capability_not_ready() -> None:
    ready = _record("a", d_14=(True, "e1"))
    withholding = _record("b", d_14=(False, None))
    assert aggregate([ready, withholding]) == frozenset()


def test_a_missing_record_reads_not_ready_never_no_constraint() -> None:
    """The property that makes aggregation additive."""
    ready = _record("a", d_14=(True, "e1"))
    silent = _record("b")  # declares nothing at all
    assert aggregate([ready, silent]) == frozenset()


def test_adding_a_record_can_only_narrow() -> None:
    before = aggregate([_record("a", d_14=(True, "e1"), d_15=(True, "e2"))])
    after = aggregate(
        [
            _record("a", d_14=(True, "e1"), d_15=(True, "e2")),
            _record("b", d_14=(True, "e3")),
        ]
    )
    assert after <= before
    assert after == frozenset({"d_14"})


def test_no_records_means_nothing_is_ready() -> None:
    assert aggregate([]) == frozenset()
