"""Range-length enforcement — T064 (FR-008, FR-010; SC-027).

Applied **only after authorisation succeeds**. The refusal names the requested
length and the governed limit, which is useful to an entitled caller and is
exactly the kind of disclosure an unauthorized one must never receive — so the
ordering is the control, not the wording (`FR-011`, authorization-preflight §step 5).

Dates are interpreted in the canonical business time zone, resolved through the
IANA database rather than a fixed offset (`FR-008`). A fixed ``-03:00`` would be
wrong for part of the year in any zone that has ever observed DST, and "the
range was one day short in October" is the kind of defect nobody finds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from ..contracts._base import ContractViolation
from ..contracts.reason_codes import AnalyticsReasonCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..contracts.policy import QueryPolicy
    from ..contracts.request import DateRange

__all__ = ["BUSINESS_TIME_ZONE", "assert_range_within_limit", "business_zone"]

#: The canonical business time zone. Resolved through the IANA database.
BUSINESS_TIME_ZONE = "America/Sao_Paulo"


def business_zone() -> ZoneInfo:
    """The canonical zone, or a hard failure.

    Raises if the IANA database is unavailable rather than falling back to UTC:
    a silent fallback would shift every date boundary by three hours.
    """
    return ZoneInfo(BUSINESS_TIME_ZONE)


def assert_range_within_limit(date_range: DateRange, policy: QueryPolicy) -> None:
    """Refuse a range longer than the governed maximum.

    Call this **after** the preflight has authorized the principal. Calling it
    earlier would disclose ``maximum_range_days`` to someone not entitled to
    know the policy exists.
    """
    # Touching the zone here keeps the dependency honest: the canonical zone must
    # be resolvable for any date reasoning this feature does.
    business_zone()

    requested = date_range.days
    limit = policy.maximum_range_days
    if requested > limit:
        raise ContractViolation(
            AnalyticsReasonCode.DATE_RANGE_TOO_LONG,
            f"requested range of {requested} days exceeds the governed maximum of {limit}",
        )
