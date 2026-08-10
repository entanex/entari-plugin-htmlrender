from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError
import pytest

from entari_plugin_htmlrender.config import (
    HtmlRenderConfig,
    RuntimeStartupPolicy,
)


def test_htmlrender_config_defaults() -> None:
    settings = HtmlRenderConfig()

    assert settings.provider is None
    assert settings.startup is RuntimeStartupPolicy.OFF
    assert settings.provider_config == {}
    assert settings.html.max_source_bytes == 64 * 1024 * 1024
    assert settings.html.max_pixels == 16 * 1024 * 1024
    assert settings.html.max_output_bytes == 64 * 1024 * 1024
    assert settings.html.max_device_pixel_ratio == 4.0
    assert settings.html.max_auto_height == 16_384
    assert settings.html.max_concurrency == 2
    assert settings.graphics.backend is None
    assert settings.graphics.max_pixels == 16 * 1024 * 1024
    assert settings.graphics.max_concurrency == 2
    assert settings.resources.cache.max_entries == 256
    assert settings.resources.cache.max_bytes == 64 * 1024 * 1024
    assert settings.resources.cache.max_resource_bytes == 64 * 1024 * 1024
    assert settings.resources.templates.environment_cache_max_entries == 64
    assert settings.resources.traversal.max_nodes == 10_000
    assert settings.resources.traversal.max_depth == 64
    assert settings.resources.traversal.max_concurrency == 16
    assert settings.resources.local_access.allow_any_path is False
    assert settings.resources.local_access.allowed_paths == []
    assert settings.resources.filehost.bind_host == "127.0.0.1"
    assert settings.resources.filehost.bind_port == 8080
    assert settings.resources.filehost.cache_ttl_seconds == 300.0
    assert settings.resources.filehost.request_header_name == (
        "X-HTMLRender-Filehost-Request"
    )
    assert settings.resources.filehost.prewarm_enabled is True
    assert settings.observability.sentry is False
    assert settings.observability.prometheus is False


def test_htmlrender_config_nested_parse() -> None:
    settings = HtmlRenderConfig.model_validate(
        {
            "provider": "takumi",
            "startup": "probe",
            "provider_config": {"max_concurrency": 2},
            "html": {
                "max_source_bytes": 1024,
                "max_pixels": 4096,
                "max_output_bytes": 2048,
                "max_device_pixel_ratio": 2,
                "max_auto_height": 512,
                "max_concurrency": 1,
            },
            "graphics": {
                "backend": "skia",
                "max_pixels": 1_000_000,
                "max_concurrency": 1,
            },
            "resources": {
                "cache": {"max_entries": 8},
                "traversal": {
                    "max_nodes": 128,
                    "max_depth": 8,
                    "max_concurrency": 2,
                },
                "local_access": {"allowed_paths": "assets"},
                "filehost": {
                    "bind_host": "localhost",
                    "bind_port": 9000,
                    "cache_ttl_seconds": 30,
                    "prewarm_paths": ["public"],
                },
            },
            "observability": {"prometheus": True},
        }
    )

    assert settings.provider == "takumi"
    assert settings.startup is RuntimeStartupPolicy.PROBE
    assert settings.provider_config == {"max_concurrency": 2}
    assert settings.html.max_source_bytes == 1024
    assert settings.html.max_pixels == 4096
    assert settings.html.max_output_bytes == 2048
    assert settings.html.max_device_pixel_ratio == 2
    assert settings.html.max_auto_height == 512
    assert settings.html.max_concurrency == 1
    assert settings.graphics.backend == "skia"
    assert settings.graphics.max_pixels == 1_000_000
    assert settings.graphics.max_concurrency == 1
    assert settings.resources.cache.max_entries == 8
    assert settings.resources.traversal.max_nodes == 128
    assert settings.resources.traversal.max_depth == 8
    assert settings.resources.traversal.max_concurrency == 2
    assert settings.resources.local_access.allowed_paths == [Path("assets")]
    assert settings.resources.filehost.bind_host == "localhost"
    assert settings.resources.filehost.bind_port == 9000
    assert settings.resources.filehost.cache_ttl_seconds == 30
    assert settings.resources.filehost.prewarm_paths == [Path("public")]
    assert settings.observability.prometheus is True


@pytest.mark.parametrize(
    "value, location",
    [
        ({"unknown": True}, "unknown"),
        ({"resources": {"unknown": True}}, "resources.unknown"),
        (
            {"resources": {"cache": {"max_entry": 8}}},
            "resources.cache.max_entry",
        ),
        ({"observability": {"prometheuz": True}}, "observability.prometheuz"),
        (
            {"resources": {"filehost": {"bind_host": "  "}}},
            "resources.filehost.bind_host",
        ),
        (
            {"resources": {"filehost": {"bind_port": 65_536}}},
            "resources.filehost.bind_port",
        ),
        ({"graphics": {"backend": ["pillow"]}}, "graphics.backend"),
        ({"graphics": {"backend": "unknown"}}, "graphics.backend"),
        ({"graphics": {"backends": ["pillow"]}}, "graphics.backends"),
    ],
)
def test_render_tree_rejects_unknown_fields(
    value: dict[str, object],
    location: str,
) -> None:
    with pytest.raises(ValidationError) as captured:
        HtmlRenderConfig.model_validate(value)

    assert location in str(captured.value)


def test_htmlrender_config_rejects_wrapped_or_unrelated_config() -> None:
    for value in (
        {"render": {"provider": "takumi"}},
        {"unrelated_plugin": {"enabled": True}},
    ):
        with pytest.raises(ValidationError):
            HtmlRenderConfig.model_validate(value)


@pytest.mark.parametrize(
    "value",
    [
        {"html": {"max_device_pixel_ratio": float("inf")}},
        {"resources": {"cache": {"revalidate_seconds": float("inf")}}},
        {"resources": {"remote_access": {"request_timeout_seconds": float("inf")}}},
        {"resources": {"filehost": {"cache_ttl_seconds": float("inf")}}},
    ],
)
def test_htmlrender_config_rejects_non_finite_numbers(
    value: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        HtmlRenderConfig.model_validate(value)


@pytest.mark.parametrize(
    "provider",
    ["", " ", "Playwright", "bad/provider", "-leading", "trailing-"],
)
def test_htmlrender_config_rejects_invalid_provider_ids(provider: str) -> None:
    with pytest.raises(ValidationError, match="provider id"):
        HtmlRenderConfig.model_validate({"provider": provider})


@pytest.mark.parametrize(
    "value",
    [
        {"provider_config": {"answer": 42}},
        {"startup": "warmup"},
        {"startup": "probe"},
    ],
)
def test_provider_options_require_a_selected_provider(
    value: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        HtmlRenderConfig.model_validate(value)


@pytest.mark.parametrize(
    "filehost",
    [
        {"request_header_name": ""},
        {"request_header_name": "bad header"},
        {"request_header_name": "bad:header"},
        {"request_header_value": "value\r\ninjected: yes"},
        {"request_header_value": "value\x7f"},
    ],
)
def test_filehost_rejects_invalid_request_headers(
    filehost: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        HtmlRenderConfig.model_validate({"resources": {"filehost": filehost}})
