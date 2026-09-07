"""Natural-language analytics interaction.

Adds **interpretation and presentation** to the governed stack and nothing else.
`semantic_catalog` decides whether a question may be answered; `analytics_query`
executes a permitted request and says what the number is made of. This package
takes a business question in pt-BR, resolves it exclusively against the governed
vocabulary, constructs the governed `AnalyticsQuery` deterministically, submits
it through `analytics_query`'s public composed entry point, and assembles an
evidence-backed answer from stored governed content.

It re-implements no catalog gate and no execution gate, generates no query text,
and holds no state between turns.

See ``specs/003-nl-analytics-interaction/`` for the governing specification.
"""

__version__ = "0.1.0"
