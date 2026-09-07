"""Governed analytics query.

Adds **execution** to the governed catalog and nothing else. `semantic_catalog`
decides whether a question may be answered; this package takes a permitted
decision, compiles it into a structurally constrained query, executes it
read-only against the `semantic` dataset under enforced ceilings, and supplies
the data revisions that advance that decision to `FINAL`.

It re-implements none of the catalog's eleven governed gates.

See ``specs/002-analytics-query/`` for the governing specification and plan.
"""

__version__ = "0.1.0"
