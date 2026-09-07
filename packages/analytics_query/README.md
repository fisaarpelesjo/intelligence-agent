# analytics-query

Governed analytics query for the `intelligence-agent`. Adds **execution** to the semantic catalog —
and nothing else.

`semantic-catalog` decides whether a question may be answered and returns a decision that is
deliberately `PRE_EVIDENCE`, because its gates read no data. This package takes a permitted decision,
compiles it into a structurally constrained query, executes it read-only against the `semantic`
dataset under enforced byte, row and time ceilings, verifies the result's shape against what was
validated, and supplies the data revisions that advance that same decision to `FINAL`.

It re-implements none of the catalog's eleven governed gates. The catalog is called, never copied.

## Status

**Implementation in progress. Not production-ready, and no production readiness is claimed.**

The feature is fail-closed on three independent grounds today:

- no source is publishable, so no metric can be answered;
- the governed observation read is unavailable;
- no approved query policy exists, so policy resolution refuses every request.

Each is an external dependency recorded in `specs/002-analytics-query/tasks.md`. None is closed by
any test in this package: fixtures prove internal behaviour and are never evidence for an external
capability.

## Boundaries

| Property | How it holds |
|---|---|
| No unrestricted SQL | Values reach the warehouse only as bound parameters; three independent guards, the last of them IAM |
| `semantic` dataset only | Table references are pattern-restricted; no `raw`, `staging` or `core` grant exists |
| No credential here | Supplied by the deployment, confined to `adapters/bigquery/`, never read, stored, logged or embedded |
| No business values at rest | The execution ledger records identity, cost, timings, status and revisions — never a figure |
| Authorization before cost | An unauthorized request performs no warehouse read, acquires no ledger entry and is told no policy limit |

## Layout

```
src/analytics_query/
├── contracts/       request, policy, result, provenance, audit, reason codes
├── authorization/   preflight — runs before any cost is incurred
├── policy/          governed QueryPolicy resolution, fail-closed
├── identity/        normalised query identity
├── observations/    self-read freshness, coverage and revisions
├── compile/         structural construction and the emitted-text guards
├── execution/       dry run, bounded execution, shape, ledger
├── results/         assembly and minimum-aggregation suppression
├── decision/        catalog decision → final analytics decision
├── audit/           synchronous fail-closed emission
├── messages/        deterministic stored pt-BR wording
├── compliance/      additive readiness aggregation
├── adapters/bigquery/   the only module importing the vendor client
└── cli/             read-only steward commands
```

## Development

```bash
python -m pip install -e "packages/semantic_catalog[dev]"   # upstream, install first
python -m pip install -e "packages/analytics_query[dev]"

python -m ruff format --check packages/analytics_query
python -m ruff check packages/analytics_query
cd packages/analytics_query && python -m pyright && cd ../..
python -m pytest packages/analytics_query -q
```

`semantic-catalog` is a path dependency inside this monorepo and is not published, so it must be
installed editable before this package.

## Governance

The specification, plan, contracts and task graph live in `specs/002-analytics-query/`. Governed
content owned by this feature — the operator allowlist, the dimension-type vocabulary, the query
policy and the pt-BR message registry — lives in `query_governance/` at the repository root.
