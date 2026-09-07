"""The outbound boundary — Phase C (ADR 0022).

Rendering may change **form**. It may never change **content**. Where form alone cannot carry the
payload, the channel's governed continuation mechanism delivers it whole; where continuation cannot
carry it intact, the response is **withheld**.

Withholding is a governed outcome with the standing of any other, which is what stops "cannot
deliver this intact" from becoming "deliver most of it".
"""

from __future__ import annotations

__all__: tuple[str, ...] = ()
