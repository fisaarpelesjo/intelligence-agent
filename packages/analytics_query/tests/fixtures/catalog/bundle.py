"""A real catalog bundle for the end-to-end tests.

Test package only. Builds `001`'s own ``decision_matrix`` fixture catalog, so the
end-to-end suites run through the **real** ``evaluate()`` and the real eleven
gates rather than through a stub verdict.

That matters for what the e2e tests can claim. A stub decision proves this
feature reacts correctly to a verdict; a real bundle proves the verdict it reacts
to is the one the catalog actually produces. Only the second catches a
translation error in the bridge.

It remains fixture-backed, and says nothing about production readiness (`FR-063`).
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

from semantic_catalog.freshness.external import load_snapshot
from semantic_catalog.loader.bundle import Bundle, build_bundle
from semantic_catalog.validation.pipeline import FreshnessSnapshot

__all__ = [
    "ALLOWED_METRIC",
    "ALLOWED_SOURCE",
    "ON",
    "SCOPE",
    "STANDARD_ACCESS",
    "bundle",
    "snapshot",
]

_FIXTURES = Path(__file__).resolve().parents[4] / "semantic_catalog" / "tests" / "fixtures"
_CATALOG = _FIXTURES / "decision_matrix" / "catalog"
_FRESHNESS = _FIXTURES / "freshness"

#: The date the fixture catalog is built and evaluated on. Fixed, because a
#: moving "today" would make lifecycle and deprecation outcomes drift.
ON = date(2026, 8, 11)

#: The one combination `001`'s own matrix records as ALLOW / REQUEST_ALLOWED.
ALLOWED_METRIC = "app_sessions"
ALLOWED_SOURCE = "app_a"
STANDARD_ACCESS = ("standard",)
SCOPE = "default"


@lru_cache(maxsize=2)
def bundle() -> Bundle:
    """The fixture catalog, built once per session.

    Cached because building parses the whole tree, and the bundle is immutable.
    This caches *governed content*, never a result.
    """
    return build_bundle(_CATALOG, current_commit="fixture0", on=ON)


def snapshot(name: str = "complete.yaml") -> FreshnessSnapshot:
    """One of `001`'s freshness fixtures, by file name."""
    return load_snapshot(_FRESHNESS / name)
