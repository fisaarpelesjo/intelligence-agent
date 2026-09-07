"""Catalog fixtures — T147. **TEST-ONLY.**

`001`'s production catalog is unpublishable by design while `D-1` and `D-8` are
open: every request against it stops at gate 2, and gates 3 to 5 are
unreachable. Faking an approval in the production catalog to make them reachable
would be inventing governance history.

So the suites use **`001`'s own fixture catalog**, reached by path rather than
copied — ``packages/semantic_catalog/tests/fixtures/decision_matrix/catalog``
together with its freshness snapshots. A copy would drift from the original, and
the point of the cross-feature tests is that a decision from the *real*
evaluator works.

This module names the paths so the three suites that need them agree on one
location, and so a move upstream breaks in one place rather than three.

A fixture is never evidence for an external record. `001`'s fixture catalog is
its test data, not a published release.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import analytics_interaction

__all__ = ["CATALOG", "FRESHNESS", "SNAPSHOT_COMPLETE"]

_TESTS = (
    Path(inspect.getfile(analytics_interaction)).resolve().parents[3] / "semantic_catalog" / "tests"
)

#: `001`'s published fixture catalog, with its own approvals.
CATALOG = _TESTS / "fixtures" / "decision_matrix" / "catalog"

#: Its freshness snapshots — one per observed state the coverage and freshness
#: gates distinguish.
FRESHNESS = _TESTS / "fixtures" / "freshness"

#: The healthy baseline every other branch contrasts against.
SNAPSHOT_COMPLETE = FRESHNESS / "complete.yaml"
