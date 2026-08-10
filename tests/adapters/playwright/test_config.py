import pytest


def test_playwright_config_uses_safe_remote_resource_defaults() -> None:
    from entari_plugin_htmlrender.adapters.playwright.config import (  # noqa: PLC0415
        PlaywrightConfig,
    )
    from entari_plugin_htmlrender.resources.config import (  # noqa: PLC0415
        RemoteLocalResourcePolicy,
        ResourceMaterializationPolicy,
    )

    cfg = PlaywrightConfig()

    assert cfg.materialization_policy is ResourceMaterializationPolicy.AUTO
    assert cfg.remote_local_resource_policy is RemoteLocalResourcePolicy.MEMORY


def test_playwright_config_preserves_explicit_materialization_policy() -> None:
    from entari_plugin_htmlrender.adapters.playwright.config import (  # noqa: PLC0415
        PlaywrightConfig,
    )
    from entari_plugin_htmlrender.resources.config import (  # noqa: PLC0415
        RemoteLocalResourcePolicy,
        ResourceMaterializationPolicy,
    )

    cfg = PlaywrightConfig.model_validate(
        {
            "materialization_policy": "off",
            "remote_local_resource_policy": "passthrough",
        }
    )

    assert cfg.materialization_policy is ResourceMaterializationPolicy.OFF
    assert cfg.remote_local_resource_policy is RemoteLocalResourcePolicy.PASSTHROUGH


def test_playwright_config_normalizes_empty_executable_path() -> None:
    from entari_plugin_htmlrender.adapters.playwright.config import (  # noqa: PLC0415
        PlaywrightConfig,
    )

    cfg = PlaywrightConfig.model_validate({"executable_path": " . "})

    assert cfg.executable_path is None


def test_playwright_config_rejects_channel_for_non_chromium() -> None:
    from entari_plugin_htmlrender.adapters.playwright.config import (  # noqa: PLC0415
        BrowserEngine,
        ChromiumChannel,
        PlaywrightConfig,
    )

    with pytest.raises(ValueError, match="channel"):
        PlaywrightConfig(
            engine=BrowserEngine.FIREFOX,
            channel=ChromiumChannel.CHROME,
        )


def test_playwright_config_rejects_multiple_remote_modes() -> None:
    from entari_plugin_htmlrender.adapters.playwright.config import (  # noqa: PLC0415
        PlaywrightConfig,
        RemoteCDPConfig,
        RemoteWSConfig,
    )

    with pytest.raises(
        ValueError,
        match=r"provider_config\.connect_ws\.endpoint",
    ):
        PlaywrightConfig(
            connect_ws=RemoteWSConfig(endpoint="ws://localhost:3000/ws"),
            connect_cdp=RemoteCDPConfig(endpoint="http://localhost:9222"),
        )


def test_playwright_config_rejects_non_chromium_cdp() -> None:
    from entari_plugin_htmlrender.adapters.playwright.config import (  # noqa: PLC0415
        BrowserEngine,
        PlaywrightConfig,
        RemoteCDPConfig,
    )

    with pytest.raises(ValueError, match=r"provider_config\.engine"):
        PlaywrightConfig(
            engine=BrowserEngine.WEBKIT,
            connect_cdp=RemoteCDPConfig(endpoint="http://localhost:9222"),
        )


def test_playwright_config_accepts_resource_resolution_options() -> None:
    from entari_plugin_htmlrender.adapters.playwright.config import (  # noqa: PLC0415
        PlaywrightConfig,
    )
    from entari_plugin_htmlrender.resources.config import (  # noqa: PLC0415
        LocalLocalResourcePolicy,
        RemoteLocalResourcePolicy,
        ResourceMaterializationPolicy,
    )

    cfg = PlaywrightConfig(
        materialization_policy=ResourceMaterializationPolicy.AUTO,
        remote_local_resource_policy=RemoteLocalResourcePolicy.FILEHOST,
        local_local_resource_policy=LocalLocalResourcePolicy.FILE,
    )

    assert cfg.materialization_policy is ResourceMaterializationPolicy.AUTO
    assert cfg.remote_local_resource_policy is RemoteLocalResourcePolicy.FILEHOST
    assert cfg.local_local_resource_policy is LocalLocalResourcePolicy.FILE


def test_playwright_config_rejects_moved_filehost_options() -> None:
    from entari_plugin_htmlrender.adapters.playwright.config import (  # noqa: PLC0415
        PlaywrightConfig,
    )

    with pytest.raises(ValueError, match="filehost_cache_ttl_seconds"):
        PlaywrightConfig.model_validate({"filehost_cache_ttl_seconds": 60})


def test_playwright_config_rejects_invalid_engine_and_channel() -> None:
    from entari_plugin_htmlrender.adapters.playwright.config import (  # noqa: PLC0415
        PlaywrightConfig,
    )

    with pytest.raises(ValueError, match=r"(invalid engine|Input should be)"):
        PlaywrightConfig.model_validate({"engine": "invalid-engine"})

    with pytest.raises(ValueError, match=r"(invalid channel|Input should be)"):
        PlaywrightConfig.model_validate({"channel": "invalid-channel"})
