"""Curated resource-domain contract surface."""

from .config import ResourceMaterializationPolicy as ResourceMaterializationPolicy
from .errors import ResourceAccessDeniedError as ResourceAccessDeniedError
from .errors import ResourceAuthenticationError as ResourceAuthenticationError
from .errors import ResourceError as ResourceError
from .errors import ResourceFetchError as ResourceFetchError
from .errors import ResourceNetworkError as ResourceNetworkError
from .errors import ResourceNotFoundError as ResourceNotFoundError
from .errors import ResourcePublishError as ResourcePublishError
from .errors import ResourceRemoteResponseError as ResourceRemoteResponseError
from .errors import ResourceTimeoutError as ResourceTimeoutError
from .errors import ResourceTooLargeError as ResourceTooLargeError
from .models import (
    FileResourceRef,
    InlineResource,
    PackageResourceRef,
    PublishedResource,
    RemoteResourceRef,
    ResourceContent,
    ResourceRef,
    ResourceRevision,
)
from .ports import (
    ResourceAccess,
    ResourceFetcher,
    ResourceMaterializer,
)
from .source import FilesystemResourceSource, PackageResourceSource

__all__ = [
    "FileResourceRef",
    "FilesystemResourceSource",
    "InlineResource",
    "PackageResourceRef",
    "PackageResourceSource",
    "PublishedResource",
    "RemoteResourceRef",
    "ResourceAccess",
    "ResourceAccessDeniedError",
    "ResourceAuthenticationError",
    "ResourceContent",
    "ResourceError",
    "ResourceFetchError",
    "ResourceFetcher",
    "ResourceMaterializationPolicy",
    "ResourceMaterializer",
    "ResourceNetworkError",
    "ResourceNotFoundError",
    "ResourcePublishError",
    "ResourceRef",
    "ResourceRemoteResponseError",
    "ResourceRevision",
    "ResourceTimeoutError",
    "ResourceTooLargeError",
]
