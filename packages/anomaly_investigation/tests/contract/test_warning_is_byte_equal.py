"""The causality warning is transported, byte for byte — T030 (`SC-003`, first half).

**Equality, not containment, and the reason is not strictness for its own sake.**
This feature *transports* the baseline's sentence. The moment a check accepted a
paraphrase — or a string that merely *contains* the warning — the feature would be
**composing** it, and composing is what `FR-013` forbids. The strict check is what
keeps the transport honest.

`automatic_claims_allowed` is `false` in the baseline, so the sentence is not ours
to reword, shorten, translate or decorate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from analytics_interaction.comparison.direction import Direction
from analytics_interaction.contracts import DerivedFigure
from analytics_query.contracts.comparable_window import ComparableWindow
from pydantic import ValidationError
from semantic_catalog.freshness.external import CompletenessStatus, FreshnessRecord

from anomaly_investigation.contracts import (
    REQUIRED_CAUSALITY_WARNING,
    CandidateFinding,
    ClaimType,
    Investigation,
    ReconciliationVerdict,
)

pytestmark = pytest.mark.contract

REPO = Path(__file__).resolve().parents[4]
BASELINE = REPO / "docs" / "intelligence-agent.yaml"
AT = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)


def _declared() -> str:
    document = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))
    warning: str = document["proactive_insights"]["causality"]["required_warning"]
    return warning


def _window() -> ComparableWindow:
    return ComparableWindow(
        start=AT.date(), end=AT.date(), reason="catalog", sources=("semantic.trials",)
    )


def _candidate(warning: str) -> CandidateFinding:
    return CandidateFinding(
        rule_id="r",
        figure=DerivedFigure(
            value=Decimal("1"), unit="count", derived_from=("a", "b"), basis="period_over_period"
        ),
        baseline_value=Decimal("1"),
        direction=Direction.INCREASE,
        primary_window=_window(),
        baseline_window=_window(),
        freshness=FreshnessRecord(
            source="trials", status=CompletenessStatus.COMPLETE, observed_at=AT
        ),
        claim_type=ClaimType.CORRELATION,
        causality_warning=warning,
    )


def test_the_constant_equals_the_baseline_byte_for_byte() -> None:
    """If the governed sentence is ever edited, this fails **instead of** the
    feature quietly emitting a stale one that no longer matches the governance it
    claims to carry."""
    assert _declared() == REQUIRED_CAUSALITY_WARNING


def test_the_bytes_match_and_not_merely_the_characters() -> None:
    """Encoded comparison, because the sentence carries accents.

    A normalisation difference — NFC against NFD — reads identically to a human
    and is a different byte string. *"Byte-equal"* has to mean bytes.
    """
    assert REQUIRED_CAUSALITY_WARNING.encode("utf-8") == _declared().encode("utf-8")


@pytest.mark.parametrize(
    "wrong",
    [
        "",
        "  ",
        "Os dados podem indicar associação temporal.",
        "os dados podem indicar associação temporal, mas não comprovam causalidade.",
        "Os dados podem indicar associacao temporal, mas nao comprovam causalidade.",
        "Os dados podem indicar associação temporal, mas não comprovam causalidade",
    ],
)
def test_every_near_miss_is_refused(wrong: str) -> None:
    """Empty, blank, truncated, lower-cased, unaccented, and missing the full stop.

    **The last two are the ones that matter.** Stripping accents and dropping the
    final period are what a well-meaning edit does, and both change the sentence
    the baseline requires.
    """
    with pytest.raises(ValidationError):
        _candidate(wrong)


def test_containment_is_not_equality() -> None:
    """The case that separates the two checks, stated on its own.

    A string that contains the warning has **our words around it** — which is
    exactly the composition `FR-013` forbids.
    """
    decorated = "Atenção: " + REQUIRED_CAUSALITY_WARNING
    assert REQUIRED_CAUSALITY_WARNING in decorated
    with pytest.raises(ValidationError):
        _candidate(decorated)


def test_the_investigation_is_held_to_the_same_sentence() -> None:
    """Both emitted entities, not just the candidate.

    Checking one would leave the other free to drift, and `SC-003` says *every*
    emitted output.
    """
    ok = Investigation(
        rule_id="r",
        reconciliation=ReconciliationVerdict.NOT_ATTEMPTED,
        claim_type=ClaimType.CORRELATION,
        causality_warning=REQUIRED_CAUSALITY_WARNING,
    )
    assert ok.causality_warning == _declared()

    with pytest.raises(ValidationError):
        Investigation(
            rule_id="r",
            reconciliation=ReconciliationVerdict.NOT_ATTEMPTED,
            claim_type=ClaimType.CORRELATION,
            causality_warning=REQUIRED_CAUSALITY_WARNING + " ",
        )


def test_the_correct_sentence_is_accepted() -> None:
    """The refusals above would be vacuous over a field nothing satisfies."""
    assert _candidate(REQUIRED_CAUSALITY_WARNING).causality_warning == _declared()
