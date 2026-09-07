# `anomaly_investigation`

**What deserves attention when nobody asked.**

The fifth package of the governed stack, and the first that looks at data **without
a question**. It produces a **candidate finding** — a measured movement, the
baseline it was compared against, both windows, the rule that fired, and the
freshness observation that permitted it — and stops there.

## What it does not do, and why each absence is load-bearing

**It does not claim a cause.** The baseline declares `automatic_claims_allowed:
false` and restricts language to `correlation`, `temporal_association` and
`hypothesis`. Every emitted output carries the required warning, **transported
byte-for-byte and never composed here**. There is no `cause` field, no `driver`, no
`root_cause` — the shape refuses before any test runs.

**It originates nothing.** No scheduler, no timer, no thread, no event loop, no
outbox write, no send. A run is *called* and receives its instant as a parameter.
`tests/security/test_originates_nothing.py` walks the syntax tree and refuses each
one — and it was written **before** the code it guards.

**It computes no date and divides no number.** Windows come from the catalog; a
period-over-period movement is *asked for* through `003`'s comparison surface.

**It does not score, rank, narrate or suppress.** Those are steps 6 to 9 of the
baseline's eleven-step pipeline. This feature implements steps 1 to 5 and hands out
the candidate.

## Why it is a separate package

Measured, not preferred: `channel_integration`'s `test_reactive_only.py` walks that
package's syntax tree and refuses every scheduler and notify primitive. Detection
could not live there without breaking that node or pretending to be a channel
concern.

## Layout

```
src/anomaly_investigation/
└── contracts/          # five entities and the reason-code namespace -- built
tests/
├── contract/           # the namespace is disjoint; the warning is the baseline's
├── security/           # test_originates_nothing.py -- proves SC-004
└── unit/               # the contracts refuse incomplete evidence
```

`freshness/`, `detect/`, `investigate/` and `ports/` are named by
`specs/005-anomaly-investigation/plan.md` and are **not built yet**. Phase 2 —
freshness and completeness — comes before Phase 3, and that ordering is deliberate:
a detector built first and guarded second is a detector that fired on bad data at
least once.

## Running the tests

The four sibling packages are installed editable in the repository's `.venv`. **This
one is not**, deliberately — installing it would modify the interpreter a running
bot uses. `tests/conftest.py` prepends the source root instead.

```
.venv/Scripts/python -m pytest packages/anomaly_investigation/tests -q
```

See `specs/005-anomaly-investigation/` for the governing specification, and
`docs/intelligence-agent.yaml` `proactive_insights` for the baseline this feature
implements the first block of.
