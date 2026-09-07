"""L4 policy validation — T093 (FR-054, FR-056, FR-058, FR-074).

L4 is the layer for rules the *policy* imposes on the catalog, rather than rules
the file format imposes on a file. Its audience is the reviewer approving a
change, so every finding names both the rule and the thing that broke it.

Seven rules, in three groups.

**Human-facing content (FR-054, FR-056).** Every content block must exist, carry
an explicit ``lang: pt-BR`` marker and hold no blank text. The contracts already
enforce this at L1 for every model that inherits ``PtBrContent`` — this sweep
re-asserts it over the whole loaded catalog, which is what catches a *future*
contract that forgets to inherit it. A metric or dimension failing here is
non-compliant and must not be published.

**Language correctness is not checked, and is not claimed** (D-10, research §R-4).
L4 verifies that pt-BR content is present and declared. It does not run language
detection: short labels defeat every detector, and a false failure on a correct
label teaches stewards to bypass the gate. Whether the Portuguese is *right*
stays a named reviewer duty, and no automated gate here may be read as covering
it.

**Pending visibility (FR-058).** A pending metric exposes ``public_name`` or
``expected_available_from`` only under an approval, so an approval naming a field
the policy does not list as exposable is a grant for something the projection
will never honour, and a policy that switches the approval requirement off
disagrees with the requirement itself.

**Reason messages (FR-074).** A reason code that can reach a consumer with no
canonical pt-BR message **fails the build**. The alternative is discovering it at
the worst moment: a refusal that reaches a user as an English enum name, or as
nothing at all.

The version gate and closed-version immutability are also L4 and live next door
in :mod:`~semantic_catalog.validation.l4_version`; keeping them separate keeps
this module free of any notion of a baseline.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from ..contracts.metric import Lifecycle
from ..contracts.policy import CatalogPolicy
from ..contracts.reason_codes import ReasonCode
from ..loader.load import LoadedCatalog
from .result import Severity, Subject, ValidationFinding, ValidationLayer, ValidationReport

__all__ = ["CONSUMER_REACHABLE_CODES", "validate_policy"]

#: Every governed code may reach a consumer through a decision, so every one
#: needs a canonical message. Treating the set as smaller would mean guessing
#: which refusals users never see, and being wrong once is a refusal nobody can
#: read.
CONSUMER_REACHABLE_CODES: frozenset[ReasonCode] = frozenset(ReasonCode)


def _finding(
    rule: str,
    kind: str,
    identifier: str,
    message: str,
    *,
    field_path: str | None = None,
    severity: Severity = Severity.ERROR,
) -> ValidationFinding:
    return ValidationFinding(
        layer=ValidationLayer.L4_POLICY,
        rule=rule,
        severity=severity,
        subject=Subject(kind=kind, identifier=identifier, field_path=field_path),
        message=message,
    )


def _content_findings(
    block: BaseModel | None, kind: str, identifier: str, field_path: str
) -> Iterable[ValidationFinding]:
    """One content block: present, declared pt-BR, no blank text (FR-054, FR-056)."""
    if block is None:
        yield _finding(
            "pt_br_content_missing",
            kind,
            identifier,
            f"{kind} {identifier!r} has no {field_path} block; human-facing content is required "
            "and an entry without it must not be published (FR-056)",
            field_path=field_path,
        )
        return

    lang = getattr(block, "lang", None)
    if lang != "pt-BR":
        yield _finding(
            "content_lang_not_pt_br",
            kind,
            identifier,
            f"{kind} {identifier!r} declares {field_path}.lang as {lang!r}; human-facing content "
            "is authored in pt-BR and its language is declared, never inferred (FR-054)",
            field_path=f"{field_path}.lang",
        )

    for name in type(block).model_fields:
        if name == "lang":
            continue
        value: Any = getattr(block, name, None)
        if isinstance(value, str) and not value.strip():
            yield _finding(
                "pt_br_content_missing",
                kind,
                identifier,
                f"{kind} {identifier!r} has a blank {field_path}.{name}; a present-but-empty "
                "field is a missing field with extra steps (FR-056)",
                field_path=f"{field_path}.{name}",
            )


def _catalog_content_findings(catalog: LoadedCatalog) -> Iterable[ValidationFinding]:
    for metric_id, metric in sorted(catalog.metrics.items()):
        for version in metric.versions:
            yield from _content_findings(
                version.content, "metric", metric_id, f"versions[{version.version}].content"
            )
    for dimension_id, dimension in sorted(catalog.dimensions.items()):
        yield from _content_findings(dimension.content, "dimension", dimension_id, "content")
    for source_id, source in sorted(catalog.sources.items()):
        yield from _content_findings(source.content, "source", source_id, "content")
    for term_id, term in sorted(catalog.glossary_terms.items()):
        yield from _content_findings(term.content, "glossary", term_id, "content")
    if catalog.access_tags is not None:
        for tag in catalog.access_tags.tags:
            yield from _content_findings(tag.content, "access_tag", tag.id, "content")


def _pending_visibility_findings(
    catalog: LoadedCatalog, policy: CatalogPolicy, lifecycles: dict[str, Lifecycle] | None
) -> Iterable[ValidationFinding]:
    rules = policy.pending_visibility
    if not rules.require_visibility_approval:
        yield _finding(
            "pending_visibility_approval_not_required",
            "catalog_policy",
            policy.policy_id,
            f"policy {policy.policy_id!r} does not require a visibility approval; FR-058 makes "
            "the approval unconditional, so a policy that switches it off disagrees with the "
            "requirement rather than configuring it",
            field_path="pending_visibility.require_visibility_approval",
        )

    if catalog.approvals is None:
        return
    exposable = frozenset(rules.exposable_fields)
    for approval in catalog.approvals.approvals:
        identifier = f"{approval.metric_id}.{approval.field_name}"
        if approval.field_name not in exposable:
            yield _finding(
                "visibility_approval_field_not_exposable",
                "approval",
                identifier,
                f"approval {identifier!r} grants exposure of a field the policy does not list as "
                f"exposable ({sorted(exposable)}); the projection would omit it regardless, so "
                "the grant states an authority that does not exist (FR-058)",
                field_path="field_name",
            )
        if lifecycles is not None and lifecycles.get(approval.metric_id) is not Lifecycle.PENDING:
            yield _finding(
                "visibility_approval_for_non_pending_metric",
                "approval",
                identifier,
                f"approval {identifier!r} covers a metric that is not pending; pending-visibility "
                "approvals govern the pending projection only",
                field_path="metric_id",
                severity=Severity.WARNING,
            )


def _reason_message_findings(
    catalog: LoadedCatalog, policy: CatalogPolicy, publishable: frozenset[ReasonCode]
) -> Iterable[ValidationFinding]:
    if not policy.publication.require_reason_message_for_publishable_codes:
        return
    registry = catalog.reason_messages
    if registry is None:
        yield _finding(
            "reason_message_registry_missing",
            "reason_messages",
            "reason-messages.pt-BR.yaml",
            "no reason-messages.pt-BR.yaml registry is authored; a refusal with no canonical "
            "message would reach a consumer as an English enum name, and messages are never "
            "translated at answer time (FR-055, FR-074)",
        )
        return
    for code in registry.missing_codes(publishable):
        yield _finding(
            "publishable_code_without_message",
            "reason_code",
            code.value,
            f"reason code {code.value} can reach a consumer and has no canonical pt-BR message; "
            "a publishable code with no message fails the catalog build (FR-074)",
        )


def validate_policy(
    catalog: LoadedCatalog,
    policy: CatalogPolicy,
    *,
    lifecycles: dict[str, Lifecycle] | None = None,
    publishable: frozenset[ReasonCode] | None = None,
) -> ValidationReport:
    """Run every L4 policy rule. An empty report means all seven passed.

    ``lifecycles`` is optional so this can run before a bundle is built; without
    it the pending-visibility staleness warning is skipped rather than guessed.
    """
    findings: list[ValidationFinding] = []
    findings.extend(_catalog_content_findings(catalog))
    findings.extend(_pending_visibility_findings(catalog, policy, lifecycles))
    findings.extend(
        _reason_message_findings(
            catalog, policy, publishable if publishable is not None else CONSUMER_REACHABLE_CODES
        )
    )
    return ValidationReport.from_findings(findings)
