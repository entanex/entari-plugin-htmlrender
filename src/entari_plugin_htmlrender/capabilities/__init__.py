"""Stable provider-specific capability contracts and lookup keys."""

from .playwright import (
    PLAYWRIGHT,
    PlaywrightCapability,
    PlaywrightPageOptions,
)
from .takumi import (
    TAKUMI,
    TakumiCapability,
    TakumiSession,
)

__all__ = [
    "PLAYWRIGHT",
    "TAKUMI",
    "PlaywrightCapability",
    "PlaywrightPageOptions",
    "TakumiCapability",
    "TakumiSession",
]
