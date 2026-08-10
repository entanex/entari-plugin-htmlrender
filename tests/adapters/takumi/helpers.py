from entari_plugin_htmlrender.adapters.resources.reader import (
    AnyioWorkerExecutor,
    CompositeResourceFetcher,
    ConfiguredLocalAccessPolicy,
    RemoteTransportExecutor,
)
from entari_plugin_htmlrender.resources.config import (
    LocalResourceStrategy,
    ResourceStrategy,
)
from entari_plugin_htmlrender.resources.service import ResourceService


def resource_service(*, strategy: ResourceStrategy | None = None) -> ResourceService:
    local_access = ConfiguredLocalAccessPolicy(allowed_roots=(), allow_any=True)
    return ResourceService(
        fetcher=CompositeResourceFetcher(
            AnyioWorkerExecutor(),
            local_access=local_access,
            remote_transport=RemoteTransportExecutor(max_concurrent_fetches=2),
        ),
        local_access=local_access,
        strategy=strategy or LocalResourceStrategy(),
    )


__all__ = ["resource_service"]
