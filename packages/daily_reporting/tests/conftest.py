"""Make this package importable from source, whether or not it is installed.

## What this file said first, and why it was wrong

It said the package was deliberately **not** installed, borrowing `005`'s reasoning that
installing would modify the interpreter the running bot uses. That reasoning was real
once and is no longer this repository's: **all seven packages before this one are
installed editable in the `.venv`**, and `006`'s
`tests/contract/test_every_package_can_actually_be_installed.py` requires every declared
package to be importable — a node written in an earlier cycle precisely because *on disk*
and *installed* look identical to a path-based suite.

**That node caught this package on its first push**, which is the node doing exactly what
it was written for, one feature later. The install was made with ``--no-deps`` and the
environment was measured before and after: **one line changed**, this package's own.

**The path insertion stays** so the suite runs in a checkout where nothing is installed.
It is test-only; no production module reads it, which
``tests/security/test_no_composed_prose_and_nothing_originates.py`` measures over the
emitted tree rather than taking this sentence's word for it.
"""

from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]

SOURCE_ROOTS = (PACKAGE_ROOT / "src",)

for root in SOURCE_ROOTS:
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
