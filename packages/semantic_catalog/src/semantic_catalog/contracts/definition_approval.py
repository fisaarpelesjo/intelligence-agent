"""Definition approvals — o cofre de assinaturas do D-2 (ciclo 525, 2026-09-02).

O molde é o do frescor (T113, inteiro): a aprovação RESTATES a definição decidida, é
assinada por papel distinto do autor, é presa ao commit do conteúdo que aprova
(``metric_commit``) e é avaliada por um caminho PÚBLICO — ``evaluate`` — cujas únicas
saídas são "aprovada como escrita" e uma recusa nomeada. Nenhum ramo devolve default,
conserto ou aproximação.

O que isto NÃO é: uma regra de permissão. O D-28 segue regra de verdade — a aprovação
registra a PALAVRA DO DONO (OD-100 e sucessoras), e um contrato cuja definição mudou
depois da assinatura lê ``DEFINITION_CHANGED`` até alguém reassinar.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import Field, model_validator

from semantic_catalog.contracts._base import CatalogModel, Identifier, PtBrText


class DefinitionDenial(StrEnum):
    """Por que uma definição NÃO está aprovada. Cada valor nomeia o remédio."""

    NO_APPROVAL = "no_approval"
    ROLE_NOT_PERMITTED = "role_not_permitted"
    COMMIT_MISMATCH = "commit_mismatch"
    DEFINITION_CHANGED = "definition_changed"


def _covers(approved: str, actual: str | None) -> bool:
    """Prefixo, como no frescor: a assinatura curta cobre o sha longo do mesmo commit."""
    if actual is None or not approved:
        return False
    menor, maior = sorted((approved, actual), key=len)
    return maior.startswith(menor)


def _normalised(text: str) -> str:
    """Folded scalars dobram linhas; a comparação é sobre as palavras, não o wrap."""
    return " ".join(text.split())


class DefinitionApproval(CatalogModel):
    """Uma definição de métrica assinada — restated, datada, presa ao commit."""

    metric_id: Identifier
    #: A definição decidida, RESTATED verbatim (normalizada por espaços) — tem que ser a
    #: mesma frase que vive no limitations do contrato da métrica, senão DEFINITION_CHANGED.
    decided_definition: PtBrText
    #: A ordem do dono que decidiu (ex.: OD-100). Citação, nunca inferência — o formato
    #: e o das ordens (OD-<n>), nao o dos identificadores do catalogo.
    decision_ref: str = Field(pattern=r"^OD-[0-9]+$")
    approved_by_role: Identifier = Field(
        description="Papel distinto do autor do contrato; o catalog-policy diz quem pode."
    )
    approved_at: date
    metric_commit: str = Field(min_length=7, description="Prende a aprovacao ao conteudo aprovado.")
    limitations: tuple[PtBrText, ...] = ()


class DefinitionApprovalRegistry(CatalogModel):
    """O cofre. Uma aprovação por métrica; avaliação pública; recusas nomeadas."""

    kind: str = Field(pattern="^definition_approvals$")
    catalog_schema_version: int
    approvals: tuple[DefinitionApproval, ...] = ()

    @model_validator(mode="after")
    def _one_approval_per_metric(self) -> DefinitionApprovalRegistry:
        vistos: set[str] = set()
        for entrada in self.approvals:
            if entrada.metric_id in vistos:
                raise ValueError(
                    f"duas aprovacoes para {entrada.metric_id!r}; a segunda esconderia a primeira"
                )
            vistos.add(entrada.metric_id)
        return self

    def get(self, metric_id: str) -> DefinitionApproval | None:
        for entrada in self.approvals:
            if entrada.metric_id == metric_id:
                return entrada
        return None

    def evaluate(
        self,
        metric_id: str,
        *,
        current_definition: str,
        metric_content_commit: str | None,
        permitted_roles: frozenset[str] | None = None,
    ) -> DefinitionDenial | None:
        """``None`` = aprovada como escrita; senão a recusa mais acionável, em ordem."""
        approval = self.get(metric_id)
        if approval is None:
            return DefinitionDenial.NO_APPROVAL
        if permitted_roles is not None and approval.approved_by_role not in permitted_roles:
            return DefinitionDenial.ROLE_NOT_PERMITTED
        if not _covers(approval.metric_commit, metric_content_commit):
            return DefinitionDenial.COMMIT_MISMATCH
        if _normalised(approval.decided_definition) != _normalised(current_definition):
            return DefinitionDenial.DEFINITION_CHANGED
        return None
