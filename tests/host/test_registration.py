from __future__ import annotations

import subprocess
import sys
import textwrap


def _run_isolated(source: str) -> None:
    subprocess.run(  # noqa: S603 -- fixed interpreter and test-owned source
        [sys.executable, "-c", textwrap.dedent(source)],
        check=True,
        capture_output=True,
        text=True,
    )


def test_normal_import_is_a_side_effect_free_library_facade() -> None:
    _run_isolated(
        """
        import sys

        import entari_plugin_htmlrender as htmlrender

        assert "__plugin__" not in vars(htmlrender)
        assert "arclet.entari" not in sys.modules
        assert "entari_plugin_htmlrender.adapters" not in sys.modules
        assert "entari_plugin_htmlrender.host.composition" not in sys.modules
        assert htmlrender.RenderRuntime is not None
        assert htmlrender.RenderCommand is not None
        """
    )


def test_entari_loader_declares_direct_config_and_runtime_service() -> None:
    _run_isolated(
        """
        import os
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
                plugin = load_plugin(
                    "entari_plugin_htmlrender",
                    {"provider": None, "startup": "off"},
                )

                assert plugin is not None
                from entari_plugin_htmlrender.host.config import RenderSettings

                assert plugin.metadata is not None
                assert plugin.metadata.role is PluginRole.LIBRARY
                assert plugin.metadata.config is RenderSettings
                service = plugin._services["htmlrender.runtime"]
                assert service.settings == RenderSettings()
                assert service.resolve_runtime() is not None
            finally:
                os.chdir(original_cwd)
        """
    )


def test_entari_loader_injects_default_playwright_storage_path() -> None:
    _run_isolated(
        """
        import os
        from pathlib import Path
        import sys
        from tempfile import TemporaryDirectory

        from arclet.entari import load_plugin
        from arclet.entari.config import EntariConfig

        with TemporaryDirectory() as directory:
            original_cwd = Path.cwd()
            try:
                os.chdir(directory)
                EntariConfig(Path(directory) / "entari.yml")
                plugin = load_plugin(
                    "entari_plugin_htmlrender",
                    {"provider": "playwright", "startup": "off"},
                )

                assert plugin is not None
                unexpected = {
                    name
                    for name in sys.modules
                    if name == "playwright" or name.startswith("playwright.")
                }
                assert not unexpected, sorted(unexpected)
                service = plugin._services["htmlrender.runtime"]
                assert service.settings.provider_config["storage_path"] == (
                    Path(directory).resolve()
                    / ".entari"
                    / "cache"
                    / "htmlrender"
                    / "playwright"
                )
            finally:
                os.chdir(original_cwd)
        """
    )


def test_entari_loader_preserves_explicit_playwright_storage_path() -> None:
    _run_isolated(
        """
        import os
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from arclet.entari import load_plugin
        from arclet.entari.config import EntariConfig

        with TemporaryDirectory() as directory:
            original_cwd = Path.cwd()
            try:
                os.chdir(directory)
                EntariConfig(Path(directory) / "entari.yml")
                explicit_path = "custom/playwright"
                plugin = load_plugin(
                    "entari_plugin_htmlrender",
                    {
                        "provider": "playwright",
                        "provider_config": {"storage_path": explicit_path},
                        "startup": "off",
                    },
                )

                assert plugin is not None
                service = plugin._services["htmlrender.runtime"]
                assert (
                    service.settings.provider_config["storage_path"] == explicit_path
                )
            finally:
                os.chdir(original_cwd)
        """
    )
