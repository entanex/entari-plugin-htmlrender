from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from entari_plugin_htmlrender.adapters.resources import (
        ConfiguredLocalAccessPolicy,
    )
    from entari_plugin_htmlrender.preparation.service import DefaultHtmlPreparer
    from entari_plugin_htmlrender.resources.service import ResourceService


@pytest.fixture
def local_access(tmp_path: Path) -> ConfiguredLocalAccessPolicy:
    from entari_plugin_htmlrender.adapters.resources import (  # noqa: PLC0415
        ConfiguredLocalAccessPolicy,
    )

    return ConfiguredLocalAccessPolicy(
        allowed_roots=(tmp_path,),
        allow_any=False,
    )


@pytest.fixture
def resources(local_access: ConfiguredLocalAccessPolicy) -> ResourceService:
    from entari_plugin_htmlrender.adapters.resources import (  # noqa: PLC0415
        AnyioWorkerExecutor,
        RemoteTransportExecutor,
        build_resource_reader,
    )
    from entari_plugin_htmlrender.resources.config import (  # noqa: PLC0415
        ResourceCacheSettings,
        ResourceStrategy,
    )
    from entari_plugin_htmlrender.resources.observation import (  # noqa: PLC0415
        NoopCacheObserver,
    )
    from entari_plugin_htmlrender.resources.service import (  # noqa: PLC0415
        ResourceService,
    )

    observer = NoopCacheObserver()
    worker = AnyioWorkerExecutor()
    reader = build_resource_reader(
        ResourceCacheSettings(),
        observer,
        worker,
        remote_transport=RemoteTransportExecutor(max_concurrent_fetches=2),
    )
    return ResourceService(
        reader=reader,
        local_access=local_access,
        strategy=ResourceStrategy(),
    )


@pytest.fixture
def preparer(
    resources: ResourceService,
    local_access: ConfiguredLocalAccessPolicy,
) -> DefaultHtmlPreparer:
    from entari_plugin_htmlrender.adapters.resources import (  # noqa: PLC0415
        AnyioWorkerExecutor,
    )
    from entari_plugin_htmlrender.adapters.templates import (  # noqa: PLC0415
        JinjaTemplateCompiler,
    )
    from entari_plugin_htmlrender.preparation.service import (  # noqa: PLC0415
        DefaultHtmlPreparer,
    )
    from entari_plugin_htmlrender.resources.observation import (  # noqa: PLC0415
        NoopCacheObserver,
    )

    observer = NoopCacheObserver()
    worker = AnyioWorkerExecutor()
    return DefaultHtmlPreparer(
        resources=resources,
        templates=JinjaTemplateCompiler(
            max_entries=16,
            observer=observer,
            worker=worker,
            local_access=local_access,
        ),
        worker=worker,
    )
