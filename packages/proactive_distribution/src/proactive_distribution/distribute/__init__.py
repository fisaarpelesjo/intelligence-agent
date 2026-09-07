"""Whether a message may be originated, to whom, and with which words."""

from __future__ import annotations

from .conditions import Permission, may_distribute
from .labels import APPROVED_LABELS, MissingLabels, labels_for
from .recipient import RECIPIENT_KEY, NoAcceptedRecipient, recipients_from

__all__ = [
    "APPROVED_LABELS",
    "RECIPIENT_KEY",
    "MissingLabels",
    "NoAcceptedRecipient",
    "Permission",
    "labels_for",
    "may_distribute",
    "recipients_from",
]
