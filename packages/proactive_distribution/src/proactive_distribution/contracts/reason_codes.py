"""This feature's reason-code namespace — T701.

**Six disjoint namespaces already exist, and the count is measured rather than
remembered** — `001`'s ``ReasonCode``, `002`'s ``AnalyticsReasonCode``, `003`'s
``InterpretationReasonCode``, `004`'s ``ChannelReasonCode``, `005`'s
``AnomalyReasonCode`` and `006`'s ``PriorityReasonCode``. This adds a **seventh**,
and adds no precedent: it follows the one the five before it set.

**The ownership rule is the narrow one `004` wrote and every feature since has
kept:** a code here may only describe a condition none of the six upstream layers
can observe. `006` cannot know a channel is disabled; `004` cannot know a finding
was not placed, because delivery does not rank. **An upstream refusal is carried,
never restated.**

## Why the missing labels have their own code, and it is the point of `T701`

Two entirely different things stop this feature today, and **a reader who sees one
code cannot tell which stopped them**:

* **nothing was worth sending** — `006` returned the finding as not prioritisable;
* **there is nothing approved to send it WITH** — the owner has not written the five
  labels.

Collapsing them into one refusal would report *the data had nothing to say* when the
truth is *the data spoke and we have no approved way to say it*. The first is a fact
about the warehouse; the second is a fact about a decision nobody has taken. They get
separate codes for that reason and no other.

## The codes, and each is used by a contract in this same package

================================================  ==========================================
code                                              what it says
================================================  ==========================================
``DISTRIBUTION_FINDING_NOT_PRIORITISABLE``        `006` did not place the finding
``DISTRIBUTION_CHANNEL_NOT_ENABLED``              the channel is not already enabled
``DISTRIBUTION_RECIPIENT_NOT_ACCEPTED``           no accepted recipient is derivable
``DISTRIBUTION_LABELS_NOT_APPROVED``              the owner's five labels do not exist
``DISTRIBUTION_FIELD_NOT_MEASURED``               a field has no value, so nothing is sent
================================================  ==========================================
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["DistributionReasonCode"]


class DistributionReasonCode(StrEnum):
    """Why nothing was distributed. **Closed**, and every member is used here.

    A code minted without a producer is dead vocabulary — `001`'s rule, kept by every
    feature since. Each of the five below is raised by a contract in this package, and
    a node asserts that rather than trusting this sentence.
    """

    #: The first condition of ADR 0035. `006` returned the finding unplaced, so there
    #: is nothing this feature is permitted to originate a message about.
    DISTRIBUTION_FINDING_NOT_PRIORITISABLE = "distribution_finding_not_prioritisable"

    #: The second condition of ADR 0035. **This feature enables nothing** — the ADR's
    #: wording is *already* enabled, and making it so is a different act with a
    #: different authorization.
    DISTRIBUTION_CHANNEL_NOT_ENABLED = "distribution_channel_not_enabled"

    #: The third condition of ADR 0035. No accepted recipient could be derived from the
    #: declared key. **Never raised because a value looked wrong** — this feature does
    #: not judge the value, only whether the key yielded one.
    DISTRIBUTION_RECIPIENT_NOT_ACCEPTED = "distribution_recipient_not_accepted"

    #: The owner's five labels do not exist. **Distinct from every other code here on
    #: purpose**, because *nothing was worth saying* and *there is no approved way to
    #: say it* are different facts about different parties.
    DISTRIBUTION_LABELS_NOT_APPROVED = "distribution_labels_not_approved"

    #: A field carries no value. A partially filled report is not a message with a gap;
    #: it is a claim about something nobody measured, so nothing is sent.
    DISTRIBUTION_FIELD_NOT_MEASURED = "distribution_field_not_measured"
