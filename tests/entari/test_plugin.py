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
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


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

                loaded = load_plugin(
                    "entari_plugin_htmlrender",
                    {"provider": None, "startup": "off"},
                )

                assert loaded
                plugin = loaded.plugin
                assert plugin is not None
                assert plugin.metadata is not None
                assert plugin.metadata.role is PluginRole.LIBRARY
                assert plugin.metadata.version == version("entari-plugin-htmlrender")
                assert plugin.metadata.config is HtmlRenderConfig
                service = plugin._services["htmlrender.runtime"]
                assert isinstance(service, HtmlRenderService)
                assert service.renderer is not None
                assert service.preparation is not None
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


def test_atomic_plugin_reload_replaces_service_with_new_configuration() -> None:
    _run_isolated(
        """
        import asyncio
        import gc
        import os
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from arclet.entari import load_plugin
        from arclet.entari.config import EntariConfig
        from arclet.entari.plugin import (
            find_plugin,
            reload_plugin,
            unload_plugin_async,
        )
        from arclet.entari.plugin.service import plugin_service
        from arclet.letoderea import global_providers, on
        from arclet.letoderea.core import run_handler
        from arclet.letoderea.utils import set_event_loop
        from creart import it
        from launart import Launart, Service

        from entari_plugin_htmlrender import (
            HtmlPreparer,
            HtmlRenderer,
            TemplateRenderer,
        )
        from entari_plugin_htmlrender.entari import HtmlRenderService
        from entari_plugin_htmlrender.entari.providers import (
            HtmlRenderContractProviderFactory,
        )
        from entari_plugin_htmlrender.graphics import GraphicsRenderer
        from entari_plugin_htmlrender.resources import ResourceAccess

        class HostService(Service):
            id = "entari.service"

            @property
            def required(self):
                return set()

            @property
            def stages(self):
                return {"preparing", "blocking", "cleanup"}

            async def launch(self, manager):
                async with self.stage("preparing"):
                    pass
                async with self.stage("blocking"):
                    await manager.status.wait_for_sigexit()
                async with self.stage("cleanup"):
                    pass

        class Probe:
            pass

        injected = {}

        def register_consumer():
            @on(Probe)
            async def consume(
                renderer: HtmlRenderer,
                templates: TemplateRenderer,
                preparation: HtmlPreparer,
                resources: ResourceAccess,
                graphics: GraphicsRenderer,
            ):
                injected.update(
                    renderer=renderer,
                    templates=templates,
                    preparation=preparation,
                    resources=resources,
                    graphics=graphics,
                )

            return consume

        def contract_instances(service):
            return {
                "renderer": service.renderer,
                "templates": service.templates,
                "preparation": service.preparation,
                "resources": service.resources,
                "graphics": service.graphics,
            }

        def contract_provider_count():
            return sum(
                type(provider).__name__ == "HtmlRenderContractProviderFactory"
                and type(provider).__module__
                == "entari_plugin_htmlrender.entari.providers"
                for provider in global_providers
            )

        async def wait_for_stage(service, stage):
            async with asyncio.timeout(10):
                while service.status.stage != stage:
                    await asyncio.sleep(0.01)

        async def wait_for_component_removal(manager, service_id):
            async with asyncio.timeout(10):
                while service_id in manager.components:
                    await asyncio.sleep(0.01)

        async def stop_manager(manager, launch):
            manager.status.exiting = True
            if manager.task_group is not None:
                # Entari dynamically sideloads its builtins with a shallow
                # ManagerStatus. Signal those trackers so the test manager can
                # enter cleanup after the plugin-specific assertions complete.
                trackers = list(manager.task_group.sideload_trackers.values())
                for tracker in trackers:
                    tracker.cancel()
                await asyncio.gather(*trackers, return_exceptions=True)
            await asyncio.wait_for(launch, timeout=10)

        async def exercise(directory: str) -> None:
            set_event_loop(asyncio.get_running_loop())
            EntariConfig(Path(directory) / "entari.yml")
            manager = it(Launart)
            manager.add_component(HostService())
            manager.add_component(plugin_service)

            launch = asyncio.create_task(manager.launch())
            await asyncio.wait_for(manager.status.wait_for_blocking(), timeout=5)
            await asyncio.wait_for(
                plugin_service.status.wait_for("blocking"),
                timeout=5,
            )

            initial = load_plugin(
                "entari_plugin_htmlrender",
                {"provider": None, "startup": "off"},
            )
            assert initial
            initial_plugin = initial.plugin
            initial_service = initial_plugin._services["htmlrender.runtime"]
            await wait_for_stage(initial_service, "blocking")

            consumer = register_consumer()

            async def assert_handler_uses(service) -> None:
                injected.clear()
                await asyncio.wait_for(
                    run_handler(consumer, Probe()),
                    timeout=10,
                )
                assert injected == contract_instances(service)

            await assert_handler_uses(initial_service)
            assert contract_provider_count() == 1

            failed = await asyncio.wait_for(
                reload_plugin(
                    "entari_plugin_htmlrender",
                    {"provider": "definitely-missing", "startup": "off"},
                ),
                timeout=10,
            )
            assert not failed
            assert failed.error is not None
            assert find_plugin("entari_plugin_htmlrender") is initial_plugin
            assert contract_provider_count() == 1
            await assert_handler_uses(initial_service)

            reloaded = await asyncio.wait_for(
                reload_plugin(
                    "entari_plugin_htmlrender",
                    {
                        "provider": None,
                        "startup": "off",
                        "html": {"max_source_bytes": 8192},
                    },
                ),
                timeout=10,
            )
            assert reloaded
            replacement_plugin = reloaded.plugin
            replacement_service = replacement_plugin._services["htmlrender.runtime"]
            await wait_for_stage(replacement_service, "blocking")

            assert replacement_plugin is not initial_plugin
            assert type(replacement_service) is not type(initial_service)
            assert replacement_service is not initial_service
            assert replacement_service.preparation is not None
            assert replacement_service._config.html.max_source_bytes == 8192
            assert initial_service.status.stage == "finished"
            assert (
                manager.get_component("htmlrender.runtime") is replacement_service
            )
            assert contract_provider_count() == 1
            await assert_handler_uses(replacement_service)

            disable_tasks = replacement_plugin.disable()
            if disable_tasks:
                await asyncio.wait_for(asyncio.wait(disable_tasks), timeout=10)
            await wait_for_component_removal(manager, "htmlrender.runtime")
            assert not replacement_plugin.is_available
            assert find_plugin("entari_plugin_htmlrender") is replacement_plugin

            injected.clear()
            try:
                await asyncio.wait_for(
                    run_handler(consumer, Probe()),
                    timeout=2,
                )
            except TimeoutError as error:
                raise AssertionError(
                    "disabled plugin DI created a waiter instead of failing fast"
                ) from error
            except Exception as error:
                cause = error
                while cause is not None:
                    if (
                        isinstance(cause, RuntimeError)
                        and str(cause) == "Entari HTMLRender is disabled."
                    ):
                        break
                    cause = cause.__cause__ or cause.__context__
                assert cause is not None, repr(error)
            else:
                raise AssertionError("disabled plugin unexpectedly resolved DI")

            assert await unload_plugin_async("entari_plugin_htmlrender")
            await wait_for_stage(replacement_service, "finished")
            await wait_for_component_removal(manager, "htmlrender.runtime")
            assert "htmlrender.runtime" not in manager.components
            assert contract_provider_count() == 0

            await stop_manager(manager, launch)

            consumer.dispose()
            del (
                initial,
                initial_plugin,
                initial_service,
                reloaded,
                replacement_plugin,
                replacement_service,
                consumer,
            )
            gc.collect()

        with TemporaryDirectory() as directory:
            original_cwd = Path.cwd()
            try:
                os.chdir(directory)
                asyncio.run(exercise(directory))
            finally:
                os.chdir(original_cwd)
        """
    )


def test_config_change_uses_default_atomic_reload() -> None:
    _run_isolated(
        """
        import asyncio
        import gc
        import json
        import os
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from arclet.entari import load_plugin
        from arclet.entari.config import EntariConfig
        from arclet.entari.plugin import unload_plugin_async
        from arclet.entari.plugin.apply import ConfigApplier
        from arclet.entari.plugin.service import plugin_service
        from arclet.letoderea.utils import set_event_loop
        from creart import it
        from launart import Launart, Service

        class HostService(Service):
            id = "entari.service"

            @property
            def required(self):
                return set()

            @property
            def stages(self):
                return {"preparing", "blocking", "cleanup"}

            async def launch(self, manager):
                async with self.stage("preparing"):
                    pass
                async with self.stage("blocking"):
                    await manager.status.wait_for_sigexit()
                async with self.stage("cleanup"):
                    pass

        async def wait_for_stage(service, stage):
            async with asyncio.timeout(10):
                while service.status.stage != stage:
                    await asyncio.sleep(0.01)

        async def wait_for_component_removal(manager, service_id):
            async with asyncio.timeout(10):
                while service_id in manager.components:
                    await asyncio.sleep(0.01)

        async def stop_manager(manager, launch):
            manager.status.exiting = True
            if manager.task_group is not None:
                # Entari dynamically sideloads its builtins with a shallow
                # ManagerStatus. Signal those trackers so the test manager can
                # enter cleanup after the plugin-specific assertions complete.
                trackers = list(manager.task_group.sideload_trackers.values())
                for tracker in trackers:
                    tracker.cancel()
                await asyncio.gather(*trackers, return_exceptions=True)
            await asyncio.wait_for(launch, timeout=10)

        async def exercise(directory: str) -> None:
            set_event_loop(asyncio.get_running_loop())
            config_path = Path(directory) / "entari.json"
            config_path.write_text(
                json.dumps(
                    {
                        "plugins": {
                            "entari_plugin_htmlrender": {
                                "provider": None,
                                "startup": "off",
                                "html": {"max_source_bytes": 4096},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            EntariConfig(config_path)

            manager = it(Launart)
            manager.add_component(HostService())
            manager.add_component(plugin_service)

            launch = asyncio.create_task(manager.launch())
            await asyncio.wait_for(manager.status.wait_for_blocking(), timeout=5)
            await asyncio.wait_for(
                plugin_service.status.wait_for("blocking"),
                timeout=5,
            )

            loaded = load_plugin(
                "entari_plugin_htmlrender",
                {
                    "provider": None,
                    "startup": "off",
                    "html": {"max_source_bytes": 4096},
                },
            )
            assert loaded
            old_plugin = loaded.plugin
            old_service = old_plugin._services["htmlrender.runtime"]
            assert old_service._config.html.max_source_bytes == 4096
            await wait_for_stage(old_service, "blocking")

            config_path.write_text(
                json.dumps(
                    {
                        "plugins": {
                            "entari_plugin_htmlrender": {
                                "provider": None,
                                "startup": "off",
                                "html": {"max_source_bytes": 8192},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            report = await asyncio.wait_for(ConfigApplier().apply(), timeout=10)

            assert report.ok
            assert "entari_plugin_htmlrender" in report.reloaded
            replacement_plugin = plugin_service.plugins[
                "entari_plugin_htmlrender"
            ]
            replacement_service = replacement_plugin._services[
                "htmlrender.runtime"
            ]
            await wait_for_stage(replacement_service, "blocking")

            assert replacement_plugin is not old_plugin
            assert replacement_service is not old_service
            assert old_service.status.stage == "finished"
            assert replacement_service._config.html.max_source_bytes == 8192
            assert (
                manager.get_component("htmlrender.runtime")
                is replacement_service
            )

            assert await unload_plugin_async("entari_plugin_htmlrender")
            await wait_for_stage(replacement_service, "finished")
            await wait_for_component_removal(manager, "htmlrender.runtime")
            await stop_manager(manager, launch)

            del (
                loaded,
                old_plugin,
                old_service,
                replacement_plugin,
                replacement_service,
            )
            gc.collect()

        with TemporaryDirectory() as directory:
            original_cwd = Path.cwd()
            try:
                os.chdir(directory)
                asyncio.run(exercise(directory))
            finally:
                os.chdir(original_cwd)
        """
    )
