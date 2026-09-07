"""The governed contracts of this feature, re-exported.

**This ``__init__`` re-exports deliberately, and the reason was measured** —
``research.md`` § 1. In the four packages' ``src/`` there are 273 ``__all__``
declarations and fifteen package ``__init__``s that both declare one and import;
eleven of the fifteen are in `004`, the package a developer of `005` opens to copy
a pattern from. `003`'s ``comparison/__init__.py`` is the exception that traps
readers: it is a docstring with zero imports, so
``from analytics_interaction.comparison import derive_figure`` **fails**.

Following the majority here is not imitation for its own sake — it is refusing to
add a sixteenth-versus-one coin flip to a repository that already has one.
"""

from __future__ import annotations

from ._base import AnomalyContractViolation, AnomalyModel, GovernedName, build
from .candidate import REQUIRED_CAUSALITY_WARNING, CandidateFinding, ClaimType
from .investigation import Investigation, ReconciliationVerdict
from .reason_codes import (
    ANOMALY_REASON_CODE_OUTCOME,
    AnomalyReasonCode,
    Outcome,
    anomaly_codes_with_outcome,
    anomaly_outcome_for,
)
from .rule import AggregationClass, DetectionMethod, Rule
from .run import Run, RunOutcome, Withholding
from .segment import SegmentContribution, SourceValue

__all__ = [
    "ANOMALY_REASON_CODE_OUTCOME",
    "REQUIRED_CAUSALITY_WARNING",
    "AggregationClass",
    "AnomalyContractViolation",
    "AnomalyModel",
    "AnomalyReasonCode",
    "CandidateFinding",
    "ClaimType",
    "DetectionMethod",
    "GovernedName",
    "Investigation",
    "Outcome",
    "ReconciliationVerdict",
    "Rule",
    "Run",
    "RunOutcome",
    "SegmentContribution",
    "SourceValue",
    "Withholding",
    "anomaly_codes_with_outcome",
    "anomaly_outcome_for",
    "build",
]
