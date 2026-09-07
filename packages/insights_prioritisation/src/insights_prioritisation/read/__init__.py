"""What this feature READS, and never derives.

Every module here answers a question by finding a declaration and carrying it. A
question with no declaration behind it comes back as an absence naming itself,
never as a default — which is `FR-003` and `FR-004` in one sentence.
"""

from __future__ import annotations

from .direction import MetricDirection, read_direction

__all__ = ["MetricDirection", "read_direction"]
