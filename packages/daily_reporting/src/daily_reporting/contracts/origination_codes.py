"""Why nothing was originated — `ADR 0036`'s five conditions, one code each — `T834`.

## A separate namespace from `ReportReasonCode`, and the split is not cosmetic

`ReportReasonCode` answers *why this summary could not be built* and *why this alert could
not be raised*. These answer a different question: **the thing was built, and may it leave
the repository?** That is an authority question, and merging the two would give a reader one
code for two decisions taken by different people for different reasons — the mistake `377`
closed when `007` refused to fuse *nothing was worth sending* with *there is no approved way
to say it*.

## One code per condition, because a reader who sees one must know which stopped them

`ADR 0036` names **five** conditions and all are required. Five conditions behind one refusal
is a message that says *not today* without saying why, and each of the five is resolved by a
different person doing a different thing: enabling the channel, deciding a recipient, fixing a
seam, taking a wording decision, and waiting for a series to fill.

**And a sixth code answers what the ADR does not name at all**, which is a different fact
again: not *a condition failed* but *this record was never about that*.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["OriginationReasonCode"]


class OriginationReasonCode(StrEnum):
    """Why a built report or alert may not leave. **Closed**, and every member is raised."""

    #: `ADR 0036` names the daily report and the rule alert, and nothing else. Anything
    #: outside those two stays under `FR-062` unchanged — this is `FR-825`, and it is
    #: distinct from every condition below because *no record covers this* is not *a
    #: condition failed*.
    ORIGINATION_NOT_NAMED_BY_THE_ADR = "origination_not_named_by_the_adr"

    #: Condition 1. The channel must be **already** enabled; this feature enables nothing,
    #: and a record that cannot be read is not permission either.
    ORIGINATION_CHANNEL_NOT_ENABLED = "origination_channel_not_enabled"

    #: Condition 2. The recipient is the owner's own chat and no other, derived from the
    #: declared key. A second recipient is not a configuration value — it is a decision
    #: that does not exist.
    ORIGINATION_RECIPIENT_NOT_AUTHORIZED = "origination_recipient_not_authorized"

    #: Condition 3. Every number comes from the seams. A line carrying a figure for a KPI
    #: the source never stated is a number this feature invented, whatever it equals.
    ORIGINATION_FIGURE_NOT_FROM_THE_SOURCE = "origination_figure_not_from_the_source"

    #: Condition 4. The wording is the closed template of `OD-15`. A word nobody approved
    #: is a word this repository authored and attributed to him.
    ORIGINATION_WORDING_NOT_HIS = "origination_wording_not_his"

    #: Condition 5. A KPI without sufficient series appears **without** an alert. Raising
    #: one on a series that cannot support a threshold is a claim about noise nobody
    #: measured.
    ORIGINATION_SHORT_SERIES_WAS_ALERTED = "origination_short_series_was_alerted"
