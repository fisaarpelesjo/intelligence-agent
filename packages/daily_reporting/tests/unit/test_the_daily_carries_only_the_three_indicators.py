"""The daily carries the indicators his file names and nothing else — `T1329` (`F7`, `OD-107`).

`scoped_kpis` is where the report's shape is decided for the 08:00 daily, so this is where the
node drives it (the `OD-54` lesson: guard the chooser, not the renderer). Then the renderer is
measured with a fixture of nineteen KPIs in the five sections of 2026-09-05's real daily, where
EVERY KPI carries two axes of top-5 plus the two lines said unavailable — deliberately heavier
than the real daily (there only the three carry breakdowns), so a fourth indicator let in by his
file renders with the full shape and the ceiling node measures it at its heaviest.

**Mutations** (`T1329`), measured 2026-09-05: `scoped_kpis` returning ``wanted`` whole →
`3 failed, 2 passed` (`test_the_scope_keeps_only_the_named_indicators_in_the_files_order`,
`test_the_scoped_daily_is_shorter_and_fits_one_send`,
`test_the_scoped_daily_keeps_the_breakdowns_of_the_three` red); a fourth indicator in his file →
`test_the_scoped_daily_is_shorter_and_fits_one_send` red (with two contract nodes). The scope NOT
applied by the deliverer is not caught by any node here — it is measured on the real `--dry`
(two sends instead of one) and written in the cycle's handoff, not asserted.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from daily_reporting.numbers.variation import RATE_FORMAT
from daily_reporting.report.breakdown import Breakdown, BreakdownGovernance
from daily_reporting.report.scope import scoped_kpis
from daily_reporting.report.summary import Reading, render, summarise
from daily_reporting.view.shape import ViewRow

pytestmark = pytest.mark.unit

#: Telegram's ceiling as the bot's transport declares it (`telegram_client.py`), and its way of
#: counting — UTF-16 code units, mirrored here so the package needs no import from the bot.
TELEGRAM_CEILING = 4096
HIS_FILE = Path(__file__).resolve().parents[4] / "report_governance" / "daily_scope.yaml"


def telegram_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _his_indicators() -> tuple[str, ...]:
    if not HIS_FILE.is_file():  # pragma: no cover - a checkout without the governed file
        pytest.skip(f"{HIS_FILE} is not in this checkout; nothing was measured")
    document = yaml.safe_load(HIS_FILE.read_text(encoding="utf-8"))
    return tuple(str(name) for name in document["indicators"])


WANTED = {
    "New trials": "new_trials",
    "Sales (qty)": "sales_qty",
    "Trial conversion (%)": "trial_conversion_rate",
    "MRR (US$)": "mrr_usd",
    "Revenue (US$)": "revenue_usd",
}
INDICATORS = ("New trials", "Sales (qty)", "Trial conversion (%)")


def test_the_scope_keeps_only_the_named_indicators_in_the_files_order() -> None:
    assert scoped_kpis(WANTED, INDICATORS) == {
        "New trials": "new_trials",
        "Sales (qty)": "sales_qty",
        "Trial conversion (%)": "trial_conversion_rate",
    }
    reordered = ("Trial conversion (%)", "New trials")
    assert list(scoped_kpis(WANTED, reordered)) == list(reordered)


def test_a_name_no_active_contract_carries_is_refused_not_skipped() -> None:
    with pytest.raises(ValueError, match="no active contract carries"):
        scoped_kpis(WANTED, ("New trials", "Trials (new)"))


def test_an_empty_scope_is_refused() -> None:
    with pytest.raises(ValueError, match="no indicator"):
        scoped_kpis(WANTED, ())


# --- the renderer, measured with the shape of the real 2026-09-05 daily -------------------------

AN_INSTANT = datetime(2026, 9, 5, 11, 0, tzinfo=UTC)
A_CLOSED_DAY = date(2026, 9, 4)

SECTIONS = {
    "Acquisition": (
        "New trials",
        "Sales (qty)",
        "Trial conversion (%)",
        "MRR (US$)",
        "Revenue (US$)",
    ),
    "Revenue": ("Cancellations (%)", "Cancellations (qty)", "Chargeback (%)", "Chargeback (qty)"),
    "Retention": ("MAU", "Not renewed (%)", "Not renewed (qty)", "Paid subscribers"),
    "Plan share": ("Annual (%)", "Monthly (%)", "Quarterly (%)", "Semiannual (%)"),
    "LTV": ("LTV (US$)", "LTV (months)"),
}
EVERY_ACTIVE: dict[str, str] = {label: label for kpis in SECTIONS.values() for label in kpis}
ROWS: tuple[ViewRow, ...] = tuple(
    {"section_name": section, "kpi_name": kpi} for section, kpis in SECTIONS.items() for kpi in kpis
)
READINGS = {
    kpi: Reading(
        format_type=RATE_FORMAT if "%" in kpi else "qty",
        value=Decimal("1234.56"),
        previous_period=Decimal("1200.00"),
        current_period=Decimal("1234.56"),
        series_is_short=False,
    )
    for kpis in SECTIONS.values()
    for kpi in kpis
}
GOVERNANCE = BreakdownGovernance(
    top_n=5,
    axis_labels=(("country", "por país"), ("game", "por jogo")),
    tail_label="demais",
    tail_noun="valores",
    axis_marker="-",
    value_marker="--",
)
_COUNTRIES = ("Brazil", "Mexico", "Argentina", "Colombia", "Peru")
_GAMES = ("No Game", "Counter-Strike 2", "Fortnite", "Valorant", "League of Legends")
_SENTENCE = (
    "A dimensão plan não se aplica à fonte subscription_daily: "
    "essa fonte não registra esse atributo."
)


def _breakdowns() -> dict[str, tuple[Breakdown, ...]]:
    def axis(column: str, label: str, names: tuple[str, ...]) -> Breakdown:
        return Breakdown(
            column=column,
            label=label,
            lines=tuple((name, Decimal(400 - 60 * i)) for i, name in enumerate(names)),
            tail_count=62,
            tail_total=Decimal(172),
        )

    said = (
        Breakdown("plan", "por plano", (), 0, Decimal(0), reason=_SENTENCE),
        Breakdown(
            "gateway", "por gateway", (), 0, Decimal(0), reason=_SENTENCE.replace("plan", "gateway")
        ),
    )
    return {
        kpi: (axis("country", "por país", _COUNTRIES), axis("game", "por jogo", _GAMES), *said)
        for kpis in SECTIONS.values()
        for kpi in kpis
    }


def _rendered(rows: tuple[ViewRow, ...]) -> str:
    summary = summarise(
        rows,
        READINGS,
        day=A_CLOSED_DAY,
        instant=AN_INSTANT,
        periods=((A_CLOSED_DAY, A_CLOSED_DAY), (date(2026, 9, 3), date(2026, 9, 3))),
        declared_order=tuple(SECTIONS),
        breakdowns=_breakdowns(),
    )
    return render(summary, breakdowns_governance=GOVERNANCE)


def test_the_scoped_daily_is_shorter_and_fits_one_send() -> None:
    """`T1329`: the rendered length FALLS below the API's ceiling and the three are all present.

    The scope is read from HIS FILE, not from a constant here, so the mutation `tasks.md` names —
    *a fourth indicator added* — reaches this node: a fourth label appears in the rendered daily
    and the node is red. Every KPI in scope carries the breakdowns of the real daily (two axes of
    top-5, two lines said unavailable), so the length measured is the length of the real shape.
    """
    whole = _rendered(ROWS)
    scope = scoped_kpis(EVERY_ACTIVE, _his_indicators())
    scoped = _rendered(tuple(row for row in ROWS if row["kpi_name"] in scope))
    assert telegram_length(scoped) < telegram_length(whole), (len(scoped), len(whole))
    assert telegram_length(scoped) <= TELEGRAM_CEILING, telegram_length(scoped)
    #: `OD-147` (2026-09-06): the label no longer carries a colon — it opens a block instead of
    #: introducing four numbers on its own line — so the label is matched as the END of a row.
    rows = set(scoped.splitlines())
    labels = {
        label
        for kpis in SECTIONS.values()
        for label in kpis
        if any(row.endswith(label) for row in rows)
    }
    assert labels == set(INDICATORS), sorted(labels)


def test_the_scoped_daily_keeps_the_breakdowns_of_the_three() -> None:
    scope = scoped_kpis(EVERY_ACTIVE, INDICATORS)
    scoped = _rendered(tuple(row for row in ROWS if row["kpi_name"] in scope))
    assert scoped.count("- por país") == 3
    assert scoped.count("- por plano") == 3 and scoped.count("- por gateway") == 3
