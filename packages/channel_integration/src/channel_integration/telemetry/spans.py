"""Telemetry over the six stages — T049 (FR-085; SC-040).

Span names and an **attribute allowlist**. Nothing else.

Telemetry is the other way what the audit contract forbids gets out, so the rule is the same and
the enforcement is stricter: an attribute name outside :data:`PERMITTED_ATTRIBUTES` cannot be
attached, so a content-bearing field cannot arrive by being called something harmless.

**Metric labels are bounded by the same allowlist.** An unbounded label — a question, an answer, a
raw identity — is both a leak and a cardinality explosion, and the two failures have one cause.

No exporter, no SDK, no network. This module names what a span may carry; wiring one is a
deployment concern and belongs where the listener lives (`D-30`).
"""

from __future__ import annotations

from collections.abc import Mapping

from ..contracts.audit import CHANNEL_STAGE_ORDER, ChannelStage

__all__ = ["PERMITTED_ATTRIBUTES", "SPAN_NAMES", "span_attributes", "span_name"]

#: One span per stage, named for the stage, in sequence order.
SPAN_NAMES: Mapping[ChannelStage, str] = {
    stage: f"channel.{stage.value.lower()}" for stage in CHANNEL_STAGE_ORDER
}

#: Every attribute a span or a metric label may carry. Closed.
#:
#: Note what is absent: no text, question, answer, value, filter value, provenance, caveat,
#: payload, header, signature, credential, url or raw identity. Only governed identifiers,
#: pseudonymous references, an outcome, a code, an operator-facing class and governing versions.
PERMITTED_ATTRIBUTES = frozenset(
    {
        "channel",
        "tenant",
        "principal_ref",
        "external_identity_ref",
        "correlation_id",
        "message_key",
        "stage",
        "outcome",
        "code",
        "detail_class",
        "policy_version",
        "capability_version",
    }
)


def span_name(stage: ChannelStage) -> str:
    """The span name for ``stage``."""
    return SPAN_NAMES[stage]


def span_attributes(attributes: Mapping[str, str]) -> dict[str, str]:
    """``attributes``, or refuse the whole set.

    Refusing the set rather than dropping the offender is deliberate: a silently dropped
    attribute is a caller believing it recorded something, and a caller that believes it recorded
    a value is a caller that will eventually record one.
    """
    unknown = sorted(set(attributes) - PERMITTED_ATTRIBUTES)
    if unknown:
        raise ValueError(f"telemetry attributes are not permitted: {', '.join(unknown)}")
    return dict(attributes)
