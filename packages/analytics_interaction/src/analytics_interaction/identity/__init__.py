"""The value-free interpretation identity and the authorization-context
fingerprint carried alongside it. Neither is derived from raw question text.

The split is `002`'s security amendment, applied before the same mistake can be
made here. Identity stays **principal-independent** so audit can see the same
question asked twice; the fingerprint carries the authorization dimension so a
contract issued to one principal is refused when presented by another. Folding
them together would destroy the first property; dropping the fingerprint would
destroy the second.
"""

from .authorization_fingerprint import (
    FINGERPRINT_INPUTS,
    derive_authorization_fingerprint,
    fingerprints_match,
)
from .interpretation_identity import (
    IDENTITY_MEMBERS,
    canonical_intent,
    derive_interpretation_identity,
)

__all__ = [
    "FINGERPRINT_INPUTS",
    "IDENTITY_MEMBERS",
    "canonical_intent",
    "derive_authorization_fingerprint",
    "derive_interpretation_identity",
    "fingerprints_match",
]
