"""Authored-file loader — T023 (FR-006).

Loads ``semantic/**.yaml`` into validated contract models. Every failure mode is
**fail-closed**: an unreadable, unrecognised, mis-versioned or invalid file is an
error, never a skipped file. A loader that silently ignores what it cannot parse
produces a catalog that looks smaller than it is, and nobody notices until a
metric that should have been governed turns out not to be.

Five refusals, each with its own exception so a caller can tell them apart:

``UnknownKindError``
    ``kind`` is missing or not a governed contract. Guessing from the directory
    would let a misfiled document load as the wrong contract.

``UnsupportedSchemaVersionError``
    Outside ``SUPPORTED_SCHEMA_VERSIONS``. Older files must be migrated
    deliberately; newer ones mean the code is behind the content.

``DuplicateIdentifierError``
    Two files claim the same identifier. Preferring either one silently would
    make which definition wins depend on filesystem ordering.

``MalformedFileError``
    Not a YAML mapping, or unreadable.

Field-level violations surface as Pydantic ``ValidationError`` — unknown fields
included, because every contract sets ``extra="forbid"``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import BaseModel

from ..contracts import (
    access_tag,
    approval,
    comparability,
    definition_approval,
    dimension,
    freshness_approval,
    glossary,
    metric,
    owner,
    policy,
    reason_message,
    source,
)
from ..contracts._base import SUPPORTED_SCHEMA_VERSIONS
from .upgrade import upgrade_payload

__all__ = [
    "CONTRACT_KINDS",
    "CatalogLoadError",
    "DuplicateIdentifierError",
    "LoadedCatalog",
    "MalformedFileError",
    "UnknownKindError",
    "UnsupportedSchemaVersionError",
    "load_catalog",
    "load_file",
]


class CatalogLoadError(Exception):
    """Base for every load refusal. Always fatal — never a skipped file."""


class MalformedFileError(CatalogLoadError):
    """Unreadable, or not a YAML mapping."""


class UnknownKindError(CatalogLoadError):
    """``kind`` missing or not a governed contract."""


class UnsupportedSchemaVersionError(CatalogLoadError):
    """``catalog_schema_version`` outside the supported window."""


class DuplicateIdentifierError(CatalogLoadError):
    """Two files claim the same identifier for the same kind."""


#: ``kind`` to contract model. A file whose ``kind`` is absent from this map is
#: refused; the directory it sits in is never used to infer the contract.
CONTRACT_KINDS: Mapping[str, type[BaseModel]] = {
    "owners": owner.OwnerRegistry,
    "source": source.Source,
    "dimension": dimension.Dimension,
    "comparability": comparability.ComparabilityRule,
    "glossary": glossary.GlossaryTerm,
    "metric": metric.Metric,
    "catalog_policy": policy.CatalogPolicy,
    "access_tags": access_tag.AccessTagRegistry,
    "reason_messages": reason_message.ReasonMessageRegistry,
    "pending_visibility_approvals": approval.PendingVisibilityApprovals,
    "freshness_approvals": freshness_approval.FreshnessApprovalRegistry,
    # ciclo 525 (2026-09-02): o cofre do D-2, no molde do frescor.
    "definition_approvals": definition_approval.DefinitionApprovalRegistry,
}

#: Where a contract's own identifier lives, per kind. Registries are singletons
#: and are keyed by kind instead.
_IDENTIFIER_FIELD: Mapping[str, str] = {
    "source": "id",
    "dimension": "id",
    "comparability": "id",
    "glossary": "id",
    "metric": "name",
    "catalog_policy": "policy_id",
}


@dataclass(frozen=True, slots=True)
class LoadedCatalog:
    """Everything authored under ``semantic/``, validated and keyed."""

    owners: owner.OwnerRegistry | None
    sources: Mapping[str, source.Source]
    dimensions: Mapping[str, dimension.Dimension]
    metrics: Mapping[str, metric.Metric]
    comparability_rules: Mapping[str, comparability.ComparabilityRule]
    glossary_terms: Mapping[str, glossary.GlossaryTerm]
    policies: tuple[policy.CatalogPolicy, ...]
    access_tags: access_tag.AccessTagRegistry | None
    reason_messages: reason_message.ReasonMessageRegistry | None
    approvals: approval.PendingVisibilityApprovals | None
    freshness_approvals: freshness_approval.FreshnessApprovalRegistry | None
    definition_approvals: definition_approval.DefinitionApprovalRegistry | None
    files: Mapping[str, Path]

    def is_empty(self) -> bool:
        return not (self.sources or self.dimensions or self.metrics)


def _read_mapping(path: Path) -> dict[str, Any]:
    raw: object
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))  # pyright: ignore[reportAny]
    except (OSError, yaml.YAMLError) as exc:
        raise MalformedFileError(f"{path}: cannot be read as YAML ({exc})") from exc
    if raw is None:
        raise MalformedFileError(f"{path}: is empty; an empty file is not an empty contract")
    if not isinstance(raw, dict):
        raise MalformedFileError(f"{path}: top level is {type(raw).__name__}, expected a mapping")
    mapping = cast("dict[object, object]", raw)
    return {str(key): value for key, value in mapping.items()}


def load_file(path: Path) -> tuple[str, BaseModel]:
    """Load and validate one authored file. Returns ``(kind, model)``.

    Raises a :class:`CatalogLoadError` subclass, or ``ValidationError`` for a
    field-level violation.
    """
    payload = _read_mapping(path)

    kind = payload.get("kind")
    if not isinstance(kind, str) or kind not in CONTRACT_KINDS:
        raise UnknownKindError(
            f"{path}: kind {kind!r} is not a governed contract; expected one of "
            f"{sorted(CONTRACT_KINDS)}. The directory is never used to infer the kind."
        )

    version = payload.get("catalog_schema_version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise UnsupportedSchemaVersionError(
            f"{path}: catalog_schema_version must be an integer, got {version!r}"
        )
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise UnsupportedSchemaVersionError(
            f"{path}: catalog_schema_version {version} is outside the supported window "
            f"{sorted(SUPPORTED_SCHEMA_VERSIONS)}; migrate the file deliberately"
        )

    payload = upgrade_payload(payload, from_version=version)

    # Field-level violations propagate as Pydantic ValidationError, unknown
    # fields included: every contract sets extra="forbid".
    model = CONTRACT_KINDS[kind].model_validate(payload)
    return kind, model


def _identifier(kind: str, model: BaseModel) -> str | None:
    field = _IDENTIFIER_FIELD.get(kind)
    if field is None:
        return None
    value = getattr(model, field)
    return str(value)


def load_catalog(root: Path, *, pattern: str = "**/*.yaml") -> LoadedCatalog:
    """Load every authored file under ``root``.

    Files are discovered, not enumerated from an index, so a new metric is
    governed the moment it is committed. Every discovered file must load: there
    is no skip-on-error path.
    """
    if not root.is_dir():
        raise MalformedFileError(f"{root}: is not a directory")

    owners_registry: owner.OwnerRegistry | None = None
    tags: access_tag.AccessTagRegistry | None = None
    messages: reason_message.ReasonMessageRegistry | None = None
    approvals: approval.PendingVisibilityApprovals | None = None
    freshness: freshness_approval.FreshnessApprovalRegistry | None = None
    definitions: definition_approval.DefinitionApprovalRegistry | None = None
    policies: list[policy.CatalogPolicy] = []
    buckets: dict[str, dict[str, BaseModel]] = {
        k: {} for k in ("source", "dimension", "metric", "comparability", "glossary")
    }
    files: dict[str, Path] = {}

    for path in sorted(root.glob(pattern)):
        kind, model = load_file(path)
        identifier = _identifier(kind, model)

        if identifier is not None:
            key = f"{kind}:{identifier}"
            if key in files:
                raise DuplicateIdentifierError(
                    f"{path}: {kind} {identifier!r} is already defined by {files[key]}; "
                    "which definition wins must never depend on filesystem ordering"
                )
            files[key] = path
            if kind == "catalog_policy":
                policies.append(model)  # type: ignore[arg-type]
            else:
                buckets[kind][identifier] = model
            continue

        singleton_key = f"{kind}:singleton"
        if singleton_key in files:
            raise DuplicateIdentifierError(
                f"{path}: a second {kind} file; {files[singleton_key]} already defines it"
            )
        files[singleton_key] = path
        match kind:
            case "owners":
                owners_registry = model  # type: ignore[assignment]
            case "access_tags":
                tags = model  # type: ignore[assignment]
            case "reason_messages":
                messages = model  # type: ignore[assignment]
            case "pending_visibility_approvals":
                approvals = model  # type: ignore[assignment]
            case "freshness_approvals":
                freshness = model  # type: ignore[assignment]
            case "definition_approvals":
                definitions = model  # type: ignore[assignment]
            case _:  # pragma: no cover - CONTRACT_KINDS membership is checked above
                raise UnknownKindError(f"{path}: {kind!r} has no singleton handler")

    return LoadedCatalog(
        owners=owners_registry,
        sources=dict(buckets["source"]),  # type: ignore[arg-type]
        dimensions=dict(buckets["dimension"]),  # type: ignore[arg-type]
        metrics=dict(buckets["metric"]),  # type: ignore[arg-type]
        comparability_rules=dict(buckets["comparability"]),  # type: ignore[arg-type]
        glossary_terms=dict(buckets["glossary"]),  # type: ignore[arg-type]
        policies=tuple(policies),
        access_tags=tags,
        reason_messages=messages,
        approvals=approvals,
        freshness_approvals=freshness,
        definition_approvals=definitions,
        files=dict(files),
    )


def discovered_kinds(models: Iterable[tuple[str, BaseModel]]) -> tuple[str, ...]:
    """Kinds present in a loaded set, sorted. Useful in compliance reporting."""
    return tuple(sorted({kind for kind, _ in models}))
