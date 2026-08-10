"""Stable, recovery-oriented failures owned by the resource domain."""

from entari_plugin_htmlrender.errors import (
    ResourceAccessDeniedError,
    ResourceAuthenticationError,
    ResourceError,
    ResourceFetchError,
    ResourceNetworkError,
    ResourceNotFoundError,
    ResourcePublishError,
    ResourceRemoteResponseError,
    ResourceTimeoutError,
    ResourceTooLargeError,
)

__all__ = [
    "ResourceAccessDeniedError",
    "ResourceAuthenticationError",
    "ResourceError",
    "ResourceFetchError",
    "ResourceNetworkError",
    "ResourceNotFoundError",
    "ResourcePublishError",
    "ResourceRemoteResponseError",
    "ResourceTimeoutError",
    "ResourceTooLargeError",
]
