"""Governed multichannel integration.

Adds the **transport boundary** to the governed stack and nothing else.
`semantic_catalog` decides whether a question may be answered; `analytics_query`
executes a permitted request; `analytics_interaction` interprets a business
question and assembles a channel-agnostic answer. This package receives a message
from an external channel, proves it is authentic, resolves the sender to a
governed principal, normalises it into a canonical envelope, hands it to the
interaction boundary unchanged, and returns whatever came back — rendered for that
channel with every governed string, value, code, caveat, provenance element and
limitation preserved byte-for-byte.

It re-implements no catalog gate, no execution gate and no interpretation rule,
holds no analytical capability, and originates no message.

**A channel is a transport, never an authority.** No contract field, parameter or
header can assert authenticity, identity, tenant, language, reference date,
authorisation or a governed limit — the absence is the mechanism.

See ``specs/004-multichannel-integration/`` for the governing specification.
"""

__version__ = "0.1.0"
