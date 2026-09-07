"""Governed semantic catalog.

Authored intent lives as version-controlled YAML under ``semantic/``; observed
reality is read from two BigQuery ``semantic`` tables owned by a separate
transformation feature. This package creates no BigQuery object, contains no
DDL, and holds no warehouse write grant.

See ``specs/001-semantic-catalog/`` for the governing specification and plan.
"""

__version__ = "0.1.0"
