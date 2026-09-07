"""Observation failure handling — T042 (FR-076; SC-033).

Every way an observation read can fall short collapses to one outcome:
``OBSERVATIONS_UNAVAILABLE``, and the request refuses.

There is deliberately **no fallback**. Not to a previous snapshot, not to a
default, not to an assumption of freshness. Each of those would answer from a
state nobody observed, and the answer would look exactly like a real one. A
refusal is legible; a silently stale figure is not.

"Partial" is treated as failure, not as a smaller success. A bundle missing one
required source cannot say whether that source is stale — and the whole purpose
of reading freshness is to know.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..contracts.reason_codes import AnalyticsReasonCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .reader import ObservationBundle, ObservationReader

__all__ = ["ObservationsUnavailable", "read_bundle_or_refuse"]


class ObservationsUnavailable(RuntimeError):  # noqa: N818 - named for its reason code, OBSERVATIONS_UNAVAILABLE
    """The governed observations could not be established for this request."""

    def __init__(self, detail: str) -> None:
        self.code = AnalyticsReasonCode.OBSERVATIONS_UNAVAILABLE
        self.detail = detail
        super().__init__(f"{self.code.value}: {detail}")


def read_bundle_or_refuse(
    reader: ObservationReader,
    *,
    source_ids: frozenset[str],
    correlation_id: str,
) -> ObservationBundle:
    """Read one atomic bundle, or refuse.

    Four failure classes, one outcome:

    * the read raises — the warehouse was unreachable or the query failed;
    * the bundle is empty while sources were required;
    * the bundle is partial — some required source is missing from freshness,
      coverage or revisions;
    * the bundle belongs to another request, which means a snapshot escaped the
      request it was read for (`FR-077`).
    """
    try:
        bundle = reader.read(source_ids=source_ids, correlation_id=correlation_id)
    except ObservationsUnavailable:
        raise
    except Exception as exc:
        raise ObservationsUnavailable(f"governed observation read failed: {exc}") from exc

    if source_ids and not bundle.source_ids():
        raise ObservationsUnavailable("governed observation read returned no records")

    if not bundle.is_atomic_for(source_ids):
        missing = sorted(source_ids - bundle.source_ids())
        raise ObservationsUnavailable(
            "governed observation read is not atomic across freshness, coverage and revisions"
            + (f"; unobserved sources: {len(missing)}" if missing else "")
        )

    if bundle.request_correlation_id != correlation_id:
        raise ObservationsUnavailable(
            "observation bundle belongs to another request; a snapshot is never reused"
        )

    return bundle
