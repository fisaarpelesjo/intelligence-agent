"""O cofre do D-2 avaliado pelo caminho público, contra os artefatos REAIS — ciclo 525.

Cada métrica decidida (OD-100) tem aprovação que RESTATES a definição e cobre o commit
ATUAL do contrato; as recusas são dirigidas uma a uma em cópias (sem aprovação; commit
velho; definição mudada; papel de fora). O mesmo git do CLI resolve o commit.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from semantic_catalog.contracts.definition_approval import (
    DefinitionApprovalRegistry,
    DefinitionDenial,
)

pytestmark = pytest.mark.contract

REPO = Path(__file__).resolve().parents[4]
VAULT = REPO / "semantic" / "governance" / "definition-approvals.yaml"
POLICY = REPO / "semantic" / "policies" / "catalog-policy.yaml"
MET = REPO / "semantic" / "metrics"


def _vault_raw() -> dict[str, Any]:
    return cast("dict[str, Any]", yaml.safe_load(VAULT.read_text(encoding="utf-8")))


def _vault() -> DefinitionApprovalRegistry:
    return DefinitionApprovalRegistry.model_validate(_vault_raw())


def _current_definition(metric_id: str) -> str:
    doc = cast(
        "dict[str, Any]", yaml.safe_load((MET / f"{metric_id}.yaml").read_text(encoding="utf-8"))
    )
    versao = cast("dict[str, Any]", cast("list[Any]", doc["versions"])[0])
    limitacoes = cast("list[str]", cast("dict[str, Any]", versao["content"])["limitations"])
    return str(limitacoes[0])


def _commit_of(metric_id: str) -> str:
    out = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", f"semantic/metrics/{metric_id}.yaml"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert len(out) == 40
    return out


def _permitted_roles() -> frozenset[str]:
    policy = cast("dict[str, Any]", yaml.safe_load(POLICY.read_text(encoding="utf-8")))
    return frozenset(cast("list[str]", policy["approval_roles"]))


def test_every_decided_definition_is_approved_at_the_current_commit() -> None:
    """As 19, uma a uma, pelo evaluate — qualquer divergência falha nomeando a métrica."""
    vault = _vault()
    roles = _permitted_roles()
    assert len(vault.approvals) == 19, "o cofre deveria carregar exatamente as 19 do OD-100"
    recusas: list[str] = []
    for approval in vault.approvals:
        denial = vault.evaluate(
            approval.metric_id,
            current_definition=_current_definition(approval.metric_id),
            metric_content_commit=_commit_of(approval.metric_id),
            permitted_roles=roles,
        )
        if denial is not None:
            recusas.append(f"{approval.metric_id}: {denial}")
    assert not recusas, "\n".join(recusas)


def test_a_metric_without_approval_is_refused() -> None:
    """Dirigida: uma das 19 removida em cópia = NO_APPROVAL nomeado."""
    raw = _vault_raw()
    aprovacoes = cast("list[dict[str, Any]]", raw["approvals"])
    removida = aprovacoes.pop(0)
    copia = DefinitionApprovalRegistry.model_validate(raw)
    metric_id = str(removida["metric_id"])
    assert (
        copia.evaluate(
            metric_id,
            current_definition=_current_definition(metric_id),
            metric_content_commit=_commit_of(metric_id),
        )
        is DefinitionDenial.NO_APPROVAL
    )


def test_a_stale_commit_in_a_copy_lights_up() -> None:
    """Dirigida: assinatura presa a commit velho = COMMIT_MISMATCH (a lição do frescor)."""
    raw = _vault_raw()
    entrada = cast("list[dict[str, Any]]", raw["approvals"])[0]
    entrada["metric_commit"] = "7c5e577"
    copia = DefinitionApprovalRegistry.model_validate(raw)
    metric_id = str(entrada["metric_id"])
    assert (
        copia.evaluate(
            metric_id,
            current_definition=_current_definition(metric_id),
            metric_content_commit=_commit_of(metric_id),
        )
        is DefinitionDenial.COMMIT_MISMATCH
    )


def test_a_rewritten_definition_lights_up() -> None:
    """Dirigida: o contrato diz outra frase = DEFINITION_CHANGED — reassinar é ato do dono."""
    vault = _vault()
    metric_id = vault.approvals[0].metric_id
    assert (
        vault.evaluate(
            metric_id,
            current_definition="uma frase que ninguem assinou",
            metric_content_commit=_commit_of(metric_id),
        )
        is DefinitionDenial.DEFINITION_CHANGED
    )


def test_a_role_outside_the_policy_is_refused() -> None:
    """Dirigida: papel de fora do catalog-policy = ROLE_NOT_PERMITTED."""
    raw = _vault_raw()
    entrada = cast("list[dict[str, Any]]", raw["approvals"])[0]
    entrada["approved_by_role"] = "engineering"
    copia = DefinitionApprovalRegistry.model_validate(raw)
    metric_id = str(entrada["metric_id"])
    assert (
        copia.evaluate(
            metric_id,
            current_definition=_current_definition(metric_id),
            metric_content_commit=_commit_of(metric_id),
            permitted_roles=_permitted_roles(),
        )
        is DefinitionDenial.ROLE_NOT_PERMITTED
    )


def test_a_text_change_lights_definition_changed_and_never_commit_mismatch() -> None:
    """S-39 (2026-09-03, ciclo 542) — **a condição da autorização do re-vínculo.**

    A re-estampagem dos `metric_commit` no OD-106 foi permitida porque o TEXTO das 19 era
    byte-idêntico, e o contrato distingue as duas recusas. Este nó prova que a distinção
    SOBREVIVE à re-estampagem: mudar o texto de uma definição em cópia acende
    `definition_changed` — nunca `commit_mismatch` — mesmo com o commit em dia. Sem ele, a
    re-vinculação seria um caminho para lavar mudança semântica no futuro.
    """
    vault = _vault()
    for approval in vault.approvals:
        metric_id = approval.metric_id
        commit = _commit_of(metric_id)
        # o commit ESTA em dia (a re-vinculacao acabou de acontecer): a unica recusa
        # possivel e a do texto.
        assert (
            vault.evaluate(
                metric_id,
                current_definition=_current_definition(metric_id),
                metric_content_commit=commit,
                permitted_roles=_permitted_roles(),
            )
            is None
        ), metric_id
        adulterado = _current_definition(metric_id) + " (uma frase que ninguem assinou)"
        denial = vault.evaluate(
            metric_id,
            current_definition=adulterado,
            metric_content_commit=commit,
            permitted_roles=_permitted_roles(),
        )
        assert denial is DefinitionDenial.DEFINITION_CHANGED, (metric_id, denial)


def test_two_approvals_for_one_metric_refuse_to_construct() -> None:
    """O cofre nem constrói com duplicata — a segunda esconderia a primeira."""
    raw = _vault_raw()
    aprovacoes = cast("list[dict[str, Any]]", raw["approvals"])
    aprovacoes.append(dict(aprovacoes[0]))
    with pytest.raises(Exception, match="duas aprovacoes"):
        DefinitionApprovalRegistry.model_validate(raw)
