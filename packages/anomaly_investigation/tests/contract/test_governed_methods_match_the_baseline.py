"""The eight methods are the baseline's, measured — not trusted.

`rules.py` says `GOVERNED_METHODS` **is** the governed list *"so a reader does not
have to trust that the enum was built from the file"* — and until this test
existed, **nothing checked it**. The claim was true and had no instrument, which
is the class this repository has closed repeatedly: a sentence asserting more than
anything measures.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from anomaly_investigation.contracts import DetectionMethod
from anomaly_investigation.detect import GOVERNED_METHODS

pytestmark = pytest.mark.contract

REPO = Path(__file__).resolve().parents[4]
BASELINE = REPO / "docs" / "intelligence-agent.yaml"


def _business_rules() -> dict[str, Any]:
    document: dict[str, Any] = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))
    level: dict[str, Any] = document["proactive_insights"]["detection_levels"]["business_rules"]
    return level


def test_the_baseline_declares_methods_at_all() -> None:
    """An empty list would make every comparison below vacuously true."""
    methods: list[str] = _business_rules()["methods"]
    assert len(methods) == 8


def test_the_enum_is_exactly_the_baselines_list() -> None:
    """Set equality in **both** directions.

    A subset check would pass while the enum quietly dropped a method, and a
    superset check would pass while it invented one.
    """
    declared: set[str] = set(_business_rules()["methods"])
    ours = {method.value for method in DetectionMethod}
    assert ours == declared


def test_governed_methods_is_the_enum_and_not_a_second_list() -> None:
    """Two hand-maintained copies of one list eventually disagree."""
    assert frozenset(DetectionMethod) == GOVERNED_METHODS


def test_this_level_is_the_first_and_the_third_stays_disabled() -> None:
    """`FR-002` measured against the file rather than restated.

    `robust_statistics` is `enabled: true` and out of scope by **priority**, which
    is asserted so that "out of scope" is never read as "forbidden".
    """
    document: dict[str, Any] = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))
    levels: dict[str, Any] = document["proactive_insights"]["detection_levels"]
    assert levels["business_rules"]["priority"] == "first"
    assert levels["business_rules"]["enabled"] is True
    assert levels["robust_statistics"]["enabled"] is True
    assert levels["time_series_models"]["enabled"] is False
