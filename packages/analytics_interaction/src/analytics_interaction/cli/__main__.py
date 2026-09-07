"""``python -m analytics_interaction.cli``.

A thin entry point so the module form quickstart documents actually runs. It
resolves nothing and decides nothing — every command lives in :mod:`main`, and
putting logic here would make the module-form and the imported-form two
different programs.
"""

from __future__ import annotations

import sys

from .main import main

if __name__ == "__main__":  # pragma: no cover - entry point
    sys.exit(main())
