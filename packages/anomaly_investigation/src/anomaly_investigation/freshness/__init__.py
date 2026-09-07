"""Freshness and completeness, decided before detection exists.

Re-exports, following the majority of the four packages' `src/` trees rather than
`003`'s `comparison`, which re-exports nothing and traps readers who assume the
repository is uniform (`research.md` § 1).
"""

from __future__ import annotations

from .validate import (
    CLASS_RANK,
    EVIDENCE_CLASS,
    WITHHOLDING_PRECEDENCE,
    WITHIN_CLASS_ORDER,
    EvidenceClass,
    FreshnessVerdict,
    assess_freshness,
    evidence_class,
)

__all__ = [
    "CLASS_RANK",
    "EVIDENCE_CLASS",
    "WITHHOLDING_PRECEDENCE",
    "WITHIN_CLASS_ORDER",
    "EvidenceClass",
    "FreshnessVerdict",
    "assess_freshness",
    "evidence_class",
]
