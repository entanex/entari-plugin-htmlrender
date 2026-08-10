from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import textwrap

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_python(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_public_library_import_is_host_neutral_and_lazy() -> None:
    result = _run_python(
        """
        import importlib.abc
        import sys

        blocked = (
            "PIL",
            "aiohttp",
            "arclet.entari",
            "playwright",
            "prometheus_client",
            "sentry_sdk",
            "skia",
            "takumi_py",
        )

        class BlockOptionalModules(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                del path, target
                if any(
                    fullname == prefix or fullname.startswith(f"{prefix}.")
                    for prefix in blocked
                ):
                    raise ModuleNotFoundError(fullname)
                return None

        sys.meta_path.insert(0, BlockOptionalModules())
        import entari_plugin_htmlrender

        unexpected = {
            name
            for name in sys.modules
            if any(name == prefix or name.startswith(f"{prefix}.") for prefix in blocked)
        }
        if unexpected:
            raise SystemExit(f"unexpected host or optional modules: {sorted(unexpected)}")
        """
    )

    assert result.returncode == 0, result.stderr


def test_core_packages_do_not_load_host_composition_or_adapters() -> None:
    result = _run_python(
        """
        import sys

        import entari_plugin_htmlrender.graphics
        import entari_plugin_htmlrender.preparation
        import entari_plugin_htmlrender.rendering
        import entari_plugin_htmlrender.resources
        import entari_plugin_htmlrender.runtime

        forbidden_prefixes = (
            "entari_plugin_htmlrender.adapters",
            "entari_plugin_htmlrender.host.composition",
            "entari_plugin_htmlrender.host._service",
            "arclet.entari",
        )
        unexpected = {
            name
            for name in sys.modules
            if any(
                name == prefix or name.startswith(f"{prefix}.")
                for prefix in forbidden_prefixes
            )
        }
        if unexpected:
            raise SystemExit(f"core import crossed a host boundary: {sorted(unexpected)}")
        """
    )

    assert result.returncode == 0, result.stderr


def test_first_party_provider_modules_do_not_load_native_engines() -> None:
    result = _run_python(
        """
        import sys

        from entari_plugin_htmlrender.adapters.playwright import provider as playwright
        from entari_plugin_htmlrender.adapters.takumi import provider as takumi

        if playwright.PROVIDER.id != "playwright":
            raise SystemExit("playwright provider id mismatch")
        if takumi.PROVIDER.id != "takumi":
            raise SystemExit("takumi provider id mismatch")

        forbidden = {
            "playwright.async_api",
            "takumi_py",
            "entari_plugin_htmlrender.adapters.playwright.render",
        }
        unexpected = forbidden & set(sys.modules)
        if unexpected:
            raise SystemExit(f"provider import loaded native engines: {sorted(unexpected)}")
        """
    )

    assert result.returncode == 0, result.stderr


def test_selected_playwright_provider_build_stays_lazy() -> None:
    result = _run_python(
        """
        import sys

        from entari_plugin_htmlrender.host.composition import compose_runtime
        from entari_plugin_htmlrender.host.config import RenderSettings

        settings = RenderSettings.model_validate(
            {"provider": "playwright", "startup": "off"}
        )
        plan = compose_runtime(settings)
        runtime = plan.build_runtime()

        if plan.provider is None or plan.provider.id != "playwright":
            raise SystemExit("playwright provider was not selected")
        if runtime is None:
            raise SystemExit("render runtime was not built")
        unexpected = {
            name
            for name in sys.modules
            if name == "playwright" or name.startswith("playwright.")
        }
        if unexpected:
            raise SystemExit(
                f"selected provider build loaded Playwright: {sorted(unexpected)}"
            )
        """
    )

    assert result.returncode == 0, result.stderr


def test_observability_import_does_not_load_optional_sdks() -> None:
    result = _run_python(
        """
        import sys

        import entari_plugin_htmlrender.adapters.observability

        unexpected = {"prometheus_client", "sentry_sdk"} & set(sys.modules)
        if unexpected:
            raise SystemExit(f"observability import loaded optional SDKs: {sorted(unexpected)}")
        """
    )

    assert result.returncode == 0, result.stderr


def test_playwright_package_and_lightweight_config_stay_lazy() -> None:
    result = _run_python(
        """
        import sys

        import entari_plugin_htmlrender.adapters.playwright as playwright_package
        from entari_plugin_htmlrender.adapters.playwright.config import PlaywrightConfig

        if "__getattr__" in playwright_package.__dict__:
            raise SystemExit("playwright package must not use module __getattr__")
        PlaywrightConfig()

        forbidden = {
            "playwright.async_api",
            "entari_plugin_htmlrender.adapters.playwright._page",
            "entari_plugin_htmlrender.adapters.playwright.operations",
            "entari_plugin_htmlrender.adapters.playwright.render",
        }
        unexpected = forbidden & set(sys.modules)
        if unexpected:
            raise SystemExit(f"lightweight config loaded backend: {sorted(unexpected)}")
        """
    )

    assert result.returncode == 0, result.stderr


def test_playwright_install_state_does_not_import_entari() -> None:
    result = _run_python(
        """
        import importlib.abc
        import sys

        class BlockEntari(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                del path, target
                if fullname == "arclet.entari" or fullname.startswith("arclet.entari."):
                    raise ModuleNotFoundError(fullname)
                return None

        sys.meta_path.insert(0, BlockEntari())
        from entari_plugin_htmlrender.adapters.playwright import install_state
        from entari_plugin_htmlrender.adapters.playwright.config import PlaywrightConfig

        config = PlaywrightConfig()
        install_state.get_playwright_storage_path(config)
        unexpected = {
            name
            for name in sys.modules
            if name == "arclet.entari" or name.startswith("arclet.entari.")
        }
        if unexpected:
            raise SystemExit(f"install state imported Entari: {sorted(unexpected)}")
        """
    )

    assert result.returncode == 0, result.stderr
