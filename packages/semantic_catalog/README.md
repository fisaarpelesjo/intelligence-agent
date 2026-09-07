# semantic_catalog

Library and steward CLI for the governed semantic catalog.

- Specification: `specs/001-semantic-catalog/spec.md`
- Plan: `specs/001-semantic-catalog/plan.md`
- Tasks: `specs/001-semantic-catalog/tasks.md`

This package creates no BigQuery object, contains and executes no DDL, and holds
no BigQuery write grant. `semantic.source_freshness` and
`semantic.metric_availability` are read-only external contracts.
