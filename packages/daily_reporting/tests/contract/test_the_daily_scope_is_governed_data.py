"""The daily's scope is GOVERNED DATA, and it is the three indicators of his contract — `T1329`.

`OD-107` split the report: the 08:00 daily carries the indicators, the weekly the rest
(`FR-1319`). Which indicators is HIS choice, so it lives in `report_governance/daily_scope.yaml`
and not in code — this file measures the real yaml against the two other places his three
indicators are already written: the metric contracts (each one is an active KPI) and
`report_governance/breakdown.yaml` (`kpis`, the indicators that carry breakdowns, `F1`).

**Mutation** (`tasks.md`, `T1329`, *"a fourth indicator added"*): `MRR (US$)` appended to
`indicators` → measured 2026-09-05 over this file and the unit file together, `3 failed, 6 passed`:
`test_the_daily_scope_is_exactly_the_three_indicators_of_his_contract`,
`test_the_scope_is_the_same_three_the_breakdown_file_names` and the unit file's
`test_the_scoped_daily_is_shorter_and_fits_one_send` red.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from daily_reporting.report.scope import active_kpis, scoped_kpis

pytestmark = pytest.mark.contract

REPO = Path(__file__).resolve().parents[4]
SCOPE = REPO / "report_governance" / "daily_scope.yaml"
BREAKDOWN = REPO / "report_governance" / "breakdown.yaml"
METRICS = REPO / "semantic" / "metrics"
#: The view the daily reads, as the metric contracts name it (`source_view`, and the deliverer).
THE_VIEW = "semantic.subscription_daily_metrics"


def _document(path: Path) -> dict[str, Any]:
    if not path.is_file():  # pragma: no cover - a checkout without the governed file
        pytest.skip(f"{path} is not in this checkout; nothing was measured")
    return cast("dict[str, Any]", yaml.safe_load(path.read_text(encoding="utf-8")))


def _contracts() -> list[dict[str, Any]]:
    return [
        cast("dict[str, Any]", yaml.safe_load(path.read_text(encoding="utf-8")))
        for path in sorted(METRICS.glob("*.yaml"))
    ]


def test_the_governed_file_declares_itself_and_his_decision() -> None:
    document = _document(SCOPE)
    assert document["kind"] == "report_daily_scope"
    assert document["decided_by"] == "OD-107"
    assert isinstance(document["indicators"], list) and document["indicators"]


def test_the_daily_scope_is_exactly_the_three_indicators_of_his_contract() -> None:
    """His daily example (`contrato-013-exemplos.md` :35-46) names three, and only three."""
    indicators = _document(SCOPE)["indicators"]
    assert indicators == ["New trials", "Sales (qty)", "Trial conversion (%)"], indicators


def test_every_indicator_is_an_active_kpi_and_the_scope_applies_without_refusing() -> None:
    """A name the contracts do not carry would be refused by `scoped_kpis`; the real file passes."""
    indicators = [str(name) for name in _document(SCOPE)["indicators"]]
    wanted = active_kpis(_contracts(), view=THE_VIEW)
    assert wanted, "no active KPI read from the contracts; this node would prove nothing"
    scoped = scoped_kpis(wanted, indicators)
    assert list(scoped) == indicators
    assert len(scoped) < len(wanted), "the scope cut nothing; the daily would still overflow"


def test_the_scope_is_the_same_three_the_breakdown_file_names() -> None:
    """Two governed files, one set of indicators — his, written twice, never diverging."""
    indicators = _document(SCOPE)["indicators"]
    kpis = _document(BREAKDOWN)["kpis"]
    assert set(indicators) == set(kpis), (indicators, kpis)
