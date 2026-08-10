"""The shipped example provider must keep satisfying the SDK contract."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import TYPE_CHECKING, Any

import pytest

from entari_plugin_htmlrender.host.composition import compose_runtime
from entari_plugin_htmlrender.host.config import RenderSettings
from entari_plugin_htmlrender.preparation import RasterOptions
from entari_plugin_htmlrender.providers.sdk import EngineProvider
from entari_plugin_htmlrender.rendering import (
    RenderHtmlRequest,
    UnsupportedRenderOption,
)
from entari_plugin_htmlrender.resources.config import ResourceStrategy

if TYPE_CHECKING:
    from entari_plugin_htmlrender.runtime import RenderRuntime

_EXAMPLE_MODULE = (
    Path(__file__).resolve().parents[2]
    / "examples"
    / "echo-provider"
    / "src"
    / "htmlrender_echo_provider"
    / "__init__.py"
)

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _load_example_provider() -> EngineProvider[Any]:
    spec = importlib.util.spec_from_file_location(
        "htmlrender_echo_provider",
        _EXAMPLE_MODULE,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclass processing resolves string annotations through sys.modules.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        provider = module.PROVIDER
    finally:
        sys.modules.pop(spec.name, None)
    assert isinstance(provider, EngineProvider)
    return provider


async def test_echo_provider_composes_and_renders() -> None:
    provider = _load_example_provider()
    settings = RenderSettings.model_validate(
        {
            "provider": "echo",
            "provider_config": {"color": "#ff0000"},
        }
    )

    composition = compose_runtime(settings, explicit_providers=[provider])
    runtime = composition.build_runtime()
    await runtime.startup()
    try:
        artifact = await runtime.renderer.render_html(
            RenderHtmlRequest(html="<p>echo</p>")
        )
    finally:
        await runtime.aclose()

    payload = bytes(artifact)
    assert payload[: len(_PNG_MAGIC)] == _PNG_MAGIC
    assert artifact.format == "png"
    assert (artifact.width, artifact.height) == (1, 1)
    assert runtime.resources.strategy == ResourceStrategy()


async def test_echo_provider_satisfies_lifecycle_conformance() -> None:
    # The installable harness ships with the production package so provider
    # authors can run it from a wheel; the example consumes it the same way.
    from entari_plugin_htmlrender.providers.testing import (  # noqa: PLC0415
        run_provider_lifecycle_conformance,
    )

    provider = _load_example_provider()
    settings = RenderSettings.model_validate({"provider": "echo"})

    def compose(selected: EngineProvider[Any]) -> RenderRuntime:
        return compose_runtime(
            settings,
            explicit_providers=[selected],
        ).build_runtime()

    await run_provider_lifecycle_conformance(provider, compose)


async def test_echo_provider_rejects_unsupported_encoded_format() -> None:
    provider = _load_example_provider()
    composition = compose_runtime(
        RenderSettings.model_validate({"provider": "echo"}),
        explicit_providers=[provider],
    )
    runtime = composition.build_runtime()
    try:
        with pytest.raises(UnsupportedRenderOption, match="PNG only"):
            await runtime.renderer.render_html(
                RenderHtmlRequest(
                    html="<p>echo</p>",
                    raster=RasterOptions(format="jpeg"),
                )
            )
    finally:
        await runtime.aclose()


def test_echo_provider_rejects_unknown_settings_keys() -> None:
    provider = _load_example_provider()
    with pytest.raises(ValueError, match="Unknown provider_config keys"):
        provider.parse_settings({"color": "#123456", "bogus": True})
