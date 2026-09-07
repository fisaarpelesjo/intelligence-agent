# `insights_prioritisation`

**Which of the things that deserve attention deserves it first.**

The sixth package of the governed stack. `005` produces **candidate findings** — a
measured movement, its baseline, both windows, the rule that fired and the freshness
observation that permitted it. This package puts them **in an order**, and stops there.

## Why this file exists at all, which is a finding rather than a formality

It did not exist until 2026-08-27, and `pyproject.toml` had declared `readme =
"README.md"` since the package was created. **The package was therefore not
installable** — `pip install -e .` fails with *"Readme file does not exist"* — and
nothing caught it, because every gate runs the suite from this directory through
pytest's own rootdir and never through an install. A package whose tests pass and whose
build fails is a package nobody has actually assembled.

It was found when the bot harness was wired to import this package and could not.

## What it does

**It orders findings term by term, and never by a composed score.** The note is
`(magnitude x confidence, reach x confidence)`, compared in that order. A single number
would answer *how important* without saying **which ingredient made it so** — and the
decision that produced this shape, `D-A` and `D-A2` of 2026-08-27, is written into the
tests rather than into a comment.

**Direction is a filter, not a component.** A fall and a rise do not compete inside one
rule.

**Confidence multiplies each term rather than a total.** A large, doubtful finding
**descends and stays visible**; it is never vetoed. The factor is the
`completeness_ratio` the `FreshnessRecord` already carries, and the output declares
`weighted_by = data_completeness_ratio` — because that measures **completeness of data**
and not **statistical certainty of the anomaly**, and calling it "confidence" without
saying what was measured is exactly the defect class this repository hunts.

**A `None` confidence refuses**, with `PRIORITY_CONFIDENCE_NOT_MEASURED`, instead of
assuming `1.0`. Assuming full confidence for something nobody measured is the
substitution-of-absence-by-zero defect in the other direction.

## What it does not do, and why each absence is load-bearing

**It originates nothing.** No scheduler, no timer, no thread, no outbox, no send —
asserted by walking the syntax tree, not by prose.

**It computes no figure.** A mean and a standard deviation are *figures*, and `FR-003`
of `005` requires every figure to arrive through the `002` and `003` seams. This package
may not compute one on its own.

**It has a namespace of refusal codes proved disjoint from the five that came before**,
by set intersection rather than by a prefix convention.

**A component carries a VALUE or a NAMED ABSENCE, exactly one of the two**, and
construction with neither is refused by the contract rather than by a test.

## What it answers today, measured rather than promised

**Every finding comes back NOT PRIORITISABLE, with each component naming its own
absence.** Both readers answer `None`:

* **magnitude** needs a mean per metric, which is a figure and reaches this package only
  through the `002`/`003` seams;
* **reach** is read from an investigation, which `005` does not yet produce.

`005` **does** produce a candidate against the real warehouse — that closed on
2026-08-27 — so the input exists. What does not exist is a component that can be read
from it. The day one becomes obtainable, the integration node goes **red**, and that is
its function.

See `specs/006-insights-and-prioritisation/` for the governing specification.
