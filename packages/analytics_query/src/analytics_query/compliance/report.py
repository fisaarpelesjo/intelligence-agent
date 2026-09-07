"""Compliance reporting — T102 (FR-063, FR-064; SC-025).

Every fixture-backed result states its limitation, and no artifact this feature
produces claims production readiness.

The caveat is **structural, not editorial**. `FixtureBackedReport` cannot be
constructed without it: the limitation is a required field with a fixed
sentence, so there is no path that produces a fixture-backed report and forgets
to say so. A report that merely *usually* carries the caveat is one that will
eventually be quoted without it.

The distinction being protected is easy to lose in a summary. "All 1200 tests
pass" is true and says nothing about production, because every one of them ran
against fixtures. Someone reading that line six months later, deciding whether
to switch this on, needs the sentence next to the number.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field, model_validator

from ..contracts._base import ContractViolation, QueryModel
from ..contracts.reason_codes import AnalyticsReasonCode
from .readiness import aggregate, load_record, readiness_root

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterable

__all__ = ["FIXTURE_LIMITATION", "FixtureBackedReport", "build_report"]

#: The exact sentence every fixture-backed report carries. Fixed rather than
#: composed per report: a wording that varied could be softened one report at a
#: time until it said nothing.
FIXTURE_LIMITATION = (
    "These results are fixture-backed. They demonstrate internal behaviour only "
    "and say nothing about production readiness."
)

#: Phrases no artifact of this feature may contain.
FORBIDDEN_CLAIMS = (
    "production ready",
    "production-ready",
    "ready for production",
    "certified",
    "guaranteed in production",
)


class FixtureBackedReport(QueryModel):
    """A validation report whose evidence came from fixtures."""

    title: str = Field(min_length=1)
    #: Gates that ran, and whether each passed. Counts only — no figures.
    gates_passed: int = Field(ge=0)
    gates_total: int = Field(ge=0)
    #: Capabilities whose external evidence is present. Empty is the normal state.
    capabilities_ready: tuple[str, ...] = ()
    #: Capabilities still awaiting evidence.
    capabilities_awaiting: tuple[str, ...] = ()
    limitation: str = FIXTURE_LIMITATION

    @model_validator(mode="after")
    def _states_its_limitation_and_claims_nothing(self) -> FixtureBackedReport:
        """The caveat is exact, and no readiness claim survives anywhere in it."""
        if self.limitation != FIXTURE_LIMITATION:
            raise ContractViolation(
                AnalyticsReasonCode.REQUEST_MALFORMED,
                "a fixture-backed report must carry the governed limitation verbatim",
            )
        # Only the title is scanned. The limitation is exact-matched above, and
        # it necessarily contains the phrase "production readiness" — scanning it
        # too would either always fire or, if excused, disable the check
        # entirely. Guarding the field that varies is the whole point.
        title = self.title.lower()
        for claim in FORBIDDEN_CLAIMS:
            if claim in title:
                raise ContractViolation(
                    AnalyticsReasonCode.REQUEST_MALFORMED,
                    "a report of this feature may not claim production readiness",
                )
        if self.gates_passed > self.gates_total:
            raise ContractViolation(
                AnalyticsReasonCode.REQUEST_MALFORMED,
                "more gates passed than ran",
            )
        return self

    @property
    def all_gates_passed(self) -> bool:
        """Every gate green — which still says nothing about production."""
        return self.gates_total > 0 and self.gates_passed == self.gates_total


def build_report(
    *,
    title: str,
    gates_passed: int,
    gates_total: int,
    records: Iterable[object] | None = None,
) -> FixtureBackedReport:
    """Assemble a report from the governed readiness record.

    ``capabilities_awaiting`` is populated from the record rather than left
    implicit. A report that listed only what is ready would read as complete;
    naming what is still missing is what makes the fail-closed state visible.
    """
    from .readiness import ReadinessRecord

    loaded: list[ReadinessRecord] = (
        list(records)  # type: ignore[arg-type]
        if records is not None
        else [load_record(readiness_root() / "analytics-query-external-readiness.yaml")]
    )
    ready = aggregate(loaded)
    declared = {name for record in loaded for name in record.capabilities}

    return FixtureBackedReport(
        title=title,
        gates_passed=gates_passed,
        gates_total=gates_total,
        capabilities_ready=tuple(sorted(ready)),
        capabilities_awaiting=tuple(sorted(declared - ready)),
    )
