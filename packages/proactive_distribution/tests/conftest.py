"""Make this package and its one uninstalled sibling importable from source.

Four of the five packages before this one are installed editable in the
repository's ``.venv``. **`005` is not, and deliberately**: installing it would
modify the interpreter the running bot uses, which is a change to a live
environment made for the convenience of a test run. That reasoning was `005`'s and
it holds unchanged for `006`, so **neither this package nor `005` is installed**.

So both source roots are prepended to ``sys.path`` here. The CI workflow installs
packages properly; this keeps the suite runnable locally with nothing installed and
nothing altered.

**This is a test-only path manipulation.** It affects no production module, and
nothing under ``src/`` reads it — which
``tests/security/test_originates_nothing.py`` measures over the emitted tree rather
than taking this sentence's word for it.
"""

from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PACKAGES = PACKAGE_ROOT.parent

#: This package first, then the two uninstalled siblings it consumes. `006` is here as
#: well as `005`: this feature reads a placed finding, and the package that places one is
#: not installed either.
SOURCE_ROOTS = (
    PACKAGE_ROOT / "src",
    PACKAGES / "insights_prioritisation" / "src",
    PACKAGES / "anomaly_investigation" / "src",
)

for root in SOURCE_ROOTS:
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
