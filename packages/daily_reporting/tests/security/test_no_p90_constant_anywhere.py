"""No `p90` lives in source, in any package — `T819`.

The table in `specs/008-daily-report-and-rule-alerts/spec.md` § 9 is **dated evidence
for a reader**, measured 2026-08-27. `FR-812` keeps it out of code, because a number
correct on the day it is typed and drifting every day after is the **`F136`** failure —
and it is the one that passes twenty tests forever while the alerts stop matching the
data.

**The sweep is over every package, not only this one.** A constant smuggled into a
sibling would be just as frozen, and this feature is the one that would consume it.
"""

from __future__ import annotations

import ast
import re
from decimal import Decimal
from pathlib import Path

import pytest

pytestmark = pytest.mark.security

#: `tests/security/` -> `tests/` -> package -> `packages/`.
PACKAGES = Path(__file__).resolve().parents[3]

#: The measured values, as text, so this file can look for them without holding them as
#: numbers a computation could reach. They are here to be FORBIDDEN, not to be used.
MEASURED_P90_TEXT = (
    "158.7",
    "100.0",
    "84.6",
    "75.7",
    "32.0",
    "27.1",
    "25.8",
    "25.5",
    "25.3",
    "23.0",
    "22.8",
    "21.9",
    "19.3",
    "14.8",
    "14.5",
)

#: A name that announces the thing this file forbids. **No `\b` after `p90`**: the
#: first run of this file used one, and `P90_BY_KPI` slipped past it because `_` is a
#: word character. The proof node below is what caught that.
SUSPICIOUS_NAME = re.compile(r"(?i)p90|percentile_table|thresholds_by_kpi")


def _source_files() -> list[Path]:
    return sorted(
        path for path in PACKAGES.glob("*/src/**/*.py") if "__pycache__" not in path.parts
    )


def test_the_sweep_reaches_every_package() -> None:
    """Read this first: a sweep over nothing forbids nothing — the `F115` shape."""
    files = _source_files()
    assert len(files) > 50, f"the sweep found only {len(files)} source files"
    packages = {path.relative_to(PACKAGES).parts[0] for path in files}
    assert len(packages) >= 7, f"the sweep reached only {sorted(packages)}"


def test_no_source_file_carries_a_measured_p90() -> None:
    """A number lifted from the evidence table into code is that table in code."""
    offending: list[str] = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant):
                continue
            if isinstance(node.value, bool) or not isinstance(node.value, int | float | str):
                continue
            text = str(node.value)
            if text in MEASURED_P90_TEXT:
                offending.append(f"{path.relative_to(PACKAGES)}:{node.lineno} carries {text}")
    assert not offending, "\n".join(offending)


def test_no_source_file_names_a_threshold_table() -> None:
    """A name is the other half: the value may be split, the intent is not."""
    offending: list[str] = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name | ast.Attribute):
                continue
            if isinstance(node, ast.FunctionDef | ast.ClassDef) and SUSPICIOUS_NAME.search(
                node.name
            ):
                offending.append(f"{path.relative_to(PACKAGES)}:{node.lineno} defines {node.name}")
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and SUSPICIOUS_NAME.search(target.id):
                        offending.append(
                            f"{path.relative_to(PACKAGES)}:{node.lineno} binds {target.id}"
                        )
    assert not offending, "\n".join(offending)


def test_the_sweep_would_catch_a_smuggled_table() -> None:
    """**Proof it bites**, over source this file parses rather than over the tree."""
    smuggled = ast.parse('P90_BY_KPI = {"cac": 158.7}\n')
    values = [
        str(node.value)
        for node in ast.walk(smuggled)
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float | str)
    ]
    names = [
        target.id
        for node in ast.walk(smuggled)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    ]
    assert any(value in MEASURED_P90_TEXT for value in values), "the value sweep misses it"
    assert any(SUSPICIOUS_NAME.search(name) for name in names), "the name sweep misses it"


def test_the_percentile_this_feature_uses_is_a_fraction_and_not_a_measurement() -> None:
    """`0.90` is the owner's CHOICE OF PERCENTILE, which does not age.

    The distinction matters: *which percentile* is a decision, and *what that percentile
    equals today* is a measurement. The first belongs in code; the second never does.
    """
    from daily_reporting.alert.threshold import ALERT_PERCENTILE

    chosen = Decimal("0.90")
    assert chosen == ALERT_PERCENTILE
    assert str(ALERT_PERCENTILE) not in MEASURED_P90_TEXT
