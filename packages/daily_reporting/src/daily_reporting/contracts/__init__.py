"""Contracts of `008`: the refusal type and the eighth reason-code namespace."""

from __future__ import annotations

from ._base import ReportRefusal
from .reason_codes import ReportReasonCode

__all__ = ["ReportReasonCode", "ReportRefusal"]
