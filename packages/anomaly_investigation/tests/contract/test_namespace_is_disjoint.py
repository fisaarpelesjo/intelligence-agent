"""The fifth namespace is disjoint, and the warning is the baseline's — T011.

**Set intersection over the four existing enums, not a prefix check.** A prefix
convention that only checks itself passes while colliding: if a code here were
named ``QUERY_RESULT_EMPTY``, a test asserting *"every code starts with ANOMALY_"*
would fail for the right reason, but a test asserting *"no code collides"* by
checking the prefix alone would pass while the collision was real. The intersection
is what actually proves the claim.

**And the count of upstream namespaces was itself a measured correction.** An
earlier draft said *"disjoint from the two that exist"*, which would have compared
against half the universe. This file names four because four is what
``research.md`` § 6 measured.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from analytics_interaction.contracts.reason_codes import InterpretationReasonCode
from analytics_query.contracts.reason_codes import AnalyticsReasonCode
from channel_integration.contracts.reason_codes import ChannelReasonCode
from semantic_catalog.contracts.reason_codes import ReasonCode

from anomaly_investigation.contracts import (
    ANOMALY_REASON_CODE_OUTCOME,
    REQUIRED_CAUSALITY_WARNING,
    AnomalyReasonCode,
    ClaimType,
)

pytestmark = pytest.mark.contract

#: ``tests/contract/`` -> ``tests/`` -> package -> ``packages/`` -> repository.
REPO = Path(__file__).resolve().parents[4]
BASELINE = REPO / "docs" / "intelligence-agent.yaml"

UPSTREAM = {
    "001 ReasonCode": ReasonCode,
    "002 AnalyticsReasonCode": AnalyticsReasonCode,
    "003 InterpretationReasonCode": InterpretationReasonCode,
    "004 ChannelReasonCode": ChannelReasonCode,
}


def test_four_upstream_namespaces_were_found() -> None:
    """The intersection below is vacuously empty if the imports silently fail."""
    assert len(UPSTREAM) == 4
    for label, enum in UPSTREAM.items():
        assert len(enum) > 0, label


@pytest.mark.parametrize("label", sorted(UPSTREAM))
def test_no_name_and_no_value_collides_with_an_upstream_namespace(label: str) -> None:
    """Names **and** values, because a collision in either is a collision."""
    upstream = UPSTREAM[label]
    ours_names = {code.name for code in AnomalyReasonCode}
    ours_values = {code.value for code in AnomalyReasonCode}
    theirs_names = {code.name for code in upstream}
    theirs_values = {str(code.value) for code in upstream}

    assert not (ours_names & theirs_names), f"name collision with {label}"
    assert not (ours_values & theirs_values), f"value collision with {label}"


def test_every_code_is_classified() -> None:
    """A code absent from the outcome map is a defect, not a silent DENY."""
    assert set(ANOMALY_REASON_CODE_OUTCOME) == set(AnomalyReasonCode)


def test_the_warning_constant_is_byte_equal_to_the_baseline() -> None:
    """The literal in the contract is compared against the governed file itself.

    This is the check that keeps *"transported, never composed"* true across time:
    if the baseline's sentence is ever edited, this fails rather than the feature
    quietly emitting a stale sentence that no longer matches the governance it
    claims to carry.
    """
    document = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))
    declared = document["proactive_insights"]["causality"]["required_warning"]
    assert declared == REQUIRED_CAUSALITY_WARNING


def test_claim_types_are_the_baselines_closed_three() -> None:
    document = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))
    causality = document["proactive_insights"]["causality"]
    assert causality["automatic_claims_allowed"] is False
    assert {claim.value for claim in ClaimType} == set(causality["allowed_language"])


def test_the_baselines_first_detection_level_is_the_one_implemented() -> None:
    """`FR-002` measured against the baseline rather than restated.

    ``time_series_models`` is ``enabled: false`` and must stay that way for this
    feature; ``robust_statistics`` is enabled and is out of scope by **priority**,
    which is worth asserting so that "out of scope" is never read as "forbidden".
    """
    levels = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))["proactive_insights"][
        "detection_levels"
    ]
    assert levels["business_rules"]["priority"] == "first"
    assert levels["business_rules"]["enabled"] is True
    assert levels["time_series_models"]["enabled"] is False
