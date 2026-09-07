# tests/fixtures/versioned_catalog

Frozen catalog containing definition changes, for as-of resolution tests (T090).

`catalog/` holds a self-contained miniature catalog; `freshness.yaml` is the
observed snapshot the coverage and freshness gates read, kept outside `catalog/`
because the loader refuses any file under it whose `kind` is not a governed
contract.

`fixture_metric` is redefined twice — @1 to 2025-06-30, @2 to 2025-09-30, @3
open from 2025-10-01 — so a range can sit before a change, after one, or across
one or two of them. `fixture_stable_metric` never moves, and is the control:
a range inside it must produce one segment and no caveat.

**Unit-test fixtures only.** They never represent production data, production
approvals or integration readiness. After EXT-A readiness (T109) is declared,
fixture fallback in integration or release CI fails closed (T101).
