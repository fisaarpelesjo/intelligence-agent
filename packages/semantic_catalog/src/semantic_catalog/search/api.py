"""Library discovery API — T046 (FR-018; library contract §1.2).

``get_metric`` returns a **closed union**: ``MetricView | PendingStub |
NotGoverned``. Closed matters. An open return type — a dict, an optional model,
``None`` — pushes the three-way distinction into every caller, and the first
caller to collapse it treats "pending" as "missing" and sends a user away to
build their own number (R-8).

``access`` gates every result, pending stubs included. A pending metric's name is
not public merely because its definition is withheld: the same authorisation gate
governs both, and a denial is indistinguishable from "not governed" so that a
refusal discloses nothing about what exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..contracts.access_tag import AccessTagRegistry, PrincipalType, TagDenial
from ..loader.bundle import Bundle
from ..loader.projection import MetricView, PendingStub
from .outcomes import Ambiguous, NotGoverned, Resolved, SearchHit, resolve_outcome
from .resolve import SearchIndex, build_index

__all__ = [
    "AccessContext",
    "CatalogApi",
    "GetMetricResult",
    "authorize",
]

GetMetricResult = MetricView | PendingStub | NotGoverned


@dataclass(frozen=True, slots=True)
class AccessContext:
    """Who is asking, in the vocabulary the access-tag registry understands.

    Not a bag of granted tag names: the registry decides authorisation from the
    principal type, the authorisation scope and the evaluation date, and passing
    a pre-computed answer would move that decision out of governed data.
    """

    principal_type: PrincipalType
    authorization_scope: str
    on: date


def authorize(
    tag_id: str,
    registry: AccessTagRegistry | None,
    context: AccessContext,
) -> TagDenial | None:
    """``None`` authorises. An absent registry denies everything.

    Deny-by-default is not configurable here: with no registry there is no
    defined input domain, so "authorised" would mean whatever the caller passed
    in (FR-073).
    """
    if registry is None:
        return TagDenial.UNKNOWN
    return registry.authorize(
        tag_id,
        principal_type=context.principal_type,
        authorization_scope=context.authorization_scope,
        on=context.on,
    )


@dataclass(frozen=True, slots=True)
class CatalogApi:
    """Discovery over one built bundle.

    Built from a :class:`Bundle` rather than a path so the release a caller
    searches is the release they resolved against — searching one build and
    reading another is how a consumer ends up quoting a definition that is no
    longer current.
    """

    bundle: Bundle
    index: SearchIndex

    @classmethod
    def from_bundle(cls, bundle: Bundle) -> CatalogApi:
        return cls(bundle=bundle, index=build_index(bundle.internal))

    def _visible(self, metric_id: str, access: AccessContext) -> MetricView | PendingStub | None:
        projection = self.bundle.public.get(metric_id)
        if projection is None:
            return None
        metric = self.bundle.internal.metrics.get(metric_id)
        if metric is None:
            return None
        if authorize(metric.access, self.bundle.internal.access_tags, access) is not None:
            return None
        return projection

    def get_metric(self, name: str, *, access: AccessContext) -> GetMetricResult:
        """Resolve an exact canonical identifier.

        An unauthorised metric returns :class:`NotGoverned`, identical to one
        that does not exist. Distinguishing them would let a caller enumerate
        the catalog by watching which refusals differ.
        """
        projection = self._visible(name, access)
        if projection is None:
            return NotGoverned(query=name)
        return projection

    def search(self, query: str, *, access: AccessContext) -> tuple[SearchHit, ...]:
        """Search pt-BR terms. Several matches return several hits (FR-016).

        Returns an empty tuple for a non-match; callers wanting the explicit
        three-way answer use :meth:`resolve`, which never collapses them.
        """
        outcome = resolve_outcome(query, self.index)
        if isinstance(outcome, NotGoverned):
            return ()
        candidates = (outcome.candidate,) if isinstance(outcome, Resolved) else outcome.candidates
        hits: list[SearchHit] = []
        for candidate in candidates:
            projection = self._visible(candidate.metric_id, access)
            if projection is None:
                continue
            hits.append(
                SearchHit(
                    metric_id=candidate.metric_id,
                    projection=projection,
                    candidate=candidate,
                )
            )
        return tuple(hits)

    def resolve(self, query: str, *, access: AccessContext) -> Resolved | Ambiguous | NotGoverned:
        """The three-way outcome, after access filtering.

        Filtering happens **before** the shape is decided, so an ambiguity the
        caller is not authorised to see does not surface as an ambiguity. If
        exactly one authorised candidate survives, that is a resolution.
        """
        outcome = resolve_outcome(query, self.index)
        if isinstance(outcome, NotGoverned):
            return outcome

        candidates = (outcome.candidate,) if isinstance(outcome, Resolved) else outcome.candidates
        visible = tuple(c for c in candidates if self._visible(c.metric_id, access) is not None)

        if not visible:
            return NotGoverned(query=query)
        if len(visible) == 1:
            return Resolved(query=query, candidate=visible[0])
        return Ambiguous(query=query, candidates=visible)
