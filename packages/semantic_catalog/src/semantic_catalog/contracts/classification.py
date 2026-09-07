"""Authoritative field classification — T021 (FR-033).

Every authored field of every contract is assigned **exactly one** of six classes.
The map is the executable form of
`specs/001-semantic-catalog/contracts/catalog-file-contracts.md §4.4`, and
:func:`verify_exhaustive` proves at test time that no model field is unassigned,
double-assigned or assigned to a field that does not exist.

Why this matters more than it looks: the semantic fingerprint (T086) is computed
over "Semantic-class fields". If that set were ambiguous, the gate protecting
SC-021 would be protecting an undefined set of things.

**Fingerprint inputs are closed**: every ``Semantic`` field, plus the three
``Lifecycle`` fields that alter as-of resolution — ``version``,
``effective_from``, ``effective_to`` on a metric version. Editing those silently
reassigns which definition answers which period, which changes historical
answers without touching a calculation. ``restatements`` is Lifecycle but is
**not** fingerprinted: it moves the data revision, not the definition.

This map and the published table are kept identical by
``test_published_table_matches_executable_map``, which parses the Markdown and
fails on any missing, stale, duplicated or differently classified field.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from pydantic import BaseModel

from . import (
    access_tag,
    approval,
    comparability,
    dimension,
    freshness_approval,
    glossary,
    metric,
    owner,
    policy,
    reason_message,
    retention,
    source,
)
from ._base import CatalogModel

__all__ = [
    "CLASSIFICATION",
    "FINGERPRINT_INPUTS",
    "FieldClass",
    "UnclassifiedFieldError",
    "class_of",
    "fields_in_class",
    "is_fingerprinted",
    "model_field_paths",
    "verify_exhaustive",
]


class UnclassifiedFieldError(LookupError):
    """A field has no classification. Never defaulted — the map must be complete."""


class FieldClass(StrEnum):
    """The six approved classes. See catalog-file-contracts.md §4.4.

    ``semantic_fingerprint`` is deliberately absent: it is computed from the
    fields below and is never authored, so it is not a classifiable field.
    """

    STABLE_IDENTITY = "stable_identity"
    SEMANTIC = "semantic"
    DESCRIPTIVE = "descriptive"
    AVAILABILITY = "availability"
    LIFECYCLE = "lifecycle"
    GOVERNANCE = "governance"


_S = FieldClass.STABLE_IDENTITY
_SEM = FieldClass.SEMANTIC
_D = FieldClass.DESCRIPTIVE
_A = FieldClass.AVAILABILITY
_L = FieldClass.LIFECYCLE
_G = FieldClass.GOVERNANCE

#: Every model whose fields are authored catalog content. Keyed by model name so
#: the map reads as ``Model.field``.
_AUTHORED_MODELS: tuple[type[CatalogModel], ...] = (
    owner.Owner,
    owner.OwnerRegistry,
    source.Outage,
    source.Restatement,
    source.SourceContent,
    source.Source,
    dimension.Synonym,
    dimension.SourceApplicability,
    dimension.DimensionContent,
    dimension.Dimension,
    comparability.ComparabilityContent,
    comparability.ComparabilityRule,
    glossary.GlossaryContent,
    glossary.GlossaryTerm,
    retention.RetentionContract,
    metric.MetricContent,
    metric.MetricVersion,
    metric.SourceAvailability,
    metric.Deprecation,
    metric.Metric,
    policy.AuthorizationRules,
    policy.PublicationRules,
    policy.PendingVisibilityRules,
    policy.RefusalRules,
    policy.CatalogPolicy,
    policy.PolicySet,
    access_tag.AccessTagContent,
    access_tag.AccessTag,
    access_tag.AccessTagRegistry,
    reason_message.ReasonMessage,
    reason_message.ReasonMessageRegistry,
    approval.PendingVisibilityApproval,
    approval.PendingVisibilityApprovals,
    freshness_approval.FreshnessApproval,
    freshness_approval.FreshnessApprovalRegistry,
)

_MAP: dict[str, FieldClass] = {
    # --- shared, inherited from CatalogModel / PtBrContent --------------------
    # `catalog_schema_version` and `kind` are Stable Identity on every root
    # contract; `lang` is the pt-BR content marker and is Descriptive.
    # --- owners registry -----------------------------------------------------
    "Owner.id": _S,
    "Owner.name": _G,
    "Owner.kind": _G,
    "Owner.review_group": _G,
    "OwnerRegistry.catalog_schema_version": _S,
    "OwnerRegistry.kind": _S,
    "OwnerRegistry.owners": _G,
    # --- source --------------------------------------------------------------
    "Outage.from_date": _A,
    "Outage.to_date": _A,
    "Outage.reason": _D,
    "Restatement.restated_at": _L,
    "Restatement.affects_from": _L,
    "Restatement.affects_to": _L,
    "Restatement.reason": _D,
    "SourceContent.lang": _D,
    "SourceContent.label": _D,
    "SourceContent.limitations": _D,
    "Source.catalog_schema_version": _S,
    "Source.kind": _S,
    "Source.id": _S,
    "Source.type": _S,
    "Source.product": _S,
    "Source.platform": _S,
    "Source.store": _S,
    "Source.reporting_timezone": _SEM,
    "Source.earliest_available_date": _A,
    "Source.expected_refresh_interval": _SEM,
    "Source.delay_tolerance": _SEM,
    "Source.owner": _G,
    "Source.content": _D,
    "Source.outages": _A,
    "Source.restatements": _L,
    # --- dimension -----------------------------------------------------------
    "Synonym.text": _D,
    "Synonym.kind": _D,
    "SourceApplicability.source": _A,
    "SourceApplicability.available_from": _A,
    "SourceApplicability.available_to": _A,
    "DimensionContent.lang": _D,
    "DimensionContent.label": _D,
    "DimensionContent.description": _D,
    "Dimension.catalog_schema_version": _S,
    "Dimension.kind": _S,
    "Dimension.id": _S,
    "Dimension.owner": _G,
    # ADR 0029. The same class `Metric.access` carries: an access tag governs whether a concept
    # is available to a principal, which is what `AVAILABILITY` means here. Following the existing
    # precedent for an identical field rather than choosing a class for it.
    "Dimension.access": _A,
    "Dimension.permitted_values": _SEM,
    "Dimension.content": _D,
    "Dimension.source_applicability": _A,
    "Dimension.synonyms": _D,
    # --- comparability -------------------------------------------------------
    "ComparabilityContent.lang": _D,
    "ComparabilityContent.reason": _D,
    "ComparabilityContent.caveat": _D,
    "ComparabilityRule.catalog_schema_version": _S,
    "ComparabilityRule.kind": _S,
    "ComparabilityRule.id": _S,
    "ComparabilityRule.subject": _S,
    "ComparabilityRule.left": _S,
    "ComparabilityRule.right": _S,
    "ComparabilityRule.relation": _SEM,
    "ComparabilityRule.content": _D,
    # --- glossary ------------------------------------------------------------
    "GlossaryContent.lang": _D,
    "GlossaryContent.term": _D,
    "GlossaryContent.definition": _D,
    "GlossaryTerm.catalog_schema_version": _S,
    "GlossaryTerm.kind": _S,
    "GlossaryTerm.id": _S,
    "GlossaryTerm.owner": _G,
    "GlossaryTerm.content": _D,
    "GlossaryTerm.synonyms": _D,
    # --- retention -----------------------------------------------------------
    "RetentionContract.window_days": _SEM,
    "RetentionContract.retention_style": _SEM,
    "RetentionContract.cohort_assignment": _SEM,
    "RetentionContract.cohort_timezone": _SEM,
    "RetentionContract.eligible_event": _SEM,
    "RetentionContract.identity_rule": _SEM,
    "RetentionContract.numerator": _SEM,
    "RetentionContract.denominator": _SEM,
    "RetentionContract.min_maturity_days": _SEM,
    # --- metric --------------------------------------------------------------
    "MetricContent.lang": _D,
    "MetricContent.label": _D,
    "MetricContent.description": _D,
    "MetricContent.limitations": _D,
    "MetricVersion.version": _L,
    "MetricVersion.effective_from": _L,
    "MetricVersion.effective_to": _L,
    "MetricVersion.source_view": _SEM,
    "MetricVersion.grain": _SEM,
    "MetricVersion.aggregation": _SEM,
    "MetricVersion.additivity": _SEM,
    "MetricVersion.unit": _SEM,
    "MetricVersion.time_dimension": _SEM,
    "MetricVersion.numerator": _SEM,
    "MetricVersion.denominator": _SEM,
    "MetricVersion.calculation_basis": _SEM,
    # SEMANTICOS OS DOIS, e nao e escolha de gosto: `kpi_name` diz QUAL LINHA da view este
    # contrato e, e `value_column` diz QUAL COLUNA carrega o numero. Mudar um dos dois muda o
    # numero que o KPI reporta -- que e a definicao de semantico aqui. Classificar
    # `value_column` como descritivo deixaria a correcao do erro publicado (MRR e Revenue
    # lidos como sem valor) entrar sem bloco de versao novo.
    "MetricVersion.kpi_name": _SEM,
    "MetricVersion.value_column": _SEM,
    "MetricVersion.exclusions": _SEM,
    "MetricVersion.allowed_dimensions": _A,
    # `D-1303`, e a classificacao foi MEDIDA em vez de escolhida no papel.
    #
    # Semantica e a leitura tentadora: inverter a polaridade inverte a COR de toda a serie
    # sem um numero se mexer, e o leitor passa a ler o contrario do que leu ontem. Escrevi
    # `_SEM` primeiro por isso -- e entao rodei o portao de versao e medi o custo: `diff`
    # contra a main exigiu BLOCO DE VERSAO NOVO nas VINTE metricas ligadas a view, so para
    # declarar uma direcao que a view ja dizia e que ninguem estava mudando.
    #
    # Vinte blocos de versao novos alteram a resposta historica de vinte metricas ("uma
    # versao por data") para registrar um preenchimento. DECLARAR pela primeira vez nao e
    # MUDAR, e o portao nao distingue as duas.
    #
    # Entao: descritiva, com o risco coberto por instrumento em vez de por classificacao --
    # um no afirma que a direcao declarada no contrato e a mesma que a view carrega, e uma
    # inversao silenciosa acende ali. E ESCALADO ao REVIEWER no handoff: se ele preferir o
    # custo dos vinte blocos, a troca e uma linha aqui.
    "MetricVersion.lower_is_better": _D,
    "MetricVersion.content": _D,
    "SourceAvailability.source": _A,
    "SourceAvailability.status": _A,
    "SourceAvailability.effective_from": _A,
    "SourceAvailability.available_from": _A,
    "SourceAvailability.reason_code": _A,
    "SourceAvailability.reversible": _A,
    "SourceAvailability.review_trigger": _A,
    # OD-106 (2026-09-03): a semantica deslizante e conteudo autorado como os vizinhos.
    "SourceAvailability.sliding": _A,
    "Deprecation.deprecated_from": _L,
    "Deprecation.successor": _L,
    "Deprecation.replacement_metric_id": _L,
    "Deprecation.content": _D,
    "Metric.catalog_schema_version": _S,
    "Metric.kind": _S,
    "Metric.name": _S,
    "Metric.owner": _G,
    "Metric.access": _A,
    "Metric.grain_family": _SEM,
    "Metric.versions": _L,
    "Metric.source_availability": _A,
    "Metric.synonyms": _D,
    "Metric.deprecation": _L,
    "Metric.retention": _SEM,
    # --- catalog policy ------------------------------------------------------
    "AuthorizationRules.default": _G,
    "AuthorizationRules.require_access_tag": _G,
    "AuthorizationRules.unknown_tag_behaviour": _G,
    "AuthorizationRules.self_approval_allowed": _G,
    "PublicationRules.require_complete_contract": _G,
    "PublicationRules.require_owner": _G,
    "PublicationRules.require_pt_br_content": _G,
    "PublicationRules.require_reason_message_for_publishable_codes": _G,
    "PendingVisibilityRules.exposable_fields": _G,
    "PendingVisibilityRules.require_visibility_approval": _G,
    "PendingVisibilityRules.approval_expiry_behaviour": _G,
    "RefusalRules.disclose_answerable_subset": _G,
    "RefusalRules.disclose_replacement_metric_id": _G,
    "CatalogPolicy.catalog_schema_version": _S,
    "CatalogPolicy.kind": _S,
    "CatalogPolicy.policy_id": _G,
    "CatalogPolicy.policy_version": _G,
    "CatalogPolicy.supersedes_version": _G,
    "CatalogPolicy.effective_from": _L,
    "CatalogPolicy.owner_role": _G,
    "CatalogPolicy.approval_roles": _G,
    "CatalogPolicy.authorization": _G,
    "CatalogPolicy.publication": _G,
    "CatalogPolicy.pending_visibility": _G,
    "CatalogPolicy.refusal": _G,
    "PolicySet.policies": _G,
    # --- access tags ---------------------------------------------------------
    "AccessTagContent.lang": _D,
    "AccessTagContent.label": _D,
    "AccessTagContent.description": _D,
    "AccessTag.id": _S,
    "AccessTag.owner_role": _G,
    "AccessTag.effective_from": _L,
    "AccessTag.deprecated_from": _L,
    "AccessTag.replacement_tag": _L,
    "AccessTag.allowed_principal_types": _G,
    "AccessTag.allowed_authorization_scopes": _G,
    "AccessTag.content": _D,
    "AccessTagRegistry.catalog_schema_version": _S,
    "AccessTagRegistry.kind": _S,
    "AccessTagRegistry.tags": _G,
    # --- reason messages -----------------------------------------------------
    "ReasonMessage.reason_code": _D,
    "ReasonMessage.interpolation_fields": _D,
    "ReasonMessage.message": _D,
    "ReasonMessage.version": _L,
    "ReasonMessage.effective_from": _L,
    "ReasonMessage.owner_role": _G,
    "ReasonMessage.reviewed_by_role": _G,
    "ReasonMessageRegistry.catalog_schema_version": _S,
    "ReasonMessageRegistry.kind": _S,
    "ReasonMessageRegistry.lang": _D,
    "ReasonMessageRegistry.messages": _D,
    # --- pending visibility approvals ----------------------------------------
    "PendingVisibilityApproval.metric_id": _S,
    "PendingVisibilityApproval.field_name": _G,
    "PendingVisibilityApproval.approval_status": _G,
    "PendingVisibilityApproval.approved_by_role": _G,
    "PendingVisibilityApproval.approved_at": _G,
    "PendingVisibilityApproval.source_commit": _G,
    "PendingVisibilityApproval.expires_at": _G,
    "PendingVisibilityApprovals.catalog_schema_version": _S,
    "PendingVisibilityApprovals.kind": _S,
    "PendingVisibilityApprovals.approvals": _G,
    # --- freshness approvals (D-1) -------------------------------------------
    # Governance throughout, INCLUDING the four restated inventory values. They
    # are not Semantic here: the Semantic fields are `Source.delay_tolerance`,
    # `Source.expected_refresh_interval` and `Source.reporting_timezone`, and
    # the approval only asserts that those authored values were signed off.
    # Classifying the restatements as Semantic would put the same decision into
    # the fingerprint twice and let an approval edit look like a definition
    # change.
    "FreshnessApproval.source_id": _S,
    "FreshnessApproval.approval_status": _G,
    "FreshnessApproval.expected_refresh_interval": _G,
    "FreshnessApproval.delay_tolerance": _G,
    "FreshnessApproval.reporting_time_zone": _G,
    "FreshnessApproval.earliest_available_date": _G,
    "FreshnessApproval.approved_by_role": _G,
    "FreshnessApproval.approved_at": _G,
    "FreshnessApproval.source_commit": _G,
    "FreshnessApproval.expires_at": _G,
    "FreshnessApproval.limitations": _D,
    "FreshnessApproval.known_outages": _A,
    "FreshnessApproval.known_restatements": _L,
    "FreshnessApprovalRegistry.catalog_schema_version": _S,
    "FreshnessApprovalRegistry.kind": _S,
    "FreshnessApprovalRegistry.approvals": _G,
}

#: Read-only authoritative classification.
CLASSIFICATION: Mapping[str, FieldClass] = MappingProxyType(_MAP)

#: The three Lifecycle fields that alter as-of resolution and are therefore
#: fingerprinted alongside every Semantic field.
_FINGERPRINTED_LIFECYCLE = frozenset(
    {"MetricVersion.version", "MetricVersion.effective_from", "MetricVersion.effective_to"}
)

#: Closed set of semantic-fingerprint inputs (T086 consumes this).
FINGERPRINT_INPUTS: frozenset[str] = frozenset(
    {path for path, cls in _MAP.items() if cls is FieldClass.SEMANTIC} | _FINGERPRINTED_LIFECYCLE
)


def class_of(path: str) -> FieldClass:
    """Class for ``Model.field``.

    Raises rather than defaulting. An unclassified field would silently fall out
    of the fingerprint, which is the one failure this map exists to prevent.
    """
    try:
        return CLASSIFICATION[path]
    except KeyError as exc:
        raise UnclassifiedFieldError(
            f"{path!r} has no classification; every authored field must appear in "
            "the map exactly once (catalog-file-contracts.md §4.4)"
        ) from exc


def fields_in_class(field_class: FieldClass) -> tuple[str, ...]:
    """All field paths in ``field_class``, sorted."""
    return tuple(sorted(p for p, c in CLASSIFICATION.items() if c is field_class))


def is_fingerprinted(path: str) -> bool:
    """Whether ``path`` contributes to the semantic fingerprint."""
    return path in FINGERPRINT_INPUTS


def model_field_paths() -> frozenset[str]:
    """Every ``Model.field`` across the authored contracts."""
    paths: set[str] = set()
    for model in _AUTHORED_MODELS:
        assert issubclass(model, BaseModel)
        paths.update(f"{model.__name__}.{name}" for name in model.model_fields)
    return frozenset(paths)


def verify_exhaustive() -> None:
    """Prove the map covers every model field exactly once.

    Raises :class:`UnclassifiedFieldError` on either failure direction:

    * a model field with no entry — it would drop out of the fingerprint;
    * an entry naming no model field — the map has drifted from the models.
    """
    actual = model_field_paths()
    classified = frozenset(CLASSIFICATION)
    missing = sorted(actual - classified)
    stale = sorted(classified - actual)
    if missing or stale:
        problems: list[str] = []
        if missing:
            problems.append(f"unclassified model fields: {missing}")
        if stale:
            problems.append(f"classified fields that no longer exist: {stale}")
        raise UnclassifiedFieldError("; ".join(problems))
