"""``python -m semantic_catalog.cli`` — T096.

Present so CI and stewards can run the CLI without installing a console script,
which keeps the workflow independent of packaging state.
"""

from __future__ import annotations

from .main import main

if __name__ == "__main__":
    raise SystemExit(main())
