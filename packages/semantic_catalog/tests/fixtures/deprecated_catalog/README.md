# tests/fixtures/deprecated_catalog

Catalog with a deprecation boundary at 2026-06-01, for segmentation tests (T090).

`catalog/` holds a self-contained miniature catalog; `freshness.yaml` is the
observed snapshot the coverage and freshness gates read, kept outside `catalog/`
because the loader refuses any file under it whose `kind` is not a governed
contract.

Four metrics, each covering one rule:

| Metric | What it proves |
|---|---|
| `fixture_metric` | Deprecated with an authored replacement and **no** continuation: before the boundary annotated, on or after refused, crossing segmented |
| `fixture_replacement` | The replacement is a live metric, and nothing substitutes it for the deprecated one |
| `fixture_pointer_metric` | Its replacement is **restricted**, so the refusal must not name it |
| `fixture_continued_metric` | A governed continuation version opens on the boundary, so the post-boundary period resolves (FR-062) |

**Unit-test fixtures only.** They never represent production data, production
approvals or integration readiness. After EXT-A readiness (T109) is declared,
fixture fallback in integration or release CI fails closed (T101).
