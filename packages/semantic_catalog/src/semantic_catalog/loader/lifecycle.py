"""Lifecycle derivation — T040 (FR-002, FR-017; data-model §5).

Lifecycle is **derived, never authored**. There is no ``status:`` field in any
metric file, and that is deliberate: a hand-written status is a claim that drifts
from the contract it describes, and the first thing it drifts into is
``published`` on a metric whose required fields were quietly cleared.

Three states, from the state diagram in data-model §5:

``pending``
    A required field is unset, the owner does not resolve, or the D-1 approval
    that makes its sources authoritative is absent (FR-076). Discoverable by
    name, refused for analysis.

``published``
    Complete contract, resolvable owner, publication-eligible sources.

``deprecated``
    A deprecation block exists. Terminal for new use; the metric stays
    resolvable for historical periods forever (FR-036, FR-061).

Deprecation is checked **first**. A deprecated metric whose source approval
lapses must not reappear as ``pending`` — pending means "on its way in", and
walking a retired metric backwards into that state would misdescribe it to every
consumer that reads the lifecycle.

``missing_fields`` carries field **names only** and never their draft values
(FR-018). Naming the gap is the point; showing the draft would defeat it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from ..contracts.definition_approval import DefinitionDenial
from ..contracts.metric import Lifecycle, Metric
from ..validation.publication import metric_eligibilities
from .load import LoadedCatalog

__all__ = [
    "LifecycleState",
    "PendingReason",
    "current_definition_of",
    "definition_denials",
    "derive_lifecycle",
    "derive_lifecycles",
]


class PendingReason(StrEnum):
    """Why a metric is not publishable. Reported, never guessed at."""

    REQUIRED_FIELDS_UNSET = "required_fields_unset"
    OWNER_UNRESOLVED = "owner_unresolved"
    SOURCE_NOT_APPROVED = "source_not_approved"
    #: The signed definition in the vault (`OD-100`) no longer covers the contract as written:
    #: `DEFINITION_CHANGED`, `COMMIT_MISMATCH` or `ROLE_NOT_PERMITTED` out of
    #: `DefinitionApprovalRegistry.evaluate`. **`NO_APPROVAL` is deliberately NOT a reason** --
    #: the vault's own words: *"O que isto NAO e: uma regra de permissao."* A metric nobody
    #: signed is not in breach; a metric somebody signed and then rewrote is.
    #:
    #: Measured 2026-09-04: `evaluate` had zero callers outside its contract file and the
    #: registry was loaded by `load.py` and read by nothing -- nineteen signatures nobody
    #: checked. This reason is the production consumer they did not have.
    DEFINITION_APPROVAL_STALE = "definition_approval_stale"


@dataclass(frozen=True, slots=True)
class LifecycleState:
    """The derived lifecycle of one metric, with the reasons behind it."""

    metric_id: str
    lifecycle: Lifecycle
    missing_fields: tuple[str, ...]
    reasons: tuple[PendingReason, ...]
    unapproved_sources: tuple[str, ...]
    #: Which of the vault's denials made the definition stale, when one did. Carried so the
    #: refusal downstream can NAME it rather than say `pending`.
    definition_denial: DefinitionDenial | None = None

    @property
    def is_pending(self) -> bool:
        return self.lifecycle is Lifecycle.PENDING

    @property
    def is_published(self) -> bool:
        return self.lifecycle is Lifecycle.PUBLISHED

    @property
    def is_requestable(self) -> bool:
        """Only ``published`` may be requested for analysis (FR-002, FR-018)."""
        return self.lifecycle is Lifecycle.PUBLISHED


def derive_lifecycle(
    metric: Metric,
    *,
    owner_known: bool,
    publication_eligible: bool,
    unapproved_sources: tuple[str, ...] = (),
    definition_denial: DefinitionDenial | None = None,
) -> LifecycleState:
    """Derive one metric's lifecycle.

    Both conditions are **required keywords with no default**. A default here
    would decide, silently and in one place, that an unowned or unapproved metric
    is publishable — which is the exact failure the derivation exists to prevent.
    """
    missing = metric.unset_required_fields()

    reasons: list[PendingReason] = []
    if missing:
        reasons.append(PendingReason.REQUIRED_FIELDS_UNSET)
    if not owner_known:
        reasons.append(PendingReason.OWNER_UNRESOLVED)
    if not publication_eligible:
        reasons.append(PendingReason.SOURCE_NOT_APPROVED)
    if definition_denial is not None:
        reasons.append(PendingReason.DEFINITION_APPROVAL_STALE)

    if metric.deprecation is not None:
        lifecycle = Lifecycle.DEPRECATED
    elif reasons:
        lifecycle = Lifecycle.PENDING
    else:
        lifecycle = Lifecycle.PUBLISHED

    return LifecycleState(
        metric_id=metric.name,
        lifecycle=lifecycle,
        missing_fields=missing,
        reasons=tuple(reasons),
        unapproved_sources=unapproved_sources,
        definition_denial=definition_denial,
    )


def derive_lifecycles(
    catalog: LoadedCatalog,
    *,
    source_commits: Mapping[str, str] | None,
    on: date,
    permitted_roles: frozenset[str] | None = None,
) -> Mapping[str, LifecycleState]:
    """Derive the lifecycle of every loaded metric, keyed by metric name.

    ``source_commits`` maps a source id to the commit that last touched its file
    — ADR 0033. It replaced ``current_commit`` here rather than joining it: this
    parameter only ever fed the freshness check, so keeping both names would have
    left the misleading one alive next to the correct one.
    """
    owner_ids: frozenset[str] = (
        frozenset(o.id for o in catalog.owners.owners) if catalog.owners else frozenset()
    )
    eligibility = metric_eligibilities(
        catalog,
        source_commits=source_commits,
        on=on,
        permitted_roles=permitted_roles,
    )
    denials = definition_denials(catalog, permitted_roles=permitted_roles)
    return {
        name: derive_lifecycle(
            metric,
            owner_known=metric.owner in owner_ids,
            publication_eligible=eligibility[name].publishable,
            unapproved_sources=eligibility[name].unapproved_sources,
            definition_denial=denials.get(name),
        )
        for name, metric in catalog.metrics.items()
    }


def current_definition_of(catalog: LoadedCatalog, metric_id: str) -> str | None:
    """The sentence a definition approval RESTATES, read where the vault's own node reads it.

    ``versions[0].content.limitations[0]`` -- `test_definition_approvals_current.py` derived it
    that way when the vault was signed, and a second derivation here would let the CI node and
    the production check disagree about which sentence the signature covers.
    """
    metric = catalog.metrics.get(metric_id)
    if metric is None or not metric.versions:
        return None
    limitations = metric.versions[0].content.limitations
    return str(limitations[0]) if limitations else None


def definition_denials(
    catalog: LoadedCatalog, *, permitted_roles: frozenset[str] | None
) -> Mapping[str, DefinitionDenial]:
    """Every signed definition that no longer covers its contract, by metric -- the vault, RUN.

    Only metrics that HAVE an approval are evaluated (`NO_APPROVAL` is not a breach). A signed
    metric the catalog no longer carries, or whose contract has no limitation to restate, reads
    `DEFINITION_CHANGED`: the approved sentence is not there.

    **The commit half is NOT measured here, and this says so rather than pretending.** The
    approval binds to `metric_commit`, the commit that last changed the metric's own file; the
    bundle is built with ONE commit (the freshness approval's) and carries no per-file commits,
    so `evaluate` is handed the approval's own commit -- which makes `COMMIT_MISMATCH`
    unreachable from this path. The CI node `test_definition_approvals_current.py` measures
    that half with `git log`; production measures the sentence and the role.
    """
    approvals = catalog.definition_approvals
    if approvals is None or not approvals.approvals:
        return {}
    found: dict[str, DefinitionDenial] = {}
    for approval in approvals.approvals:
        current = current_definition_of(catalog, approval.metric_id)
        if current is None:
            found[approval.metric_id] = DefinitionDenial.DEFINITION_CHANGED
            continue
        denial = approvals.evaluate(
            approval.metric_id,
            current_definition=current,
            metric_content_commit=approval.metric_commit,
            permitted_roles=permitted_roles,
        )
        if denial is not None:
            found[approval.metric_id] = denial
    return found
