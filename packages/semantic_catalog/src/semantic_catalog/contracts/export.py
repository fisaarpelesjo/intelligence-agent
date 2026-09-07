"""JSON Schema export — T022 (FR-053).

**This module is the single writer of ``schemas/``.** No other task generates
into that directory, and nothing there is ever hand-edited: the Pydantic models
are the source of truth, the JSON Schema is a derived artifact for editor
completion, pre-commit hooks and non-Python tooling.

That rule is not stylistic. A hand-edited schema that disagrees with the models
gives editors one answer and CI another, and the disagreement surfaces as a
mysterious validation failure weeks later. :func:`check_drift` makes the
disagreement impossible by regenerating and comparing.

Determinism matters: the output is sorted and newline-terminated so regeneration
on a clean tree is byte-identical and a diff means a real change.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel

from . import (
    access_tag,
    approval,
    audit_event,
    comparability,
    dimension,
    freshness_approval,
    glossary,
    metric,
    owner,
    policy,
    reason_message,
    source,
)
from ._base import SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS

__all__ = [
    "EXPORTED_MODELS",
    "SchemaDriftError",
    "check_drift",
    "export_all",
    "render_schema",
    "schema_filename",
]

#: Root contracts exported to ``schemas/``. Nested models appear inside their
#: root's ``$defs``; exporting them separately would duplicate definitions.
EXPORTED_MODELS: Mapping[str, type[BaseModel]] = {
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
    # Not an authored file, but downstream consumers validate emitted events
    # against it, so it is generated from the same source of truth (T020).
    "catalog_decision_audit_event": audit_event.CatalogDecisionAuditEvent,
}


class SchemaDriftError(RuntimeError):
    """Committed JSON Schema differs from what the models generate."""


def schema_filename(kind: str) -> str:
    """File name for a contract kind."""
    return f"{kind}.schema.json"


def render_schema(model: type[BaseModel], kind: str) -> str:
    """Deterministic JSON Schema text for ``model``."""
    schema = model.model_json_schema(mode="validation")
    schema["$id"] = f"https://intelligence-agent/semantic-catalog/{kind}.schema.json"
    schema["x-catalog-schema-version"] = SCHEMA_VERSION
    schema["x-supported-schema-versions"] = list(SUPPORTED_SCHEMA_VERSIONS)
    schema["x-generated-by"] = "semantic_catalog.contracts.export"
    schema["x-do-not-edit"] = (
        "Generated from the Pydantic models. Edit the models, then regenerate. "
        "This file is never a source of truth."
    )
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def export_all(out_dir: Path) -> tuple[Path, ...]:
    """Write every schema to ``out_dir``. Returns the paths written, sorted."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for kind, model in EXPORTED_MODELS.items():
        path = out_dir / schema_filename(kind)
        path.write_text(render_schema(model, kind), encoding="utf-8")
        written.append(path)
    return tuple(sorted(written))


def check_drift(out_dir: Path) -> tuple[str, ...]:
    """Kinds whose committed schema differs from the generated one.

    Empty means the committed artifacts match the models. A non-empty result
    fails CI (T100) — the fix is always to regenerate, never to edit the file.
    """
    drifted: list[str] = []
    for kind, model in EXPORTED_MODELS.items():
        path = out_dir / schema_filename(kind)
        expected = render_schema(model, kind)
        if not path.exists() or path.read_text(encoding="utf-8") != expected:
            drifted.append(kind)
    return tuple(sorted(drifted))
