from __future__ import annotations

import subprocess
import sys
import textwrap


def _run_isolated(source: str) -> None:
    result = subprocess.run(  # noqa: S603 -- fixed interpreter and test source
        [sys.executable, "-c", textwrap.dedent(source)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_normal_import_is_a_side_effect_free_caller_facade() -> None:
    _run_isolated(
        """
        import sys

        import entari_plugin_htmlrender as htmlrender

        assert "__plugin__" not in vars(htmlrender)
        assert "arclet.entari" not in sys.modules
        assert "entari_plugin_htmlrender.adapters" not in sys.modules
        assert "entari_plugin_htmlrender.composition" not in sys.modules
        assert "entari_plugin_htmlrender.entari" not in sys.modules
        assert htmlrender.HtmlRenderer is not None
        assert htmlrender.TemplateRenderer is not None
        assert htmlrender.RenderOperation.HTML_TO_IMAGE.value == "html_to_image"
        assert not hasattr(htmlrender, "RenderRuntime")
        """
    )


def test_entari_loader_registers_concrete_caller_service() -> None:
    _run_isolated(
        """
        import os
        from importlib.metadata import version
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from arclet.entari import load_plugin
        from arclet.entari.config import EntariConfig
        from arclet.entari.plugin import PluginRole

        with TemporaryDirectory() as directory:
            original_cwd = Path.cwd()
            try:
                os.chdir(directory)
                EntariConfig(Path(directory) / "entari.yml")
                from entari_plugin_htmlrender.config import HtmlRenderConfig
                from entari_plugin_htmlrender.entari import HtmlRenderService

                plugin = load_plugin(
                    "entari_plugin_htmlrender",
                    {"provider": None, "startup": "off"},
                )

                assert plugin is not None
                assert plugin.metadata is not None
                assert plugin.metadata.role is PluginRole.LIBRARY
                assert plugin.metadata.version == version("entari-plugin-htmlrender")
                assert plugin.metadata.config is HtmlRenderConfig
                service = plugin._services["htmlrender.runtime"]
                assert isinstance(service, HtmlRenderService)
                assert service.renderer is not None
                assert service.templates is not None
                assert service.resources is not None
                assert service.graphics is not None
                assert service.capabilities is not None
                assert not hasattr(service, "resolve_runtime")
                assert not hasattr(service, "settings")
                assert not hasattr(service, "aclose")
            finally:
                os.chdir(original_cwd)
        """
    )


def test_entari_defaults_own_playwright_storage_path_only_when_absent() -> None:
    _run_isolated(
        """
        import os
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from arclet.entari.config import EntariConfig

        with TemporaryDirectory() as directory:
            original_cwd = Path.cwd()
            try:
                os.chdir(directory)
                EntariConfig(Path(directory) / "entari.yml")
                from entari_plugin_htmlrender.config import HtmlRenderConfig
                from entari_plugin_htmlrender.entari.plugin import (
                    _apply_entari_defaults,
                )

                defaulted = _apply_entari_defaults(
                    HtmlRenderConfig.model_validate(
                        {"provider": "playwright", "startup": "off"}
                    )
                )
                explicit = _apply_entari_defaults(
                    HtmlRenderConfig.model_validate(
                        {
                            "provider": "playwright",
                            "provider_config": {"storage_path": "custom/playwright"},
                            "startup": "off",
                        }
                    )
                )

                assert defaulted.provider_config["storage_path"] == (
                    Path(directory).resolve()
                    / ".entari"
                    / "cache"
                    / "htmlrender"
                    / "playwright"
                )
                assert explicit.provider_config["storage_path"] == "custom/playwright"
            finally:
                os.chdir(original_cwd)
        """
    )
