"""This feature's reason-code namespace — `T801`, `T802`.

**Seven disjoint namespaces already exist, and the count is measured rather than
remembered** — `001`'s ``ReasonCode``, `002`'s ``AnalyticsReasonCode``, `003`'s
``InterpretationReasonCode``, `004`'s ``ChannelReasonCode``, `005`'s
``AnomalyReasonCode``, `006`'s ``PriorityReasonCode`` and `007`'s
``DistributionReasonCode``. This adds an **eighth**, and adds no precedent: it
follows the one the seven before it set.

**The ownership rule is the narrow one `004` wrote and every feature since has
kept:** a code here may only describe a condition none of the seven upstream layers
can observe. `002` cannot know a week was incomplete for a WEEKLY comparison it was
never asked to make; `001` cannot know a metric failed to declare which column
carries its number, because that declaration does not exist until this feature needs
it. **An upstream refusal is carried, never restated.**

## Why the report's codes and the alert's codes are in one enum but never one concern

The two products do not merge, and neither do their reasons. Every code below belongs
to exactly one of them, and the split is visible in the names: ``REPORT_`` refuses to
summarise, ``ALERT_`` refuses to raise. **A report refusing is a report that cannot be
built; an alert refusing is a report that is built and says nothing more.** They are
different outcomes for the reader and are never collapsed.

## The codes, and each is raised by something in this same package

=====================================  ====================================================
code                                   what it says
=====================================  ====================================================
``REPORT_KPI_NOT_DERIVABLE``           a row carries no name or no section to derive from
``REPORT_VALUE_COLUMN_NOT_DECLARED``   the metric never declared which column holds it
``REPORT_PERIOD_NOT_COMPLETE``         a week short of seven days was handed in
``REPORT_DAY_NOT_CLOSED``              the day in progress was handed in
``ALERT_SERIES_TOO_SHORT``             fewer comparable periods than the derived minimum
``ALERT_THRESHOLD_NOT_COMPUTABLE``     the series cannot produce a percentile
=====================================  ====================================================
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["ReportReasonCode"]


class ReportReasonCode(StrEnum):
    """Why a summary was not built, or an alert not raised. **Closed.**

    A code minted without a producer is dead vocabulary — `001`'s rule, kept by every
    feature since. Each of the six below is raised by something in this package, and a
    node asserts that rather than trusting this sentence.
    """

    #: A row from the view carries no `kpi_name` or no `section_name`, so a label
    #: cannot be derived. **The report refuses rather than borrowing a name**, because
    #: a borrowed name is a label this repository authored — `FR-803`.
    REPORT_KPI_NOT_DERIVABLE = "report_kpi_not_derivable"

    #: The metric's catalog contract does not declare which column carries its value.
    #: **Never defaulted to `value`** — that default is exactly the shape that
    #: published MRR and Revenue as valueless when their numbers were in `value_usd`.
    REPORT_VALUE_COLUMN_NOT_DECLARED = "report_value_column_not_declared"

    #: A period handed in is not a complete seven-day week. **Reporting over it would
    #: compare six days against seven** and call the difference a movement — `FR-809`.
    REPORT_PERIOD_NOT_COMPLETE = "report_period_not_complete"

    #: The instant handed in falls on the day still in progress. The daily report
    #: speaks of the CLOSED day; the source rebuilds at 06:00 UTC and its window ends
    #: yesterday — `FR-802`.
    REPORT_DAY_NOT_CLOSED = "report_day_not_closed"

    #: The KPI has fewer comparable periods than the derived minimum -- DAYS since `OD-31`,
    #: and the word moved with the unit rather than after it. **It still appears
    #: in the report**, with its number and the footnote; what refuses is the alert,
    #: and only the alert — `FR-814`.
    ALERT_SERIES_TOO_SHORT = "alert_series_too_short"

    #: The series cannot produce a percentile at all. **No flat threshold is
    #: substituted**, not even temporarily: a guessed threshold is a claim about noise
    #: nobody measured — `FR-813`, `FR-820`.
    ALERT_THRESHOLD_NOT_COMPUTABLE = "alert_threshold_not_computable"
