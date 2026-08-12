"""Shared domain layer: interfaces, models, config, persistence, task queue.

`core` must never import from `api`, `web` or `ml`. Dependencies point inward.
"""

__version__ = "0.1.0"
