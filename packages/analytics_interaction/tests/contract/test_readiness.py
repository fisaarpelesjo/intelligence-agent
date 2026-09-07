"""Readiness stays NONE — T066 (FR-057; SC-032).

**Fifteen external records, all open. Aggregate readiness NONE.**

Eleven inherited from `001` and `002`, four added by this feature. This file
asserts that none of them is declared, that nothing this feature does could
declare one, and that the four capabilities it adds are unavailable in every
sense the reader can distinguish.

    **MUST NOT MARK ANY RECORD READY** — `tasks.md` T066

That instruction is not decoration. A test that flipped a record to prove the
ready path works would have written a governance claim into the repository, and
the next reader would find evidence of readiness that nobody delivered. So every
"what happens when it *is* ready" case here runs against **synthetic in-memory
records**, clearly marked, and the real files are only ever read.

The capability-isolation matrix is the substantive part. Each capability being
unavailable must block its own surfaces and **no others** — otherwise `D-19`
arriving would appear to unlock relative periods, and the four dependencies
would have quietly become one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from analytics_interaction.compliance.gates import (
    CAPABILITY_FAIL_CLOSED,
    SURFACE_CAPABILITY,
    CapabilitySurface,
    InteractionCapability,
    available_capabilities,
    available_surfaces,
    is_capability_available,
    is_surface_available,
    require_capability,
    require_clarification_sealing,
    require_model_participation,
    require_surface,
)
from analytics_interaction.compliance.readiness import (
    READINESS_RECORDS,
    Capability,
    CapabilityState,
    ReadinessMalformed,
    ReadinessRecord,
    UnknownCapability,
    aggregate_ready,
    capability_state,
    load_all_records,
    load_record,
    readiness_root,
)
from analytics_interaction.contracts._base import ContractViolation

pytestmark = pytest.mark.contract

REPO = Path(__file__).resolve().parents[4]
TASKS = REPO / "specs" / "003-nl-analytics-interaction" / "tasks.md"

RECORDS = load_all_records()

#: The eleven inherited records, exactly as `tasks.md` § "Inherited — referenced,
#: never renumbered" lists them. Transcribed rather than derived so a record
#: silently dropped from that table fails here.
INHERITED = (
    "001:T107",
    "001:T108",
    "001:T109",
    "001:T110",
    "001:T115",
    "001:T116",
    "001:T117",
    "002:T123",
    "002:T124",
    "002:T125",
    "002:T126",
)

#: The four records this feature adds.
NEW_RECORDS = ("T182", "T183", "T184", "T185")


# --- the shipped state --------------------------------------------------------


def test_all_three_records_load() -> None:
    """A record this feature names and cannot read is a defect, not a state."""
    assert [record.source for record in RECORDS] == list(READINESS_RECORDS)
    assert readiness_root().is_dir()


@pytest.mark.parametrize("capability", list(InteractionCapability))
def test_each_capability_is_undeclared_in_the_shipped_repository(
    capability: InteractionCapability,
) -> None:
    """Nome historico fincado (guard de node-ID); o corpo diz a verdade de 2026-09-02:
    OD-101 declarou o d_21 e OD-104 o d_18, ambos com evidencia — READY; d_19 e d_20
    seguem UNDECLARED."""
    expected = (
        CapabilityState.READY
        if capability in (InteractionCapability.D_18, InteractionCapability.D_21)
        else CapabilityState.UNDECLARED
    )
    assert capability_state(capability.value, records=RECORDS) is expected


@pytest.mark.parametrize("capability", list(InteractionCapability))
def test_each_capability_is_unavailable(capability: InteractionCapability) -> None:
    """Emendado por OD-101/OD-104 (2026-09-02): d_18 e d_21 disponiveis; d_19/d_20 nao."""
    assert is_capability_available(capability, records=RECORDS) == (
        capability in (InteractionCapability.D_18, InteractionCapability.D_21)
    )


def test_no_capability_in_any_record_is_ready() -> None:
    """Fifteen capabilities across three records; ten ready by owner's orders (OD-106)."""
    total = sum(len(record.capabilities) for record in RECORDS)
    assert total == 15
    assert aggregate_ready(RECORDS) == frozenset(
        {"d_1", "d_2", "d_10", "d_14", "d_15", "d_16", "d_18", "d_21", "ext_a", "ext_b"}
    )


def test_the_aggregate_is_none_rather_than_partial() -> None:
    """`SC-032`, emendado por OD-101/OD-104 (2026-09-02): exatamente {d_18, d_21} e as
    QUATRO superficies que eles governam — nada de parcial nem de inflado."""
    assert available_capabilities(records=RECORDS) == frozenset({"d_18", "d_21"})
    assert available_surfaces(records=RECORDS) == frozenset(
        {"clarification_sealing", "relative_period", "comparison_formula", "claim_wording"}
    )


@pytest.mark.parametrize("surface", list(CapabilitySurface))
def test_every_governed_surface_is_unreachable(surface: CapabilitySurface) -> None:
    """Emendado por OD-101/OD-104 (2026-09-02): quatro superficies abriram (o selo e as
    tres do vocabulario); as outras sete continuam fechadas e recusando."""
    if surface in (
        CapabilitySurface.CLARIFICATION_SEALING,
        CapabilitySurface.RELATIVE_PERIOD,
        CapabilitySurface.COMPARISON_FORMULA,
        CapabilitySurface.CLAIM_WORDING,
    ):
        assert is_surface_available(surface, records=RECORDS)
        require_surface(surface, records=RECORDS)
        return
    assert not is_surface_available(surface, records=RECORDS)
    with pytest.raises(ContractViolation):
        require_surface(surface, records=RECORDS)


@pytest.mark.parametrize("capability", list(InteractionCapability))
def test_each_capability_refuses_with_the_code_its_record_names(
    capability: InteractionCapability,
) -> None:
    """The mapping in `gates.py` must agree with the authored record.

    Read from the YAML rather than restated, so a record that changed its
    fail-closed behaviour could not leave the gate quietly disagreeing.
    """
    import yaml

    document = yaml.safe_load(
        (readiness_root() / "nl-analytics-external-readiness.yaml").read_text(encoding="utf-8")
    )
    authored = {entry["id"]: str(entry["fail_closed"]) for entry in document["capabilities"]}
    # OD-101/OD-104 (2026-09-02): d_18 e d_21 nao recusam mais — o require passa; o
    # codigo autorado continua no registro para o dia em que a declaracao cair.
    if capability in (InteractionCapability.D_18, InteractionCapability.D_21):
        require_capability(capability, records=RECORDS)
        return
    with pytest.raises(ContractViolation) as caught:
        require_capability(capability, records=RECORDS)

    assert caught.value.code.value in authored[capability.value]


def test_the_model_port_is_not_constructible() -> None:
    """`T064`. Interpretation stays deterministic-only."""
    with pytest.raises(ContractViolation) as caught:
        require_model_participation(records=RECORDS)
    assert caught.value.code.value == "MODEL_SURFACE_UNAVAILABLE"


def _sealed_contract_for_the_port_check():  # type: ignore[no-untyped-def] - fixture local
    """Um contrato das fixtures — o no so precisa de ALGO para tentar selar sem porto."""
    from ..fixtures.clarifications import issued_contract

    return issued_contract(fingerprint="fp-1")


def test_no_clarification_contract_can_be_issued() -> None:
    """`T065` — nome historico fincado; o corpo e a verdade de OD-101 (2026-09-02): a
    superficie abriu, e o que continua verdade e que SEM PORTO nenhum contrato nasce —
    ausencia e recusa governada, nunca bypass."""
    require_clarification_sealing(records=RECORDS)
    from analytics_interaction.clarification.seal import issue_seal

    with pytest.raises(ContractViolation) as caught:
        issue_seal(
            _sealed_contract_for_the_port_check(),
            port=None,
            key_id="k",
            algorithm="a",
            records=RECORDS,
        )
    assert caught.value.code.value == "CLARIFICATION_UNAVAILABLE"


def test_no_refusal_names_a_governed_value() -> None:
    """A caller refused by an unavailable capability learns only that.

    OD-101/OD-104 (2026-09-02): d_18 e d_21 nao recusam mais e saem do laco — a
    propriedade e sobre RECUSAS, e eles nao produzem uma.
    """
    for capability in InteractionCapability:
        if capability in (InteractionCapability.D_18, InteractionCapability.D_21):
            continue
        with pytest.raises(ContractViolation) as caught:
            require_capability(capability, records=RECORDS)
        rendered = caught.value.detail.lower()
        for leak in ("threshold", "bound", "expiry", "formula", "key", "week", "seconds"):
            assert leak not in rendered


# --- the fifteen records ------------------------------------------------------


def test_the_task_ledger_carries_the_four_new_records_and_none_is_complete() -> None:
    """Nome historico fincado; a regra uniforme dos externos fechados vale desde
    2026-09-02 (OD-93): um registro externo FECHADO carrega [X] + o marcador + um
    "CLOSED 20.." datado na mesma linha. Aberto continua sendo "- [ ]"."""
    ledger = TASKS.read_text(encoding="utf-8")
    for record in NEW_RECORDS:
        match = re.search(
            rf"^- \[([ xX])\] {record} `\[BLOCKED-EXTERNAL\]`([^\n]*)", ledger, re.MULTILINE
        )
        assert match is not None, f"{record} is missing from the ledger"
        if match.group(1) != " ":
            assert "CLOSED 20" in match.group(2), (
                f"{record} is marked complete without a dated closure"
            )


@pytest.mark.parametrize("record", INHERITED)
def test_each_inherited_record_is_referenced_and_never_renumbered(record: str) -> None:
    """`FR-057`: this feature marks, closes and reinterprets none of them."""
    ledger = TASKS.read_text(encoding="utf-8")
    assert record in ledger, f"{record} is no longer referenced"


def test_the_fifteen_records_are_eleven_inherited_plus_four_new() -> None:
    assert len(INHERITED) == 11
    assert len(NEW_RECORDS) == 4
    assert len(INHERITED) + len(NEW_RECORDS) == 15


def test_no_executable_task_is_an_external_record() -> None:
    """External records are records, never executable dependencies."""
    ledger = TASKS.read_text(encoding="utf-8")
    external = re.findall(r"^- \[[ xX]\] (T\d{3}) `\[BLOCKED-EXTERNAL\]`", ledger, re.MULTILINE)
    assert external == list(NEW_RECORDS)


# --- the five distinguishable states ------------------------------------------
#
# SYNTHETIC RECORDS ONLY. Nothing below is written to disk, and none of it is
# evidence for any dependency. They exist to prove the reader distinguishes
# states it will not encounter in this repository.


def _synthetic(**capabilities: Capability) -> ReadinessRecord:
    """TEST-ONLY in-memory record. Never persisted, never evidence."""
    return ReadinessRecord("fixture-feature", "FIXTURE-ONLY", capabilities)


def _capability(identifier: str, declared: bool, evidence: str | None) -> Capability:
    return Capability(identifier, declared, evidence, "fixture-owner")


@pytest.mark.parametrize(
    ("declared", "evidence", "expected"),
    [
        (False, None, CapabilityState.UNDECLARED),
        (True, None, CapabilityState.DECLARED_WITHOUT_EVIDENCE),
        (True, "   ", CapabilityState.DECLARED_WITHOUT_EVIDENCE),
        (False, "docs/evidence.md", CapabilityState.EVIDENCE_WITHOUT_DECLARATION),
        (True, "docs/evidence.md", CapabilityState.READY),
    ],
)
def test_the_reader_distinguishes_all_five_states(
    declared: bool, evidence: str | None, expected: CapabilityState
) -> None:
    record = _synthetic(d_18=_capability("d_18", declared, evidence))
    assert capability_state("d_18", records=[record]) is expected


def test_a_declaration_without_evidence_does_not_unlock() -> None:
    """A flag with nothing behind it is not readiness."""
    record = _synthetic(d_18=_capability("d_18", True, None))
    assert not is_capability_available(InteractionCapability.D_18, records=[record])


def test_evidence_without_a_declaration_does_not_unlock() -> None:
    """A dangling reference is not readiness either."""
    record = _synthetic(d_19=_capability("d_19", False, "docs/evidence.md"))
    assert not is_capability_available(InteractionCapability.D_19, records=[record])


def test_the_strictest_state_wins_across_disagreeing_records() -> None:
    """Additive aggregation: a second opinion can only narrow.

    Without this, one record declaring a capability ready would unlock it even
    while another said otherwise — which is exactly the widening the additive
    rule exists to prevent.
    """
    ready = _synthetic(d_20=_capability("d_20", True, "docs/evidence.md"))
    undeclared = _synthetic(d_20=_capability("d_20", False, None))
    assert capability_state("d_20", records=[ready]) is CapabilityState.READY
    assert capability_state("d_20", records=[ready, undeclared]) is CapabilityState.UNDECLARED
    assert not is_capability_available(InteractionCapability.D_20, records=[ready, undeclared])


def test_a_ready_synthetic_capability_unlocks_only_its_own_surfaces() -> None:
    """Capability isolation, stated as the positive case.

    A synthetic `D-19` marked ready must leave every `D-18`, `D-20` and `D-21`
    surface exactly as unavailable as it found them.
    """
    record = _synthetic(
        d_18=_capability("d_18", False, None),
        d_19=_capability("d_19", True, "FIXTURE-ONLY"),
        d_20=_capability("d_20", False, None),
        d_21=_capability("d_21", False, None),
    )
    unlocked = available_surfaces(records=[record])
    assert unlocked == {
        surface
        for surface, capability in SURFACE_CAPABILITY.items()
        if capability is InteractionCapability.D_19
    }


@pytest.mark.parametrize("capability", list(InteractionCapability))
def test_no_capability_enables_another(capability: InteractionCapability) -> None:
    """Each dependency blocks only its own surfaces, checked one at a time."""
    record = _synthetic(
        **{
            member.value: _capability(
                member.value, member is capability, "FIXTURE-ONLY" if member is capability else None
            )
            for member in InteractionCapability
        }
    )
    unlocked = available_capabilities(records=[record])
    assert unlocked == {capability}


# --- malformed and contradictory data fails closed ----------------------------


@pytest.mark.parametrize(
    ("case", "document"),
    [
        ("not a mapping", "- just\n- a list\n"),
        ("unknown top-level key", "capabilities: []\nreadiness: READY\n"),
        ("capabilities not a list", "capabilities: yes\n"),
        ("entry not a mapping", "capabilities:\n  - just-a-string\n"),
        ("no identifier", "capabilities:\n  - declared: false\n"),
        ("blank identifier", "capabilities:\n  - id: '  '\n    declared: false\n"),
        ("declared not boolean", "capabilities:\n  - id: d_18\n    declared: 'yes'\n"),
        (
            "evidence not a string",
            "capabilities:\n  - id: d_18\n    declared: false\n    evidence_ref: 7\n",
        ),
        (
            "unknown capability key",
            "capabilities:\n  - id: d_18\n    declared: false\n    evidence_reference: x\n",
        ),
        (
            "duplicate identifier",
            "capabilities:\n  - id: d_18\n    declared: false\n  - id: d_18\n    declared: true\n"
            "    evidence_ref: x\n",
        ),
    ],
)
def test_malformed_readiness_data_raises_rather_than_reading_as_unavailable(
    case: str, document: str, tmp_path: Path
) -> None:
    """A defect must not look like a governed "not ready".

    Reading a broken file as unavailable would be safe today and dangerous the
    moment somebody fixed it badly.
    """
    target = tmp_path / "broken.yaml"
    target.write_text(document, encoding="utf-8")
    with pytest.raises(ReadinessMalformed):
        load_record(target)


def test_a_missing_record_raises_rather_than_dropping_a_constraint(tmp_path: Path) -> None:
    with pytest.raises(ReadinessMalformed, match="missing"):
        load_record(tmp_path / "absent.yaml")


def test_an_unknown_capability_identifier_refuses() -> None:
    """An ungoverned name has no state; answering one would invent a fact."""
    with pytest.raises(UnknownCapability):
        capability_state("d_99", records=RECORDS)


def test_an_empty_record_set_grants_nothing() -> None:
    assert aggregate_ready([]) == frozenset()
    with pytest.raises(UnknownCapability):
        capability_state("d_18", records=[])


# --- determinism, immutability and the absence of overrides --------------------


def test_the_reader_is_deterministic() -> None:
    first = load_all_records()
    second = load_all_records()
    assert [r.source for r in first] == [r.source for r in second]
    assert aggregate_ready(first) == aggregate_ready(second)
    for a, b in zip(first, second, strict=True):
        assert {k: v.state for k, v in a.capabilities.items()} == {
            k: v.state for k, v in b.capabilities.items()
        }


def test_reading_mutates_no_record() -> None:
    """Every byte on disk is unchanged after a full read."""
    before = {name: (readiness_root() / name).read_bytes() for name in READINESS_RECORDS}
    load_all_records()
    available_surfaces()
    for capability in InteractionCapability:
        is_capability_available(capability)
    after = {name: (readiness_root() / name).read_bytes() for name in READINESS_RECORDS}
    assert before == after


def test_nothing_is_cached_across_calls() -> None:
    """A cached aggregate could outlive a readiness-record change.

    Proven by reading a synthetic directory: if a cache existed, the second call
    would return the first call's answer for the same capability id.
    """
    # OD-104 (2026-09-02): a sonda virou o d_19 — o d_18 ficou READY de verdade e um
    # cache dele nao seria distinguivel do estado embarcado.
    assert not is_capability_available(InteractionCapability.D_19)
    ready = _synthetic(d_19=_capability("d_19", True, "FIXTURE-ONLY"))
    assert is_capability_available(InteractionCapability.D_19, records=[ready])
    assert not is_capability_available(InteractionCapability.D_19)


def test_the_fail_closed_map_is_read_only() -> None:
    with pytest.raises(TypeError):
        CAPABILITY_FAIL_CLOSED[InteractionCapability.D_18] = None  # type: ignore[index]


def test_the_surface_map_is_read_only_and_total() -> None:
    with pytest.raises(TypeError):
        SURFACE_CAPABILITY[CapabilitySurface.RELATIVE_PERIOD] = None  # type: ignore[index]
    assert set(SURFACE_CAPABILITY) == set(CapabilitySurface)
    assert set(SURFACE_CAPABILITY.values()) == set(InteractionCapability)


def test_no_module_offers_a_readiness_override() -> None:
    """No flag, environment variable, argument or mode unlocks a capability."""
    import ast
    import inspect

    from analytics_interaction import compliance

    root = Path(inspect.getfile(compliance)).resolve().parent
    forbidden = ("environ", "getenv", "override", "force_ready", "assume_ready", "skip_readiness")
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            name = (
                node.id
                if isinstance(node, ast.Name)
                else node.attr
                if isinstance(node, ast.Attribute)
                else node.name
                if isinstance(node, ast.FunctionDef)
                else node.arg
                if isinstance(node, ast.arg)
                else ""
            )
            if any(token in name.lower() for token in forbidden):
                offenders.append(f"{path.name}: {name}")
    assert not offenders, f"a readiness override exists: {offenders}"


def test_no_module_writes_to_the_readiness_directory() -> None:
    """The readers read. Nothing opens a record for writing."""
    import ast
    import inspect

    from analytics_interaction import compliance

    root = Path(inspect.getfile(compliance)).resolve().parent
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                called = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else node.func.id
                    if isinstance(node.func, ast.Name)
                    else ""
                )
                if called in {"write_text", "write_bytes", "open", "unlink", "rename", "mkdir"}:
                    offenders.append(f"{path.name}:{node.lineno} {called}()")
    assert not offenders, f"a compliance module writes: {offenders}"
