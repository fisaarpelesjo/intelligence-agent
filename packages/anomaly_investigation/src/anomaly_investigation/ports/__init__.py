"""The seams this feature asks through, and never reaches around.

`FR-003`: no arithmetic over warehouse values here. `FR-012`: no date computed
here. Both are kept by asking, and both would be broken by a shortcut that read a
value directly.
"""

from __future__ import annotations

from .catalog_port import CatalogEvaluator, MetricResolution, resolve_metric
from .figures_port import FigureExecutor, MovementResolution, SideFigure, resolve_movement

__all__ = [
    "CatalogEvaluator",
    "FigureExecutor",
    "MetricResolution",
    "MovementResolution",
    "SideFigure",
    "resolve_metric",
    "resolve_movement",
]
