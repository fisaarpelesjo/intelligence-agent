"""Bundle build and ``catalog_release_id`` — T043 (FR-018; library contract §1.1).

Two projections from one load:

``INTERNAL``
    Everything, drafts included. Stewards and CI only.

``PUBLIC``
    Published metrics in full; pending metrics as :class:`PendingStub`. The
    unsafe fields are **stripped here and the bundle is serialised without
    them** — absent, not present-but-hidden (R-8).

``catalog_release_id`` is the content hash of the serialised public bundle **and of
the authored catalog behind it**. Two consequences follow, and both are the reason
for content-addressing rather than a counter: the same content always yields the
same id, so a rebuild is provably a no-op; and **any** authored change of any class
yields a new id, so a release can never be silently edited under a reused
identifier (FR-075, R-12).

The second half was not true until 2026-09-05 (`OD-124` (a)). The id hashed the
public projection alone, and **45 of the 80 files under ``semantic/`` could be
deleted without moving it** — every access tag, source, dimension, comparability
rule, glossary term, reason message, definition approval and visibility approval.
An access-tag change that flips a decision from ALLOW to DENY produced the same id,
and :mod:`release_state` refuses a repeated id as "nothing to publish", so the
corrective release FR-075 demands could not be published at all. The id now covers
:func:`serialise_authored` as well. What stays outside, on purpose: files the loader
does not read (READMEs, ``examples/``) and the machine-specific ``files`` paths.

Serialisation is canonical — sorted keys, fixed separators, UTF-8 preserved — so
the hash depends on content and not on dict ordering or a Python version.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel

from ..contracts.policy import CatalogPolicy, PolicySet, PolicyUnresolvableError
from .lifecycle import LifecycleState, derive_lifecycles
from .load import LoadedCatalog, load_catalog
from .projection import MetricView, PendingStub, project_metric
from .visibility import resolve_visibility

__all__ = [
    "Bundle",
    "Projection",
    "build_bundle",
    "compute_release_id",
    "serialise_authored",
    "serialise_public",
]


class Projection(StrEnum):
    """Which view of the catalog a consumer receives."""

    PUBLIC = "public"
    INTERNAL = "internal"


@dataclass(frozen=True, slots=True)
class Bundle:
    """Both projections plus the content-addressed release id."""

    public: Mapping[str, MetricView | PendingStub]
    internal: LoadedCatalog
    lifecycles: Mapping[str, LifecycleState]
    release_id: str

    @property
    def pending(self) -> tuple[str, ...]:
        return tuple(sorted(n for n, p in self.public.items() if isinstance(p, PendingStub)))

    @property
    def published(self) -> tuple[str, ...]:
        return tuple(sorted(n for n, p in self.public.items() if isinstance(p, MetricView)))


def serialise_public(public: Mapping[str, MetricView | PendingStub]) -> str:
    """Canonical JSON for the public projection.

    Sorted keys and fixed separators make the output a function of content
    alone. ``ensure_ascii=False`` keeps pt-BR text readable in the artifact
    rather than escaping it into noise.
    """
    payload: dict[str, Any] = {
        name: projection.to_public_dict() for name, projection in sorted(public.items())
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _plain(value: object) -> object:
    """Pydantic models to JSON-mode dicts, mappings sorted, tuples to lists -- recursively."""
    if value is None:
        return None
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        return {
            str(key): _plain(item)
            for key, item in sorted(mapping.items(), key=lambda kv: str(kv[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in cast("Sequence[object]", value)]
    return value


def serialise_authored(catalog: LoadedCatalog) -> str:
    """Canonical JSON of everything the loader read — the half the release id was missing.

    Every registry of :class:`LoadedCatalog` takes part, including the ones the public
    projection never shows (access tags, approvals, reason messages): a change there
    changes what the catalog DECIDES, and two catalogs that decide differently must not
    share an id. ``files`` is left out because it holds absolute paths, which would make
    the id a function of the machine rather than of the content.
    """
    payload = {
        "access_tags": _plain(catalog.access_tags),
        "approvals": _plain(catalog.approvals),
        "comparability_rules": _plain(catalog.comparability_rules),
        "definition_approvals": _plain(catalog.definition_approvals),
        "dimensions": _plain(catalog.dimensions),
        "freshness_approvals": _plain(catalog.freshness_approvals),
        "glossary_terms": _plain(catalog.glossary_terms),
        "metrics": _plain(catalog.metrics),
        "owners": _plain(catalog.owners),
        "policies": _plain(catalog.policies),
        "reason_messages": _plain(catalog.reason_messages),
        "sources": _plain(catalog.sources),
    }
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )


def compute_release_id(
    public: Mapping[str, MetricView | PendingStub], authored: LoadedCatalog
) -> str:
    """``sha256:<hex>`` over the serialised public bundle AND the authored catalog.

    Both halves, newline-separated, so that a change in either moves the id and a
    rebuild of identical content does not (`OD-124` (a), measured 2026-09-05).
    """
    material = serialise_public(public) + "\n" + serialise_authored(authored)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _effective_policy(catalog: LoadedCatalog, on: date) -> CatalogPolicy:
    """The policy governing this build.

    No policy, or several, raises rather than defaulting: a bundle built under a
    policy nobody approved is unauditable (FR-072).
    """
    if not catalog.policies:
        raise PolicyUnresolvableError(
            "no catalog policy is authored; a bundle cannot be built without one"
        )
    return PolicySet(policies=catalog.policies).resolve_effective(on)


def build_bundle(
    root: Path | LoadedCatalog,
    *,
    current_commit: str,
    on: date,
    proposer_role: str | None = None,
    source_commits: Mapping[str, str] | None = None,
) -> Bundle:
    """Build both projections and the release id.

    ``current_commit`` is supplied by the caller rather than read from Git: the
    library holds no repository handle, and a **visibility** approval must be
    checked against the commit the *caller* is publishing.

    ``source_commits`` maps a source id to the commit that last modified that
    source's own file, and it is what the **freshness** check uses — ADR 0033.
    The two are separate parameters because they answer different questions, and
    conflating them is the defect that ADR records: a freshness approval promised
    to bind to the content it approved and bound to repository state instead.

    **``None`` FALLS BACK to ``current_commit``, and that is a DECLARED TRANSITION
    rather than a design.** ADR 0033 changed the comparand; it did not schedule the
    conversion of every caller that predates it. Measured while executing the ADR:
    a hard cutover fails **142** nodes across fifteen files of `001`'s own suite,
    every one of them a fixture catalog that is not in Git at all and for which
    "the commit that last touched this source's file" has no meaning.

    So the rule is: **a caller that states content commits gets content binding; a
    caller that does not gets the comparand it always had.** Nothing is loosened —
    under the fallback the outcome is byte-for-byte what it was before the ADR.

    **THE DEBT IS REAL AND IS NAMED HERE.** While those 142 nodes ride the fallback,
    `001`'s suite mostly exercises the OLD comparand, so the new one is thin on
    coverage. Converting them is its own piece of work and is not this ADR's.
    `test_the_production_caller_binds_to_content.py` asserts the one thing that
    keeps the transition from quietly becoming permanent where it matters: the CLI
    — the only production caller — supplies the mapping.

    Supplied by the caller for the same reason ``current_commit`` is: reading Git
    is a repository act, and this library holds no repository handle by design.
    """
    catalog = load_catalog(root) if isinstance(root, Path) else root
    policy = _effective_policy(catalog, on)
    permitted = frozenset(policy.approval_roles) | {policy.owner_role}

    lifecycles = derive_lifecycles(
        catalog,
        source_commits=(
            source_commits
            if source_commits is not None
            else dict.fromkeys(catalog.sources, current_commit)
        ),
        on=on,
        permitted_roles=permitted,
    )
    owner_ids: frozenset[str] = (
        frozenset(o.id for o in catalog.owners.owners) if catalog.owners else frozenset()
    )

    public: dict[str, MetricView | PendingStub] = {}
    for name, metric in catalog.metrics.items():
        visibility = resolve_visibility(
            name,
            policy=policy,
            approvals=catalog.approvals,
            current_commit=current_commit,
            on=on,
            proposer_role=proposer_role,
        )
        public[name] = project_metric(
            metric,
            lifecycles[name],
            visibility=visibility,
            owner_known=metric.owner in owner_ids,
        )

    return Bundle(
        public=public,
        internal=catalog,
        lifecycles=lifecycles,
        release_id=compute_release_id(public, catalog),
    )
