#!/usr/bin/env python3
"""Load an installed Entari plugin through its real lifecycle in isolation.

This module must run with ``python -I`` from a temporary working directory.
It may import only the standard library and packages installed in the target
virtual environment; it must never import from the source checkout.
"""

import argparse
import asyncio
from collections.abc import Iterable, Sequence
import contextlib
from copy import deepcopy
from importlib.metadata import (
    PackageNotFoundError,
    distribution,
    version,
)
import io
import json
import os
from pathlib import Path
import platform
import re
import tempfile
from typing import Any, Protocol

RESULT_MARKER = "__ENTARI_PLUGIN_LOAD_CHECK_RESULT__="
PROBE_TIMEOUT_SECONDS = 30.0
ERROR_LIMIT = 1_200
_CANONICALIZE_RE = re.compile(r"[-_.]+")
_ANSI_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_REQUIREMENT_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_SENSITIVE_MARKERS = (
    "authorization",
    "cookie",
    "credential",
    "password",
    "passwd",
    "private",
    "secret",
    "token",
    "api-key",
    "apikey",
)


class ProbeFailure(RuntimeError):
    """A bounded, user-facing failure from one probe stage."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


class _ContractHandler(Protocol):
    async def __call__(self, context: object) -> object: ...


def canonicalize_name(value: str) -> str:
    """Return the PEP 503 normalized project name."""
    return _CANONICALIZE_RE.sub("-", value).lower()


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as stream:
            stream.write(serialized)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _config_scalar_strings(value: object) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _config_scalar_strings(item)
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            yield from _config_scalar_strings(item)
        return
    if isinstance(value, str):
        if value:
            yield value
        return
    if value is not None:
        yield str(value)


def _sanitize_error(
    error: BaseException,
    *,
    config: object,
    config_path: Path | None,
) -> str:
    message = _ANSI_RE.sub("", f"{type(error).__name__}: {error}")
    secrets = set(_config_scalar_strings(config))
    if config_path is not None:
        secrets.add(str(config_path))
    for secret in sorted(secrets, key=len, reverse=True):
        if len(secret) < 2:
            continue
        variants = {
            secret,
            json.dumps(secret, ensure_ascii=False)[1:-1],
            secret.replace("\n", "\\n"),
        }
        for variant in variants:
            if variant:
                message = message.replace(variant, "***")
    for marker in _SENSITIVE_MARKERS:
        message = re.sub(
            rf"(?i)({re.escape(marker)}[^\n:=]*[:=]\s*)[^\s,}}\]]+",
            r"\1***",
            message,
        )
    if len(message) > ERROR_LIMIT:
        return message[:ERROR_LIMIT] + "...<truncated>"
    return message


def _read_plugin_config(path: Path) -> dict[str, object]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ProbeFailure("config", "cannot read plugin config file") from error
    if not text.strip():
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise ProbeFailure(
            "config",
            f"plugin config must be one JSON object (line {error.lineno})",
        ) from error
    if not isinstance(value, dict):
        raise ProbeFailure("config", "plugin config must be one JSON object")
    return value


def _installed_environment(project_name: str) -> dict[str, str]:
    names = (
        "entari-plugin-htmlrender",
        "arclet-entari",
        "arclet-letoderea",
        "launart",
        "pydantic",
        "playwright",
        "pillow",
        "skia-python",
        "takumi-py",
    )
    result = {"python": platform.python_version()}
    for distribution_name in names:
        try:
            result[canonicalize_name(distribution_name)] = version(distribution_name)
        except PackageNotFoundError:
            continue
    with contextlib.suppress(PackageNotFoundError):
        result[canonicalize_name(project_name)] = version(project_name)
    return {canonicalize_name(name): installed for name, installed in result.items()}


def _applicable_requirement_name(requirement: str) -> str | None:
    requirement_text, separator, marker = requirement.partition(";")
    if separator and "extra" in marker.lower():
        return None
    match = _REQUIREMENT_NAME_RE.match(requirement_text)
    if match is None:
        return None
    return canonicalize_name(match.group(1))


def _dependency_report(project_name: str) -> dict[str, object]:
    try:
        project = distribution(project_name)
    except PackageNotFoundError as error:
        raise ProbeFailure(
            "dependencies",
            f"installed distribution {project_name!r} was not found",
        ) from error

    checked: list[str] = []
    missing: list[str] = []
    for requirement in project.requires or ():
        name = _applicable_requirement_name(requirement)
        if name is None or name == canonicalize_name(project_name):
            continue
        checked.append(name)
        try:
            distribution(name)
        except PackageNotFoundError:
            missing.append(name)
    if missing:
        raise ProbeFailure(
            "dependencies",
            "missing installed dependencies: " + ", ".join(sorted(set(missing))),
        )
    return {
        "checked": len(set(checked)),
        "missing": [],
    }


def _metadata_summary(metadata: object) -> dict[str, object]:
    role = getattr(metadata, "role", None)
    config = getattr(metadata, "config", None)
    return {
        "name": getattr(metadata, "name", None),
        "role": getattr(role, "value", role),
        "version": getattr(metadata, "version", None),
        "license": getattr(metadata, "license", None),
        "config": getattr(config, "__name__", None),
        "requirements": list(getattr(metadata, "requirements", ()) or ()),
    }


async def _wait_for_service(
    manager: object,
    service: object,
    *,
    expected_stage: str,
    threshold: float = PROBE_TIMEOUT_SECONDS,
) -> None:
    service_id = service.id  # type: ignore[attr-defined]
    status = service.status  # type: ignore[attr-defined]
    async with asyncio.timeout(threshold):
        while status.stage != expected_stage:
            task_group = manager.task_group  # type: ignore[attr-defined]
            tracker = None
            if task_group is not None:
                tracker = task_group.sideload_trackers.get(service_id)
            if tracker is not None and tracker.done():
                exception = tracker.exception()
                if exception is not None:
                    raise ProbeFailure(
                        "lifecycle",
                        f"service {service_id!r} lifecycle failed: "
                        f"{type(exception).__name__}: {exception}",
                    ) from exception
            await asyncio.sleep(0.01)
    stage = status.stage
    if stage != expected_stage:
        raise ProbeFailure(
            "lifecycle",
            f"service {service_id!r} reached {stage!r}, expected {expected_stage!r}",
        )


async def _wait_for_component_removal(
    manager: object,
    service_id: str,
    *,
    threshold: float = PROBE_TIMEOUT_SECONDS,
) -> None:
    removed = asyncio.Event()

    async def observe_removal() -> None:
        while (  # noqa: ASYNC110
            service_id in manager.components  # type: ignore[attr-defined]
        ):
            # Launart does not expose a removal future for sideloaded services.
            await asyncio.sleep(0.01)
        removed.set()

    observer = asyncio.create_task(observe_removal())
    async with asyncio.timeout(threshold):
        try:
            await removed.wait()
        finally:
            observer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await observer


def _contract_provider_count() -> int:
    from arclet.letoderea import global_providers  # noqa: PLC0415

    from entari_plugin_htmlrender.entari.providers import (  # noqa: PLC0415
        HtmlRenderContractProviderFactory,
    )

    return sum(
        isinstance(provider, HtmlRenderContractProviderFactory)
        for provider in global_providers
    )


async def _resolve_contracts(
    service: object,
    consumer: _ContractHandler,
    injected: dict[str, object],
) -> dict[str, bool]:
    from arclet.letoderea.core import run_handler  # noqa: PLC0415

    class Probe:
        pass

    injected.clear()
    await asyncio.wait_for(run_handler(consumer, Probe()), timeout=10)
    expected = {
        "renderer": service.renderer,  # type: ignore[attr-defined]
        "templates": service.templates,  # type: ignore[attr-defined]
        "preparation": service.preparation,  # type: ignore[attr-defined]
        "resources": service.resources,  # type: ignore[attr-defined]
        "graphics": service.graphics,  # type: ignore[attr-defined]
    }
    if injected != expected:
        raise ProbeFailure(
            "di",
            "Letoderea did not inject the five contracts from the active service",
        )
    return dict.fromkeys(expected, True)


def _provider_factories() -> tuple[object, ...]:
    from arclet.letoderea import global_providers  # noqa: PLC0415

    return tuple(
        provider
        for provider in global_providers
        if type(provider).__module__ == "entari_plugin_htmlrender.entari.providers"
        and type(provider).__name__ == "HtmlRenderContractProviderFactory"
    )


def _validate_plugin_service(
    plugin: object,
    service: object,
    *,
    stage: str,
) -> None:
    from launart import Service  # noqa: PLC0415

    if service.id != "htmlrender.runtime":  # type: ignore[attr-defined]
        raise ProbeFailure(
            stage,
            "plugin registered an unexpected service id",
        )
    if not isinstance(service, Service):
        raise ProbeFailure(
            stage,
            "plugin service does not implement the framework Service base",
        )
    service_type = type(service)
    if (
        service_type.__module__ != "entari_plugin_htmlrender.entari.service"
        or service_type.__qualname__ != "HtmlRenderService"
    ):
        raise ProbeFailure(
            stage,
            "plugin service has an unexpected implementation identity",
        )
    if not any(
        type(registered) is service_type
        for registered in plugin._services.values()  # type: ignore[attr-defined]
    ):
        raise ProbeFailure(
            stage,
            "plugin service is not owned by the returned plugin instance",
        )


async def _stop_manager(manager: object, launch: asyncio.Task[None]) -> None:
    manager.status.exiting = True  # type: ignore[attr-defined]
    task_group = manager.task_group  # type: ignore[attr-defined]
    if task_group is not None:
        trackers = list(getattr(task_group, "sideload_trackers", {}).values())
        for tracker in trackers:
            tracker.cancel()
        if trackers:
            await asyncio.gather(*trackers, return_exceptions=True)
    await asyncio.wait_for(launch, timeout=PROBE_TIMEOUT_SECONDS)


async def _run_probe(
    *,
    module_name: str,
    plugin_config: dict[str, object],
    result: dict[str, object],
) -> None:
    from arclet.entari import load_plugin  # noqa: PLC0415
    from arclet.entari.config import EntariConfig  # noqa: PLC0415
    from arclet.entari.plugin import (  # noqa: PLC0415
        PluginRole,
        find_plugin,
        reload_plugin,
        unload_plugin_async,
    )
    from arclet.entari.plugin.service import plugin_service  # noqa: PLC0415
    from arclet.letoderea.utils import set_event_loop  # noqa: PLC0415
    from creart import it  # noqa: PLC0415
    from launart import Launart, Service  # noqa: PLC0415
    from launart.status import Phase  # noqa: PLC0415

    class HostService(Service):
        id = "entari.service"

        @property
        def required(self) -> set[str]:
            return set()

        @property
        def stages(self) -> set[Phase]:
            return {"preparing", "blocking", "cleanup"}

        async def launch(self, manager: Launart) -> None:
            async with self.stage("preparing"):
                pass
            async with self.stage("blocking"):
                await manager.status.wait_for_sigexit()
            async with self.stage("cleanup"):
                pass

    injected: dict[str, object] = {}
    consume: Any = None

    set_event_loop(asyncio.get_running_loop())
    EntariConfig(Path.cwd() / ".entari-load-check.json")
    manager = it(Launart)
    manager.add_component(HostService())
    manager.add_component(plugin_service)
    launch = asyncio.create_task(manager.launch())
    loaded_plugin: object | None = None
    loaded_service: object | None = None

    try:
        result["stage"] = "manager"
        await asyncio.wait_for(
            manager.status.wait_for_blocking(),
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        await asyncio.wait_for(
            plugin_service.status.wait_for("blocking"),
            timeout=PROBE_TIMEOUT_SECONDS,
        )

        providers_before = _provider_factories()
        result["stage"] = "load"
        loaded = load_plugin(module_name, deepcopy(plugin_config))
        if not loaded:
            raise ProbeFailure(
                "load",
                f"Entari refused to load plugin: {type(loaded.error).__name__}: "
                f"{loaded.error}",
            )
        loaded_plugin = loaded.plugin
        plugin = loaded.plugin
        if not plugin.available:
            raise ProbeFailure("load", "loaded Entari plugin is unavailable")

        providers_after_load = _provider_factories()
        added_providers = tuple(
            provider
            for provider in providers_after_load
            if all(provider is not before for before in providers_before)
        )
        if (
            len(added_providers) != 1
            or len(providers_after_load) != len(providers_before) + 1
        ):
            raise ProbeFailure(
                "di",
                "loading the plugin did not add exactly one contract provider",
            )
        initial_plugin_provider = added_providers[0]
        # Import plugin-owned types only after Entari has loaded the entry
        # module. Importing them first would let Entari's import hook treat the
        # probe's own imports as the plugin load and invalidate the lifecycle
        # ordering under test.
        from arclet.letoderea import on  # noqa: PLC0415

        from entari_plugin_htmlrender.config import (  # noqa: PLC0415
            HtmlRenderConfig,
        )
        from entari_plugin_htmlrender.entari import (  # noqa: PLC0415
            HtmlRenderService,
        )
        from entari_plugin_htmlrender.graphics import (  # noqa: PLC0415
            GraphicsRenderer,
        )
        from entari_plugin_htmlrender.preparation.service import (  # noqa: PLC0415
            HtmlPreparer,
        )
        from entari_plugin_htmlrender.rendering.contracts import (  # noqa: PLC0415
            HtmlRenderer,
            TemplateRenderer,
        )
        from entari_plugin_htmlrender.resources import (  # noqa: PLC0415
            ResourceAccess,
        )

        class DiProbe:
            pass

        async def handle_contracts(
            renderer: HtmlRenderer,
            templates: TemplateRenderer,
            preparation: HtmlPreparer,
            resources: ResourceAccess,
            graphics: GraphicsRenderer,
        ) -> None:
            injected.update(
                renderer=renderer,
                templates=templates,
                preparation=preparation,
                resources=resources,
                graphics=graphics,
            )

        consume = on(DiProbe)(handle_contracts)

        metadata = plugin.metadata
        if metadata is None:
            raise ProbeFailure("metadata", "loaded Entari plugin has no metadata")
        if metadata.role is not PluginRole.LIBRARY:
            raise ProbeFailure(
                "metadata",
                f"plugin role is {metadata.role!r}, expected PluginRole.LIBRARY",
            )
        if metadata.config is not HtmlRenderConfig:
            raise ProbeFailure(
                "config",
                "plugin metadata config is not HtmlRenderConfig",
            )
        installed_version = result.get("installed_version")
        if installed_version and metadata.version != installed_version:
            raise ProbeFailure(
                "metadata",
                "plugin metadata version does not match the installed distribution",
            )
        result["metadata"] = _metadata_summary(metadata)

        service = plugin._services.get(HtmlRenderService.id)
        if not isinstance(service, HtmlRenderService):
            raise ProbeFailure(
                "service",
                f"plugin did not register {HtmlRenderService.id!r}",
            )
        loaded_service = service
        if not isinstance(service._config, HtmlRenderConfig):
            raise ProbeFailure(
                "config",
                "service did not retain the validated HtmlRenderConfig",
            )
        result["stage"] = "lifecycle"
        await _wait_for_service(
            manager,
            service,
            expected_stage="blocking",
        )

        result["stage"] = "di"
        await _resolve_contracts(service, consume, injected)
        contracts = {
            "renderer": True,
            "templates": True,
            "preparation": True,
            "resources": True,
            "graphics": True,
        }

        result["stage"] = "reload"
        replacement = await asyncio.wait_for(
            reload_plugin(module_name, deepcopy(plugin_config)),
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        if not replacement:
            raise ProbeFailure(
                "reload",
                f"Entari refused to reload plugin: "
                f"{type(replacement.error).__name__}: {replacement.error}",
            )
        replacement_plugin = replacement.plugin
        replacement_service = replacement_plugin._services.get(HtmlRenderService.id)
        if replacement_service is None:
            raise ProbeFailure(
                "reload",
                "reloaded plugin did not register an HtmlRenderService",
            )
        _validate_plugin_service(
            replacement_plugin,
            replacement_service,
            stage="reload",
        )
        if replacement_service is service:
            raise ProbeFailure(
                "reload",
                "hot reload reused the previous service instance",
            )
        await _wait_for_service(
            manager,
            replacement_service,
            expected_stage="blocking",
        )
        if service.status.stage != "finished":
            raise ProbeFailure(
                "reload",
                "the previous service did not finish during hot reload",
            )
        if manager.get_component(HtmlRenderService.id) is not replacement_service:
            raise ProbeFailure(
                "reload",
                "Launart did not promote the replacement service",
            )
        replacement_providers = _provider_factories()
        result["provider_counts"] = {
            "before": len(providers_before),
            "load": len(providers_after_load),
            "reload": len(replacement_providers),
        }
        if (
            len(replacement_providers) != 1
            or replacement_providers[0] is initial_plugin_provider
        ):
            raise ProbeFailure(
                "reload",
                "hot reload did not leave one plugin-owned provider replacement",
            )
        await _resolve_contracts(replacement_service, consume, injected)
        loaded_plugin = replacement_plugin
        loaded_service = replacement_service

        result["stage"] = "unload"
        if not await unload_plugin_async(module_name):
            raise ProbeFailure("unload", "Entari did not report an unload")
        await _wait_for_service(
            manager,
            replacement_service,
            expected_stage="finished",
        )
        await _wait_for_component_removal(manager, HtmlRenderService.id)
        if find_plugin(module_name) is not None:
            raise ProbeFailure("unload", "plugin remained loaded after unloading")
        if _provider_factories():
            raise ProbeFailure(
                "unload",
                "contract providers remained registered after unloading",
            )

        result["lifecycle"] = {
            "manager": "blocking",
            "service": "blocking",
            "reload": "replaced",
            "unload": "finished",
        }
        result["di"] = {"contracts": contracts}
        result["service"] = {
            "id": HtmlRenderService.id,
            "startup_policy": service._config.startup.value,
            "capabilities": sorted(
                replacement_service.capabilities.available_names  # type: ignore[attr-defined]
            ),
        }
        result["stage"] = "complete"
    finally:
        if consume is not None:
            with contextlib.suppress(BaseException):
                consume.dispose()
        if loaded_plugin is not None and find_plugin(module_name) is not None:
            with contextlib.suppress(BaseException):
                await unload_plugin_async(module_name)
        with contextlib.suppress(BaseException):
            if loaded_service is not None:
                await _wait_for_service(
                    manager,
                    loaded_service,
                    expected_stage="finished",
                    threshold=5,
                )
        with contextlib.suppress(BaseException):
            await _stop_manager(manager, launch)


def _base_result(
    *,
    module_name: str,
    project_name: str,
) -> dict[str, object]:
    installed_version = None
    try:
        project = distribution(project_name)
        installed_version = project.version
        installed_distribution_name = project.metadata["Name"]
    except PackageNotFoundError:
        installed_distribution_name = None
    return {
        "ok": False,
        "stage": "validate",
        "module_name": module_name,
        "project_name": installed_distribution_name or project_name,
        "installed_version": installed_version,
    }


def _validate_names(
    *,
    module_name: str,
    project_name: str,
) -> None:
    if not module_name or any(character.isspace() for character in module_name):
        raise ProbeFailure("validate", "module name must be a non-empty import path")
    if any(not part.isidentifier() for part in module_name.split(".")):
        raise ProbeFailure("validate", "module name is not a valid import path")
    if not project_name.strip():
        raise ProbeFailure("validate", "project name must not be empty")
    try:
        project = distribution(project_name)
    except PackageNotFoundError as error:
        raise ProbeFailure(
            "metadata",
            f"installed distribution {project_name!r} was not found",
        ) from error
    declared_name = project.metadata["Name"]
    if canonicalize_name(declared_name) != canonicalize_name(project_name):
        raise ProbeFailure(
            "metadata",
            "project name does not identify the installed distribution",
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module-name", required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--config-file", required=True)
    parser.add_argument("--result-file", required=True)
    return parser


def _write_and_print(
    result_file: Path,
    result: dict[str, object],
) -> None:
    _atomic_write_json(result_file, result)
    print(  # noqa: T201 -- marker protocol for the orchestrator
        RESULT_MARKER + json.dumps(result, ensure_ascii=False, sort_keys=True)
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result_file = Path(args.result_file)
    config_path = Path(args.config_file)
    result = _base_result(
        module_name=args.module_name,
        project_name=args.project_name,
    )
    plugin_config: dict[str, object] = {}

    captured_stdout = io.StringIO()
    captured_stderr = io.StringIO()
    try:
        _validate_names(
            module_name=args.module_name,
            project_name=args.project_name,
        )
        result["installed_environment"] = _installed_environment(args.project_name)
        result["dependencies"] = _dependency_report(args.project_name)
        plugin_config = _read_plugin_config(config_path)
        with (
            contextlib.redirect_stdout(captured_stdout),
            contextlib.redirect_stderr(captured_stderr),
        ):
            try:
                from loguru import logger  # noqa: PLC0415

                logger.remove()
            except ImportError:
                pass
            asyncio.run(
                _run_probe(
                    module_name=args.module_name,
                    plugin_config=plugin_config,
                    result=result,
                )
            )
        result["ok"] = True
        result["config_present"] = bool(config_path.read_text(encoding="utf-8").strip())
    except ProbeFailure as error:
        result["stage"] = error.stage
        result["error"] = _sanitize_error(
            error,
            config=plugin_config,
            config_path=config_path,
        )
    except BaseException as error:
        result["stage"] = str(result.get("stage") or "error")
        result["error"] = _sanitize_error(
            error,
            config=plugin_config,
            config_path=config_path,
        )

    try:
        _write_and_print(result_file, result)
    except OSError as error:
        print(  # noqa: T201 -- marker protocol even when result storage fails
            RESULT_MARKER
            + json.dumps(
                {
                    "ok": False,
                    "stage": "result",
                    "error": f"{type(error).__name__}: cannot write result file",
                    "module_name": args.module_name,
                    "project_name": args.project_name,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
