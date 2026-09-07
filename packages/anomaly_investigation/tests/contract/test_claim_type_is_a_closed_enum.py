"""Every assertion declares a `claim_type` from a closed set — T031 (`SC-003`, second half).

**Checked as an enum domain rather than as a string**, so a typo cannot pass as a
fourth kind. `automatic_claims_allowed` is `false`, so a fourth value is a baseline
change and a decision that is not ours.

And the check is over **the fields that carry an assertion**, which is the division
`contracts/candidate-finding.md` draws: a measurement is what the governed seam
returned; an assertion is a statement *about* a measurement.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from anomaly_investigation.contracts import (
    REQUIRED_CAUSALITY_WARNING,
    ClaimType,
    Investigation,
    ReconciliationVerdict,
)

pytestmark = pytest.mark.contract

REPO = Path(__file__).resolve().parents[4]
BASELINE = REPO / "docs" / "intelligence-agent.yaml"
SRC = Path(__file__).resolve().parents[2] / "src" / "anomaly_investigation"

#: Every emitted contract that carries an assertion must declare its class.
#: **Named, so a new emitted entity without a `claim_type` fails here** rather
#: than shipping an assertion nobody classified.
ASSERTING = ("candidate.py", "investigation.py", "segment.py")


def _allowed() -> set[str]:
    document = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))
    language: list[str] = document["proactive_insights"]["causality"]["allowed_language"]
    return set(language)


def test_the_enum_is_exactly_the_baselines_allowed_language() -> None:
    """Set equality in both directions: a missing value and an invented one are
    both defects, and a subset check would catch only one."""
    assert {claim.value for claim in ClaimType} == _allowed()


def test_the_baseline_forbids_automatic_claims() -> None:
    """The premise under the closed set. If this ever flipped, the whole shape of
    this feature would be up for reconsideration rather than quietly wider."""
    document = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))
    assert document["proactive_insights"]["causality"]["automatic_claims_allowed"] is False


def test_there_are_exactly_three() -> None:
    assert len(ClaimType) == 3


@pytest.mark.parametrize("name", ASSERTING)
def test_every_asserting_contract_declares_a_claim_type(name: str) -> None:
    """The field must exist on the entity, not merely be available somewhere.

    An assertion emitted without its class is an assertion nobody bounded.
    """
    tree = ast.parse((SRC / "contracts" / name).read_text(encoding="utf-8"))
    declaring = {
        klass.name
        for klass in ast.walk(tree)
        if isinstance(klass, ast.ClassDef)
        and any(
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "claim_type"
            for node in klass.body
        )
    }
    assert declaring, f"{name} declares no claim_type on any entity"


@pytest.mark.parametrize("bad", ["causation", "cause", "correlational", "CORRELATION", ""])
def test_a_value_outside_the_three_is_refused(bad: str) -> None:
    """**`causation` is the one that matters**, and it is refused by the domain
    rather than by anybody reading the diff."""
    with pytest.raises(ValidationError):
        Investigation(
            rule_id="r",
            reconciliation=ReconciliationVerdict.NOT_ATTEMPTED,
            claim_type=bad,  # type: ignore[arg-type]  # the point is that it is refused
            causality_warning=REQUIRED_CAUSALITY_WARNING,
        )


@pytest.mark.parametrize("claim", list(ClaimType))
def test_each_of_the_three_is_accepted(claim: ClaimType) -> None:
    """The refusals above would be vacuous over a field nothing satisfies."""
    investigation = Investigation(
        rule_id="r",
        reconciliation=ReconciliationVerdict.NOT_ATTEMPTED,
        claim_type=claim,
        causality_warning=REQUIRED_CAUSALITY_WARNING,
    )
    assert investigation.claim_type is claim


def test_no_contract_names_a_causal_field() -> None:
    """`FR-006` enforced by the **shape**, before any value is checked.

    A field called `cause` would let a caller populate a causal claim while every
    `claim_type` stayed inside the three.
    """
    forbidden = ("cause", "because", "driver", "root_cause", "reason_why", "explanation")
    offences: list[str] = []
    for path in sorted((SRC / "contracts").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            named = isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
            if named and node.target.id in forbidden:  # type: ignore[union-attr]
                offences.append(node.target.id)  # type: ignore[union-attr]
    assert not offences, offences
