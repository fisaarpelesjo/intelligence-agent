"""Semantic fingerprint — T086 (FR-033).

A hash over exactly the fields whose change alters what a metric *means*. If the
hash of an existing version block moves and no new version was appended, the
build fails naming the fields that moved (T087). That is what turns FR-033 from
a rule people remember into one they cannot merge past.

**The input set is closed and is not defined here.** It comes from
:data:`~semantic_catalog.contracts.classification.FINGERPRINT_INPUTS`, the
executable form of catalog-file-contracts §4.4 — every Semantic-class field plus
the three Lifecycle fields that alter as-of resolution (``version``,
``effective_from``, ``effective_to``). Restating the set here would create a
second place for it to drift, and an ambiguous input set would leave the gate
protecting SC-021 protecting an undefined thing.

Two consequences of reading the classification rather than a hand-written list:

* a newly added contract field with **no** classification raises
  :class:`~semantic_catalog.contracts.classification.UnclassifiedFieldError` the
  first time anything is fingerprinted, instead of silently falling outside the
  hash;
* widening or narrowing the fingerprint requires editing §4.4 and its executable
  map together, which is a reviewed change rather than an incidental one.

**A detector, not an oracle** (research §R-6). It proves declared-semantic fields
did not change. It cannot know whether a Descriptive prose edit changed the
concept — ``content.description`` is not fingerprinted, deliberately, because a
description is allowed to improve. Owner-plus-reviewer approval stays mandatory
for every change regardless of a green fingerprint; treating this hash as
sufficient would manufacture exactly the false confidence it exists to prevent.

Determinism: canonical JSON with sorted keys over the ``mode="json"`` dump, so
the digest depends on authored content and not on dict ordering, Python version
or in-memory type. Two identical catalogs fingerprint identically forever.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from ..contracts._base import CatalogModel
from ..contracts.classification import FINGERPRINT_INPUTS, class_of
from ..contracts.metric import Metric, MetricVersion

__all__ = [
    "FINGERPRINT_INPUTS",
    "digest",
    "fingerprint",
    "fingerprint_inputs",
    "metric_fingerprints",
    "version_fingerprint",
]


def digest(inputs: Mapping[str, Any]) -> str:
    """``sha256:<hex>`` over canonical JSON of ``inputs``."""
    canonical = json.dumps(inputs, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def fingerprint_inputs(model: CatalogModel) -> dict[str, Any]:
    """The fingerprinted fields of ``model``, keyed ``Model.field``.

    Every declared field is looked up in the classification first — including
    the ones that will be discarded. That lookup is the closure guarantee: an
    unclassified field raises here rather than quietly contributing nothing.
    """
    model_name = type(model).__name__
    dumped: dict[str, Any] = model.model_dump(mode="json")
    inputs: dict[str, Any] = {}
    for field_name in type(model).model_fields:
        path = f"{model_name}.{field_name}"
        class_of(path)  # raises on an unclassified field; never defaulted
        if path in FINGERPRINT_INPUTS:
            inputs[path] = dumped[field_name]
    return inputs


def fingerprint(model: CatalogModel) -> str:
    """Digest over one model's own fingerprinted fields."""
    return digest(fingerprint_inputs(model))


def version_fingerprint(metric: Metric, version: MetricVersion) -> str:
    """Digest for one version block, metric-level semantics included.

    ``grain_family`` and ``retention`` live on the metric rather than the
    version, and changing either changes what **every** version means. Folding
    them in is why switching a metric from day- to cohort-grained fires the gate
    on each existing block, instead of on none of them.
    """
    return digest({**fingerprint_inputs(metric), **fingerprint_inputs(version)})


def metric_fingerprints(metric: Metric) -> Mapping[int, str]:
    """Every version block's fingerprint, keyed by version number."""
    return {version.version: version_fingerprint(metric, version) for version in metric.versions}
