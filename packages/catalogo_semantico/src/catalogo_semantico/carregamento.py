from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .modelos import (
    Aggregation,
    Catalogo,
    DimensionDefinition,
    DimensionType,
    Grain,
    MetricDefinition,
    MetricDefinitionVersion,
    MetricStatus,
)


class CatalogoInvalido(ValueError):
    """Levantada quando o catalogo declarado viola uma invariante de integridade."""


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _build_version(raw: dict[str, Any]) -> MetricDefinitionVersion:
    return MetricDefinitionVersion(
        effective_from=raw["effective_from"],
        effective_until=raw.get("effective_until"),
        label=raw["label"],
        source_view=raw["source_view"],
        grain=Grain(raw["grain"]),
        aggregation=Aggregation(raw["aggregation"]),
        unit=raw["unit"],
        allowed_dimensions=tuple(raw.get("allowed_dimensions", [])),
        owner=raw.get("owner"),
        limitations=raw.get("limitations"),
    )


def _assert_no_overlap(metric_id: str, versions: tuple[MetricDefinitionVersion, ...]) -> None:
    ordered = sorted(versions, key=lambda v: v.effective_from)
    for earlier, later in zip(ordered, ordered[1:], strict=False):
        if earlier.effective_until is None or earlier.effective_until > later.effective_from:
            raise CatalogoInvalido(
                f"metric '{metric_id}' has overlapping version windows: "
                f"{earlier.effective_from}..{earlier.effective_until} vs "
                f"{later.effective_from}..{later.effective_until}"
            )


def _build_metrics(raw_metrics: list[dict[str, Any]]) -> dict[str, MetricDefinition]:
    metrics: dict[str, MetricDefinition] = {}
    for raw in raw_metrics:
        metric_id = raw["id"]
        if metric_id in metrics:
            raise CatalogoInvalido(f"duplicate metric id in catalog: '{metric_id}'")
        versions = tuple(_build_version(v) for v in raw["versions"])
        _assert_no_overlap(metric_id, versions)
        metrics[metric_id] = MetricDefinition(
            id=metric_id,
            status=MetricStatus(raw.get("status", "active")),
            versions=versions,
        )
    return metrics


def _build_dimensions(raw_dimensions: list[dict[str, Any]]) -> dict[str, DimensionDefinition]:
    dimensions: dict[str, DimensionDefinition] = {}
    for raw in raw_dimensions:
        dimension_id = raw["id"]
        if dimension_id in dimensions:
            raise CatalogoInvalido(f"duplicate dimension id in catalog: '{dimension_id}'")
        dimensions[dimension_id] = DimensionDefinition(
            id=dimension_id, type=DimensionType(raw["type"])
        )
    return dimensions


def carregar_catalogo(caminho: str | Path) -> Catalogo:
    base = Path(caminho)
    metrics_doc = _load_yaml(base / "metrics.yaml") or {}
    dimensions_doc = _load_yaml(base / "dimensions.yaml") or {}
    metrics = _build_metrics(metrics_doc.get("metrics", []))
    dimensions = _build_dimensions(dimensions_doc.get("dimensions", []))
    return Catalogo(metrics=metrics, dimensions=dimensions)
