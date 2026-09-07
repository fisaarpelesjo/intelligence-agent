"""Make this package and its uninstalled siblings importable from source.

The reasoning is `005`'s and `006`'s, unchanged: installing into the repository's
``.venv`` would modify the interpreter the running bot uses — a change to a live
environment for the convenience of a test run. So the source roots are prepended
here, and CI installs properly.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PACKAGES = Path(__file__).resolve().parents[2]
for _sibling in ("conversation_context", "analytics_interaction", "channel_integration"):
    _root = str(_PACKAGES / _sibling / "src")
    if _root not in sys.path:
        sys.path.insert(0, _root)
