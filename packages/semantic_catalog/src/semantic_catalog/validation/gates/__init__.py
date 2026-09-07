"""Ordered decision gates — Phase 6 (decision-contract §4).

One module per gate. The order they run in lives in ``validation/pipeline.py``
and is load-bearing, not stylistic: authorisation runs before combination so a
refusal never discloses the shape of a metric the requester may not see.
"""
