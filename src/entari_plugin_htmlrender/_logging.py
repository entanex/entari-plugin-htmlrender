"""Package-local logging boundary.

Core modules use the standard library logger so they remain independent from
the Entari host and from optional observability integrations.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("entari_plugin_htmlrender")

__all__ = ["logger"]
