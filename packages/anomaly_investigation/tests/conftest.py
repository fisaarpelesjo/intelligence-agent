"""Make this package importable from its source tree, without installing it.

The four sibling packages are installed editable in the repository's ``.venv``.
This one is **not**, and deliberately: installing it would modify the interpreter
the running bot uses, which is a change to a live environment made for the
convenience of a test run. Standing constraints forbid touching the ``.venv``, and
the constraint is right — an environment change is not free just because it usually
works.

So the source root is prepended to ``sys.path`` here. The CI workflow installs
packages properly; this keeps the suite runnable locally with nothing installed and
nothing altered.

**This is a test-only path manipulation.** It affects no production module, and
nothing under ``src/`` reads it.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
