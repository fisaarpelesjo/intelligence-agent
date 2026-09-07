"""Typed governed contracts: intake, resolved intent, clarification, comparison,
answer, reason codes and audit. Every model is frozen and forbids unknown fields,
so a caller cannot pass a field that does not exist.

This module is the package's **public contract surface**. Importing it also
closes the one genuine cycle in the data model: ``ResolvedIntent`` forward-
references ``ComparisonIntent``, which needs ``ResolvedPeriod`` back. Importing
`intent` then `comparison` here — and `comparison` rebuilding ``ResolvedIntent``
at its end — means no import order can observe a half-built model.

`contracts/audit.py` is deliberately absent: the interpretation audit event and
its six stages are `T136`, in Phase 13.
"""

from ._base import ContractViolation, InteractionModel, LocalizedRef, build
from .answer import (
    AnalyticsAnswer,
    AnswerClaim,
    AttributedCaveat,
    CaveatOrigin,
    CaveatSet,
    ClaimClass,
    ComparisonBasis,
    InsufficiencyNotice,
)
from .clarification import (
    SUPPORTED_CONTRACT_VERSIONS,
    CandidateRef,
    ClarificationContract,
    Seal,
)
from .comparison import (
    ComparisonIntent,
    ComparisonRoute,
    DerivedFigure,
    GovernedComparison,
    SideResult,
)
from .intake import (
    STRUCTURAL_TEXT_CEILING,
    DeclaredLanguage,
    PrincipalContext,
    QuestionIntake,
)
from .intent import (
    MatchKind,
    PeriodConvention,
    ResolutionBasis,
    ResolvedIntent,
    ResolvedPeriod,
    SlotKind,
    TermRef,
    TermResolution,
)
from .reason_codes import (
    REASON_CODE_OUTCOME,
    InterpretationReasonCode,
    Outcome,
    codes_with_outcome,
    outcome_for,
)

__all__ = [
    "REASON_CODE_OUTCOME",
    "STRUCTURAL_TEXT_CEILING",
    "SUPPORTED_CONTRACT_VERSIONS",
    "AnalyticsAnswer",
    "AnswerClaim",
    "AttributedCaveat",
    "CandidateRef",
    "CaveatOrigin",
    "CaveatSet",
    "ClaimClass",
    "ClarificationContract",
    "ComparisonBasis",
    "ComparisonIntent",
    "ComparisonRoute",
    "ContractViolation",
    "DeclaredLanguage",
    "DerivedFigure",
    "GovernedComparison",
    "InsufficiencyNotice",
    "InteractionModel",
    "InterpretationReasonCode",
    "LocalizedRef",
    "MatchKind",
    "Outcome",
    "PeriodConvention",
    "PrincipalContext",
    "QuestionIntake",
    "ResolutionBasis",
    "ResolvedIntent",
    "ResolvedPeriod",
    "Seal",
    "SideResult",
    "SlotKind",
    "TermRef",
    "TermResolution",
    "build",
    "codes_with_outcome",
    "outcome_for",
]
