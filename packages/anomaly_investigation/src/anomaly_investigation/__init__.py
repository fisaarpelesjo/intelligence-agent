"""Governed anomaly detection and investigation.

Adds the **judgement that a measured movement is worth a person's time** to the
governed stack, and nothing else. `semantic_catalog` decides whether a question may
be answered; `analytics_query` executes a permitted request; `analytics_interaction`
interprets a business question and assembles a channel-agnostic answer;
`channel_integration` carries a question in and an answer out.

This package is the first that looks at data **without a question**. That is its
whole novelty and its whole risk, so two constraints govern everything in it:

**Detecting is not claiming a cause.** It may say *what* moved, *by how much*,
*against which baseline*, and *which segment carried the movement*. It may not say
*why*. Every emitted output carries the baseline's required warning, transported
byte-for-byte and never composed here.

**Detecting is not delivering.** Nothing here originates: no scheduler, no timer,
no thread, no event loop, no outbox write, no send. A run is **called**, and it
receives its instant as a parameter. The outbox, the workers and the delivery are
the owner's item 8 and live elsewhere, on a substrate that does not exist yet.

It re-implements no catalog gate, no execution ceiling, no interpretation rule and
no comparison arithmetic. A period-over-period movement is **asked for** through
the existing seams, never divided here.

It ends at step 5 of the baseline's eleven-step pipeline and hands out a candidate
finding with its evidence. Nothing scores it, narrates it or sends it.

See ``specs/005-anomaly-investigation/`` for the governing specification.
"""

__version__ = "0.1.0"
