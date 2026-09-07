"""Mid-flight catalog change — T089 (FR-029; SC-020).

Between validation and execution the catalog can move: a release published, a
metric version superseded. If it did, the result on the wire was computed under
a definition the decision never validated.

**The race resolves toward refusal.** The output is discarded and the request
refuses with ``CATALOG_CHANGED_DURING_EXECUTION``. Returning it would hand back
a figure whose governance verdict does not apply to it — the ceilings, the
caveats and the declared units were all established against a different
definition, so none of them describes what actually came back.

**The cost is still recorded.** The warehouse was paid whether or not the answer
was usable, and a ledger that dropped the cost of a discarded execution would
under-report spend exactly when something is going wrong.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts._base import ContractViolation
from ..contracts.reason_codes import AnalyticsReasonCode

__all__ = ["CatalogSnapshot", "assert_catalog_unchanged"]


@dataclass(frozen=True, slots=True)
class CatalogSnapshot:
    """What the catalog looked like at one instant.

    Captured before execution and re-read after. Metric versions are compared
    as a sorted set, so a differently ordered but identical collection is not a
    change — the question is whether the definitions moved, not how they were
    listed.
    """

    release_id: str
    metric_version_ids: tuple[str, ...]

    def normalised(self) -> tuple[str, tuple[str, ...]]:
        return self.release_id, tuple(sorted(self.metric_version_ids))


def assert_catalog_unchanged(before: CatalogSnapshot, after: CatalogSnapshot) -> None:
    """Discard and refuse when the catalog moved during execution.

    The message names *that* the catalog changed, never which metric or which
    version. A caller who could not see a definition before the execution must
    not learn about it from the failure.
    """
    if before.normalised() == after.normalised():
        return
    raise ContractViolation(
        AnalyticsReasonCode.CATALOG_CHANGED_DURING_EXECUTION,
        "the catalog changed between validation and execution; the output is discarded",
    )
