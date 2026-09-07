"""The vault of signed definitions (`OD-100`) is CONSULTED on the production path — `OD-124` (c).

## What was measured before a line was written

`DefinitionApprovalRegistry.evaluate` had **zero callers** outside its own contract file, and
`definition_approvals` was loaded by `load.py` and read by nothing (grep over `packages/*/src` and
`apps`, 2026-09-04). Nineteen definitions signed on 2026-09-02, and a contract whose sentence
changed after the signature would have carried the approval forward in silence — the exact
outcome the vault's docstring says it exists to stop: *"lê DEFINITION_CHANGED até alguém
reassinar"*.

**A trap this file records because it was almost fallen into**: `visibility.py:97` calls an
`approvals.evaluate(...)` — with a different signature, on the PENDING-VISIBILITY registry. Same
word, different vault. A grep for `.evaluate(` alone would have said the debt did not exist.

## Where the consumer lives, and why there

The bot's production path builds the real bundle: `run.py:282 _survey → anomaly.survey →
build_bundle → derive_lifecycles`. A stale definition now becomes a `PendingReason`, the metric
becomes `PENDING`, `project_metric` returns a `PendingStub`, and `gate_2_lifecycle` refuses with
`METRIC_PENDING` naming the reason — the same mechanism a freshness denial already uses. A named
refusal on the real path, not a library node that calls `evaluate` and stays green.

## What is NOT measured, said out loud

The commit half. The approval binds to the commit that last changed the metric's own file; the
bundle is built with ONE commit and carries no per-file commits, so `evaluate` is handed the
approval's own commit and `COMMIT_MISMATCH` is unreachable from this path. `test_definition_
approvals_current.py` measures that half in CI with `git log`. Production measures the sentence
and the role.

## The rule this file applies to itself

Every fixture below is written in a state where the approved sentence and the current one
DIFFER — a fixture where they coincide would let the mutation that drops the check stay green.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from semantic_catalog.contracts.definition_approval import (
    DefinitionApproval,
    DefinitionApprovalRegistry,
    DefinitionDenial,
)
from semantic_catalog.contracts.metric import Lifecycle, Metric
from semantic_catalog.contracts.reason_codes import ReasonCode
from semantic_catalog.loader.bundle import build_bundle
from semantic_catalog.loader.lifecycle import (
    PendingReason,
    definition_denials,
    derive_lifecycle,
    derive_lifecycles,
)
from semantic_catalog.loader.load import LoadedCatalog, load_catalog
from semantic_catalog.loader.projection import PendingStub

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[4]
SEMANTIC = REPO / "semantic"
ON = date(2026, 9, 4)
COMMIT = "0000000"

APPROVED = "Sessões iniciadas no dia, sem sessões de teste."
REWRITTEN = "Sessões iniciadas no dia, INCLUINDO sessões de teste."

METRIC: dict[str, object] = {
    "catalog_schema_version": 1,
    "kind": "metric",
    "name": "sessions",
    "owner": "product_analytics",
    "access": "standard",
    "grain_family": "day",
    "versions": [
        {
            "version": 1,
            "effective_from": date(2026, 8, 11),
            "source_view": "semantic.product_daily_metrics",
            "grain": "date x platform",
            "aggregation": "sum",
            "additivity": "additive",
            "unit": "sessions",
            "time_dimension": "date",
            "calculation_basis": "Sessões iniciadas no dia.",
            "content": {
                "lang": "pt-BR",
                "label": "Sessões",
                "description": "Número de sessões iniciadas no dia.",
                "limitations": [APPROVED],
            },
        }
    ],
}


def _metric(limitation: str) -> Metric:
    payload = {**METRIC}
    version = {**METRIC["versions"][0]}  # type: ignore[index]
    version["content"] = {**version["content"], "limitations": [limitation]}  # type: ignore[index]
    payload["versions"] = [version]
    return Metric.model_validate(payload)


def _vault(
    *, role: str = "product_analytics", sentence: str = APPROVED
) -> DefinitionApprovalRegistry:
    return DefinitionApprovalRegistry(
        catalog_schema_version=3,
        kind="definition_approvals",
        approvals=(
            DefinitionApproval(
                metric_id="sessions",
                decided_definition=sentence,
                decision_ref="OD-100",
                approved_by_role=role,
                approved_at=date(2026, 9, 2),
                metric_commit=COMMIT,
            ),
        ),
    )


@pytest.fixture(scope="module")
def production() -> LoadedCatalog:
    return load_catalog(SEMANTIC)


def _replace(catalog: LoadedCatalog, **changes: object) -> LoadedCatalog:
    """The house way (`test_l3_l4_validation.py`): rebuild the frozen catalog field by field."""
    fields: dict[str, object] = {
        name: getattr(catalog, name) for name in catalog.__dataclass_fields__
    }
    fields.update(changes)
    return LoadedCatalog(**fields)  # pyright: ignore[reportArgumentType]


def _catalog(
    base: LoadedCatalog, metric: Metric, vault: DefinitionApprovalRegistry | None
) -> LoadedCatalog:
    return _replace(base, metrics={"sessions": metric}, definition_approvals=vault)


ROLES = frozenset({"product_analytics", "data_governance"})


# --- the four denials, one by one ----------------------------------------------------


def test_a_signed_definition_that_still_matches_is_published(production: LoadedCatalog) -> None:
    denials = definition_denials(
        _catalog(production, _metric(APPROVED), _vault()), permitted_roles=ROLES
    )
    assert denials == {}
    state = derive_lifecycle(_metric(APPROVED), owner_known=True, publication_eligible=True)
    assert state.lifecycle is Lifecycle.PUBLISHED
    assert state.definition_denial is None


def test_a_signed_definition_that_was_rewritten_makes_the_metric_pending(
    production: LoadedCatalog,
) -> None:
    """**The debt.** Approved sentence and current sentence DIFFER by one word."""
    catalog = _catalog(production, _metric(REWRITTEN), _vault())
    denials = definition_denials(catalog, permitted_roles=ROLES)
    assert denials == {"sessions": DefinitionDenial.DEFINITION_CHANGED}

    states = derive_lifecycles(catalog, source_commits=None, on=ON, permitted_roles=ROLES)
    assert states["sessions"].lifecycle is Lifecycle.PENDING
    assert PendingReason.DEFINITION_APPROVAL_STALE in states["sessions"].reasons
    assert states["sessions"].definition_denial is DefinitionDenial.DEFINITION_CHANGED
    assert not states["sessions"].is_requestable


def test_a_definition_signed_by_a_role_outside_the_policy_makes_the_metric_pending(
    production: LoadedCatalog,
) -> None:
    catalog = _catalog(production, _metric(APPROVED), _vault(role="marketing"))
    assert definition_denials(catalog, permitted_roles=ROLES) == {
        "sessions": DefinitionDenial.ROLE_NOT_PERMITTED
    }


def test_the_commit_half_is_not_measured_here_and_cannot_fire(production: LoadedCatalog) -> None:
    """Said, not hidden: the bundle has no per-file commits, so the approval's own commit is handed
    to `evaluate` and `COMMIT_MISMATCH` is unreachable from this path. CI measures it with git."""
    catalog = _catalog(production, _metric(APPROVED), _vault())
    assert (
        DefinitionDenial.COMMIT_MISMATCH
        not in definition_denials(catalog, permitted_roles=ROLES).values()
    )


def test_a_metric_nobody_signed_is_not_in_breach(production: LoadedCatalog) -> None:
    """`NO_APPROVAL` is not a reason — *"O que isto NÃO é: uma regra de permissão."* Turning it into
    one would make every unsigned metric in the catalogue pending overnight."""
    catalog = _catalog(production, _metric(REWRITTEN), None)
    assert definition_denials(catalog, permitted_roles=ROLES) == {}
    states = derive_lifecycles(catalog, source_commits=None, on=ON, permitted_roles=ROLES)
    assert PendingReason.DEFINITION_APPROVAL_STALE not in states["sessions"].reasons


def test_a_signature_for_a_metric_the_catalog_no_longer_carries_reads_changed(
    production: LoadedCatalog,
) -> None:
    """An approval of a sentence that is not there approves nothing."""
    catalog = _replace(production, metrics={}, definition_approvals=_vault())
    assert definition_denials(catalog, permitted_roles=ROLES) == {
        "sessions": DefinitionDenial.DEFINITION_CHANGED
    }


# --- the path production walks -----------------------------------------------------------


def test_the_bundle_projects_a_rewritten_definition_as_a_pending_stub(
    production: LoadedCatalog,
) -> None:
    """`build_bundle` is what `anomaly.survey` calls on the bot's real path. A stale definition
    comes out as a `PendingStub`, which `gate_2_lifecycle` refuses with `METRIC_PENDING`."""
    catalog = _catalog(production, _metric(REWRITTEN), _vault())
    bundle = build_bundle(catalog, current_commit=COMMIT, on=ON)
    assert isinstance(bundle.public["sessions"], PendingStub)
    assert bundle.lifecycles["sessions"].definition_denial is DefinitionDenial.DEFINITION_CHANGED
    assert ReasonCode.METRIC_PENDING  # the code the gate answers with; named, not `pending`


def test_the_production_vault_still_covers_every_signed_metric_today(
    production: LoadedCatalog,
) -> None:
    """The nineteen of `OD-100` against the contracts as they are: zero stale. Dated by the run —
    the day a contract is rewritten without a re-signature, this goes red and NAMES the metric."""
    roles = frozenset(production.policies[0].approval_roles) | {production.policies[0].owner_role}
    stale = definition_denials(production, permitted_roles=roles)
    assert stale == {}, stale
