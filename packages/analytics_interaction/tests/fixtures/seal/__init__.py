"""A synthetic sealing provider — T147. **TEST-ONLY.**

`D-21` is undeclared. **No key material exists anywhere in this repository**, and
none is provisioned here — what follows is a stand-in that makes tampering
detectable in a test and is explicitly not a proposal for what `D-21` should
govern.

Every value carries :data:`FIXTURE_MARKER` in its own text, so a reader
encountering one in a traceback sees what it is. `T113`'s scan asserts the marker
appears in no `src/` module, no readiness record and no governed content file.

The construction is a plain SHA-256 over ``key || preimage``. `003`'s production
port declares **no algorithm at all**, precisely because that decision is not
this feature's to make — so the choice here is a fixture's convenience and
carries no weight.

A fixture is never evidence for an external record. This one especially: a
sealing suite passing green is the single most tempting thing in this feature to
read as "`D-21` is handled".
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from analytics_interaction.contracts.clarification import Seal

__all__ = ["FIXTURE_ALGORITHM", "FIXTURE_KEY", "FIXTURE_KEY_ID", "FIXTURE_MARKER", "SyntheticSeal"]

#: Stamped into every synthetic value here.
#:
#: The **same string** the clarification fixtures use, deliberately. Two markers
#: for one piece of key material would mean the `src/` leak scan and the
#: governance scan each covered half of it, and the half nobody scanned is the
#: half that leaks.
FIXTURE_MARKER = "fixture-only-not-provisioned"

#: A literal rather than a generated value, on purpose. A generated key would
#: vary per run and make seal comparisons irreproducible — and generation is
#: itself one of the things the key scan forbids anywhere near this feature.
FIXTURE_KEY = f"{FIXTURE_MARKER}-key-material"
FIXTURE_KEY_ID = f"{FIXTURE_MARKER}-key-1"
FIXTURE_ALGORITHM = f"{FIXTURE_MARKER}-sha256"


@dataclass(frozen=True, slots=True)
class SyntheticSeal:
    """A ``SealPort`` over an injected synthetic key.

    The key is a constructor argument with **no default**, so a caller who forgot
    to supply one gets a type error rather than a silently keyless seal.

    ``verify`` returns a bool rather than raising, as the port declares: the
    governed refusal belongs to the feature, not to a provider.
    """

    key: str

    def _digest(self, preimage: str) -> str:
        return hashlib.sha256(f"{self.key}\x00{preimage}".encode()).hexdigest()

    def seal(self, preimage: str, *, key_id: str) -> Seal:
        from analytics_interaction.contracts.clarification import Seal as SealContract

        return SealContract(
            key_id=key_id, algorithm=FIXTURE_ALGORITHM, value=self._digest(preimage)
        )

    def verify(self, preimage: str, seal: Seal) -> bool:
        return seal.value == self._digest(preimage)
