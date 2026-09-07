"""Readiness aggregation and the ten locks — T027 (FR-096, FR-097; SC-053, SC-056).

Four claims:

* the four records are read, additively, and a **missing** record is not permission;
* `D-22` to `D-31` are **undeclared with no evidence reference** — the shipped state;
* no inherited record of `001`, `002` or `003` is declared, satisfied or reinterpreted;
* channel enablement is **derived** from the records, so no configuration can enable a
  channel whose credential record is undeclared.

**No test here declares a capability.** The record on disk is read, never written, and
the one test that needs a declared capability builds a synthetic record in a temporary
directory rather than touching the real one.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from channel_integration.compliance.readiness import (
    CHANNEL_CAPABILITIES,
    READINESS_RECORDS,
    Capability,
    CapabilityState,
    ReadinessMalformed,
    UnknownCapability,
    aggregate_ready,
    capabilities_in_own_record,
    capability_state,
    channel_enabled,
    descriptor_with_derived_enablement,
    load_all_records,
    readiness_root,
)
from channel_integration.contracts import ChannelDescriptor, ChannelId, CredentialRecord

pytestmark = pytest.mark.contract


def test_four_records_are_named_not_globbed() -> None:
    """A file appearing in the directory must not silently join the conjunction."""
    assert READINESS_RECORDS == (
        "external-readiness.yaml",
        "analytics-query-external-readiness.yaml",
        "nl-analytics-external-readiness.yaml",
        "multichannel-external-readiness.yaml",
    )
    for name in READINESS_RECORDS:
        assert (readiness_root() / name).is_file(), f"{name} must exist to be read"


#: The one capability the owner declared, and the reason it is named rather than counted.
#:
#: **RE-DERIVED on 2026-08-28, not deleted** -- `FR-818`. This file asserted that EVERY channel
#: capability was undeclared, which was true and stopped being true: `OD-18` signed `d_24` and
#: `OD-20-A` applied it to SENDING while the inbound door stays shut. A node deleted here would
#: be a property that stopped being checked while the ledger still claimed it.
DECLARED_BY_THE_OWNER = "d_24"
#: OD-91 (2026-09-02, clique dele na recomendada): o d_34 foi declarado com a emenda
#: OD-87 verde (runbook + registro + no dos 90 dias + S-32). O conjunto substitui o
#: singular nos nos que contavam UM; um TERCEIRO continua falhando.
DECLARED_SET = ("d_24", "d_34")


def test_every_channel_capability_except_the_declared_one_is_undeclared() -> None:
    """The shipped state, asserted per capability so a single flip is visible.

    **And the flip that happened is asserted too**, in `test_the_declared_one_is_signed`
    below: a node that merely excused `d_24` would stop measuring it.
    """
    capabilities = load_all_records()
    # OD-91 (2026-09-02): d_34 entrou para o conjunto declarado; o resto segue fechado.
    for identifier in CHANNEL_CAPABILITIES:
        if identifier in DECLARED_SET:
            continue
        capability = capabilities[identifier]
        assert capability.declared is False, f"{identifier} is declared"
        assert capability.evidence_ref is None, f"{identifier} names evidence"
        assert capability.state is CapabilityState.UNDECLARED


def test_the_declared_one_is_signed_and_evidenced() -> None:
    """**The other half of the re-derivation.** A declaration is not a flag.

    `001` has required this since the beginning -- *readiness is named evidence signed by a
    permitted role* -- and this reader learned it the day the first record was declared.
    """
    capability = load_all_records()[DECLARED_BY_THE_OWNER]
    assert capability.declared is True
    assert capability.evidence_ref, f"{DECLARED_BY_THE_OWNER} is declared with no evidence"
    assert capability.declared_by_role, f"{DECLARED_BY_THE_OWNER} is declared by nobody"
    assert capability.state is CapabilityState.READY


def test_the_channel_locks_are_exactly_these() -> None:
    """The enumeration and this feature's own record must name **the same set**.

    ## The promise this node made and did not keep

    Its docstring said adding a record to the directory without listing it in
    `CHANNEL_CAPABILITIES` *fails here*. **It did not.** The assertion was
    ``set(CHANNEL_CAPABILITIES) <= set(capabilities)`` — a SUBSET, so an extra record in the
    file passed in silence.

    **`d_34` was the living proof**: created 2026-08-28 under `OD-17`, in this feature's own
    file, never listed, and this node stayed green. The consequence the old docstring named
    is exactly what happened — *a lock that reads as present and is not*.

    Compared as an EQUALITY now, and against **this feature's own file** rather than against
    the merged four: an extra record fails, and a record that vanished from the file fails
    too. Both directions, which is why the tuple stays hand-written — deriving it would make
    this one reading of one file compared with itself.
    """
    own = set(capabilities_in_own_record())
    listed = set(CHANNEL_CAPABILITIES)
    assert listed == own, (
        f"the enumeration and the record disagree: {sorted(listed - own)} are named and absent "
        f"from the file, {sorted(own - listed)} are in the file and govern nothing"
    )

    #: Every one of them must also survive the merge, or the enumeration names something the
    #: aggregator cannot see.
    merged = set(load_all_records())
    assert listed <= merged, f"{sorted(listed - merged)} are named and unreachable"


def test_the_equality_would_catch_a_decorative_record() -> None:
    """**Proof it bites**, and the shape the reviewer's mutation takes.

    A record added to the file and left out of the tuple governs nothing while reading as
    governed. The old subset assertion could not see it; this one is fed the same situation
    and must.
    """
    own = set(capabilities_in_own_record())
    decorative = own | {"d_99_decorative"}
    assert set(CHANNEL_CAPABILITIES) != decorative, (
        "the comparison accepts a record the enumeration does not name"
    )
    assert set(CHANNEL_CAPABILITIES) != own - {"d_34"}, (
        "the comparison accepts an enumeration that lost an entry the file still has"
    )


def test_only_the_declared_capability_is_ready() -> None:
    """Aggregated external readiness is ONE capability, and it is named.

    **RE-DERIVED, not deleted.** It asserted NONE was ready, which held until `OD-18`;
    depois UM (d_24). Emendado no ciclo 501 (2026-09-01, OD-86): o dono declarou o d_15 no
    registro do 002 — DOIS prontos, cada um com a sua assinatura nomeada. Contar em vez de
    excusar segue sendo a propriedade: um TERCEIRO falha aqui.
    """
    ready = sorted(
        identifier for identifier, capability in load_all_records().items() if capability.ready
    )
    # OD-91..106 (2026-09-03): DOZE prontos nomeados; um DECIMO TERCEIRO falha aqui.
    named = ["d_1", "d_2", "d_10", "ext_a", "ext_b", "d_14", "d_15", "d_16", "d_18", "d_21"]
    assert ready == sorted([*named, *DECLARED_SET]), (
        f"{ready} read as ready; exactly twelve capabilities were declared and signed "
        "(d_24 OD-18, d_15 OD-86, d_34 OD-91, d_14 OD-94, d_16 OD-97, d_1 OD-99, d_2 OD-100, "
        "d_21 OD-101, d_18 OD-104, d_10 e ext_b OD-103, ext_a OD-106)"
    )


def test_no_inherited_record_is_touched_by_this_feature() -> None:
    """`001`, `002` and `003` capabilities stay exactly as their owners left them.

    ## Inherited means ANOTHER FILE, and it did not

    It meant *absent from `CHANNEL_CAPABILITIES`*, which is a different set — and on
    2026-08-28 `d_34` fell into it. It passed only because it is `UNDECLARED`, and **the day
    the owner declares managed custody this node would have gone red saying another
    feature's record was touched**: false, and false in the direction that sends a reader
    looking in the wrong place.

    Provenance is a fact about the file, so it is read from the file.

    Emendado no ciclo 501 (2026-09-01, OD-86): o DONO do d_15 (registro do 002) o declarou
    — herdado mudou porque o dono dele mudou, que e exatamente o que este no distingue de
    "este feature tocou". A excecao e UMA, nomeada, e qualquer outra herdada declarada
    continua falhando aqui.
    """
    capabilities = load_all_records()
    own = set(capabilities_in_own_record())
    inherited = [identifier for identifier in capabilities if identifier not in own]
    assert inherited, "the inherited records must contribute capabilities"
    assert not (set(inherited) & set(CHANNEL_CAPABILITIES)), (
        f"{sorted(set(inherited) & set(CHANNEL_CAPABILITIES))} are named by this feature and "
        f"counted as inherited; a record of ours in that bucket accuses the wrong owner"
    )
    for identifier in inherited:
        herdados_declarados = {
            "d_1",
            "d_2",
            "d_10",
            "ext_a",
            "ext_b",
            "d_14",
            "d_15",
            "d_16",
            "d_18",
            "d_21",
        }
        if identifier in herdados_declarados:  # OD-86..105 + OD-103
            assert capabilities[identifier].state is CapabilityState.READY, (
                f"{identifier} foi declarado pelo dono do registro dele (001/002/003) e "
                "este no o le do arquivo desse dono"
            )
            continue
        assert capabilities[identifier].state is CapabilityState.UNDECLARED


@pytest.mark.parametrize("channel", list(ChannelId))
def test_only_the_authorized_channel_may_send_and_none_may_receive(channel: ChannelId) -> None:
    """**RE-DERIVED for the split key**, and it now asserts BOTH halves per channel.

    `OD-20-A`: *may a message arrive* and *may a message be sent* are two questions. His
    2026-08-18 rule stands in full for what arrives -- no channel may receive, because
    Telegram and WhatsApp sign no instant and the other two have undeclared records -- and
    exactly one channel may send.
    """
    from channel_integration.compliance.readiness import may_receive_from, may_send_to

    expected = channel is ChannelId.TELEGRAM
    assert channel_enabled(channel) is expected
    assert may_send_to(channel) is expected
    assert may_receive_from(channel) is False, (
        f"{channel.value} may RECEIVE; the 2026-08-18 decision forbids that until a governed "
        f"cross-process store exists, and OD-20-A split the key rather than weakening it"
    )


def test_enablement_is_derived_and_cannot_be_asserted_by_a_descriptor() -> None:
    """A descriptor claiming ``enabled=True`` is overruled by the record."""
    claimed = ChannelDescriptor(
        channel=ChannelId.SLACK,
        verification_scheme="slack-v0",
        credential_record=CredentialRecord.D_23_SLACK,
        enabled=True,
    )
    derived = descriptor_with_derived_enablement(claimed)
    assert derived.enabled is False


def test_a_descriptor_gated_by_the_wrong_record_is_malformed() -> None:
    """A channel must not be enableable by another channel's lock."""
    with pytest.raises(ReadinessMalformed):
        descriptor_with_derived_enablement(
            ChannelDescriptor(
                channel=ChannelId.SLACK,
                verification_scheme="slack-v0",
                credential_record=CredentialRecord.D_22_WHATSAPP,
            )
        )


def test_an_unknown_capability_raises_rather_than_reading_as_unavailable() -> None:
    """ "Unavailable" is a statement about a governed capability; a name nobody governs
    has no state to report, and answering "not ready" would invent one."""
    with pytest.raises(UnknownCapability):
        capability_state("d_99")
    with pytest.raises(UnknownCapability):
        aggregate_ready(["d_99"])


def test_a_declaration_without_evidence_never_unlocks() -> None:
    """The two invalid middles are distinguished and neither is readiness."""
    declared_only = Capability("d_22", declared=True, evidence_ref=None, owner_role="platform")
    assert declared_only.state is CapabilityState.DECLARED_WITHOUT_EVIDENCE
    assert not declared_only.ready

    evidence_only = Capability("d_22", declared=False, evidence_ref="ref", owner_role="platform")
    assert evidence_only.state is CapabilityState.EVIDENCE_WITHOUT_DECLARATION
    assert not evidence_only.ready

    both = Capability("d_22", declared=True, evidence_ref="ref", owner_role="platform")
    assert both.state is CapabilityState.READY


def test_a_missing_record_is_not_permission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The load-bearing rule: absence narrows, never widens.

    Driven against a synthetic directory so the real records are never touched.
    """
    from channel_integration.compliance import readiness as module

    (tmp_path / "external-readiness.yaml").write_text(
        yaml.safe_dump({"capabilities": [{"capability": "d_1", "declared": False}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "readiness_root", lambda: tmp_path)
    with pytest.raises(ReadinessMalformed, match="not permission"):
        module.load_all_records()


def test_a_duplicate_capability_across_records_is_malformed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two records declaring one capability would make readiness depend on read order."""
    from channel_integration.compliance import readiness as module

    for name in READINESS_RECORDS:
        (tmp_path / name).write_text(
            yaml.safe_dump({"capabilities": [{"id": "d_26", "declared": False}]}),
            encoding="utf-8",
        )
    monkeypatch.setattr(module, "readiness_root", lambda: tmp_path)
    with pytest.raises(ReadinessMalformed, match="more than one record"):
        module.load_all_records()


def test_a_malformed_record_raises_rather_than_reading_as_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A defect must not look like a governed "not ready"."""
    from channel_integration.compliance import readiness as module

    for name in READINESS_RECORDS:
        (tmp_path / name).write_text(
            yaml.safe_dump({"capabilities": [{"id": "d_26", "declared": "yes"}]}),
            encoding="utf-8",
        )
    monkeypatch.setattr(module, "readiness_root", lambda: tmp_path)
    with pytest.raises(ReadinessMalformed, match="not a boolean"):
        module.load_all_records()


def test_nothing_here_can_write_a_record() -> None:
    """The module reads. No write path exists, asserted by source inspection."""
    source = Path(module_path()).read_text(encoding="utf-8")
    for forbidden in ("write_text(", "safe_dump(", "open(", '"w"', "'w'"):
        assert forbidden not in source, f"the readiness reader contains {forbidden}"


def module_path() -> str:
    from channel_integration.compliance import readiness as module

    assert module.__file__ is not None
    return module.__file__
