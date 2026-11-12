"""Canonical drawing modules whose imports and reloads belong to Entari."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from contextvars import Context
from dataclasses import dataclass, field
import hashlib
import importlib
from importlib.machinery import ModuleSpec, PathFinder
from importlib.util import find_spec
from os import walk
from pathlib import Path
import sys
from typing import TYPE_CHECKING, TypeVar

import anyio
from arclet.entari.plugin import (
    find_plugin,
    get_plugin_references,
    get_plugins,
    load_plugin,
    reload_plugin,
    reload_subplugin,
    requires,
    unload_plugin,
    unload_plugin_async,
)
from arclet.entari.plugin.service import plugin_service

from entari_plugin_htmlrender._logging import logger
from entari_plugin_htmlrender.graphics.drawing_loader import (
    DrawingLoadError,
    DrawingNotFoundError,
    DrawingSpec,
    _validate_draw,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Coroutine, Mapping
    from typing import Any

    from entari_plugin_htmlrender.graphics.drawing_models import DrawingFunction
    from entari_plugin_htmlrender.resources.ports import WorkerExecutor


_R = TypeVar("_R")


async def _independent(operation: Coroutine[Any, Any, _R]) -> _R:
    def start() -> asyncio.Task[_R]:
        return asyncio.create_task(operation)

    task = Context().run(start)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Entari may already have disposed the live plugin and be waiting to
        # promote its staged replacement. Keep the pool lock until that atomic
        # operation finishes, even if the caller is cancelled repeatedly.
        with anyio.CancelScope(shield=True):
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
                except Exception:  # the caller's cancellation takes precedence
                    break
        if not task.cancelled():
            task.exception()
        raise


@dataclass(frozen=True, slots=True)
class _Source:
    name: str
    path: Path
    root: Path
    ancestors: tuple[str, ...]


@dataclass(slots=True)
class _OwnedPlugin:
    users: set[EntariDrawingRegistry] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class _Fingerprint:
    path: Path
    module: object
    digest: str | None


class _ImportPath(str):
    """Identity token for one path entry temporarily mounted by the pool."""

    __slots__ = ()


def _module_spec(name: str) -> ModuleSpec | None:
    """Resolve Python paths without importing a package before declaration."""
    search = None
    spec = None
    parts = name.split(".")
    for index in range(len(parts)):
        current = ".".join(parts[: index + 1])
        loaded = sys.modules.get(current)
        spec = getattr(loaded, "__spec__", None) if loaded is not None else None
        if spec is None:
            spec = PathFinder.find_spec(current, search)
        if spec is None and index == 0:
            spec = find_spec(current)
        if spec is None:
            return None
        search = spec.submodule_search_locations
        if search is None and index < len(parts) - 1:
            return None
    return spec


def _source_for(spec: DrawingSpec) -> _Source:
    if spec.path is None:
        assert spec.module is not None
        name = spec.module
        resolved = _module_spec(name)
        if (
            resolved is None
            or not resolved.origin
            or not resolved.origin.endswith(".py")
        ):
            raise DrawingLoadError(
                f"Drawing module {name!r} must resolve to a Python source file.",
                backend=spec.backend,
            )
        path = Path(resolved.origin).resolve()
        root = path.parent
        for _ in range(len(name.split(".")) - (path.name != "__init__.py")):
            root = root.parent
    else:
        path = spec.path.expanduser().resolve()
        if path.suffix != ".py" or not path.is_file():
            raise DrawingLoadError(
                f"Drawing source {path} must be an existing Python file.",
                backend=spec.backend,
            )
        candidates: list[tuple[int, Path, tuple[str, ...]]] = []
        for entry in sys.path:
            root = Path(entry or Path.cwd()).resolve()
            try:
                relative = path.relative_to(root)
            except ValueError:
                continue
            parts = relative.with_suffix("").parts
            if path.name == "__init__.py":
                parts = parts[:-1]
            if parts and all(part.isidentifier() for part in parts):
                candidates.append((len(root.parts), root, parts))
        if candidates:
            _, root, parts = max(candidates, key=lambda candidate: candidate[0])
        else:
            root = path.parent
            package_parts: list[str] = []
            while (root / "__init__.py").is_file():
                package_parts.insert(0, root.name)
                root = root.parent
            parts = tuple(package_parts)
            if path.name != "__init__.py":
                parts = (*parts, path.stem)
        if not parts or any(not part.isidentifier() for part in parts):
            raise DrawingLoadError(
                f"Drawing file {path} needs an importable Python module name.",
                backend=spec.backend,
            )
        name = ".".join(parts)
    ancestors = tuple(
        ".".join(name.split(".")[:index])
        for index in range(1, len(name.split(".")))
        if root.joinpath(*name.split(".")[:index], "__init__.py").is_file()
    )
    return _Source(name, path, root, ancestors)


def _digest(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        return f"{type(error).__name__}:{error}"


def _package_modules(source: _Source) -> dict[str, Path]:
    packages = source.ancestors
    if source.path.name == "__init__.py":
        packages = (*packages, source.name)
    if not packages:
        return {}
    package = packages[0]
    directory = source.root.joinpath(*package.split("."))
    modules: dict[str, Path] = {}
    for folder, directories, filenames in walk(directory):
        directories[:] = [
            name
            for name in directories
            if name.isidentifier() and name != "__pycache__"
        ]
        relative = Path(folder).relative_to(directory)
        prefix = (package, *relative.parts)
        for filename in filenames:
            path = Path(folder, filename)
            if path.suffix != ".py" or not path.stem.isidentifier():
                continue
            parts = prefix if filename == "__init__.py" else (*prefix, path.stem)
            modules[".".join(parts)] = path.resolve()
    return modules


def _plugin_roots() -> dict[str, str]:
    roots: dict[str, str] = {}
    for plugin in get_plugins():
        pending = [plugin.id]
        while pending:
            name = pending.pop()
            if name in roots:
                continue
            roots[name] = plugin.id
            if child := plugin_service.plugins.get(name):
                pending.extend(child.subplugins)
    return roots


class EntariDrawingPool:
    """Share owned plugin lifetimes across overlapping host runtime generations."""

    def __init__(self) -> None:
        self._owned: dict[str, _OwnedPlugin] = {}
        self._paths: dict[
            Path, tuple[_ImportPath | None, set[EntariDrawingRegistry]]
        ] = {}
        self._fingerprints: dict[str, _Fingerprint] = {}
        self._failed: dict[str, _Fingerprint] = {}
        self._lock = anyio.Lock()
        self._registries: set[EntariDrawingRegistry] = set()

    def registry(
        self,
        definitions: Mapping[str, DrawingSpec],
        *,
        worker: WorkerExecutor,
    ) -> EntariDrawingRegistry:
        registry = EntariDrawingRegistry(self, definitions, worker=worker)
        self._registries.add(registry)
        try:
            registry._initialize()
        except BaseException:
            self._release_now(registry)
            registry._closed = True
            raise
        return registry

    def _mount(self, registry: EntariDrawingRegistry, root: Path) -> None:
        if root not in self._paths:
            present = any(
                Path(entry or Path.cwd()).resolve() == root for entry in sys.path
            )
            token = None if present else _ImportPath(str(root))
            if token is not None:
                sys.path.insert(0, token)
            self._paths[root] = (token, set())
        self._paths[root][1].add(registry)
        registry._roots.add(root)

    def _claim(
        self,
        registry: EntariDrawingRegistry,
        before: set[str],
        *,
        dependencies_only: bool = False,
    ) -> None:
        roots = _plugin_roots()
        relevant = registry._dependencies()
        created = set(roots.values()) - before
        if dependencies_only:
            created.intersection_update(roots.get(name, name) for name in relevant)
        for root in created:
            self._owned.setdefault(root, _OwnedPlugin())
        for name in relevant:
            root = roots.get(name, name)
            if root in self._owned:
                self._owned[root].users.add(registry)
                registry._claimed.add(root)
        # Include newly created package roots, even when they have no import edges.
        for root in created:
            self._owned[root].users.add(registry)
            registry._claimed.add(root)

    def _release_candidates(
        self, registry: EntariDrawingRegistry | None = None
    ) -> set[str]:
        if registry is not None:
            for name in registry._claimed:
                if owned := self._owned.get(name):
                    owned.users.discard(registry)
        candidates = {name for name, owned in self._owned.items() if not owned.users}
        roots = _plugin_roots()
        # A separately loaded external plugin may now use a module we created.
        # Preserve such modules rather than disabling their independent consumers.
        while True:
            retained = {
                name
                for name in candidates
                if any(
                    roots.get(dependent, dependent) not in candidates
                    for dependent in plugin_service.dependents_of(name)
                )
            }
            if not retained:
                break
            candidates.difference_update(retained)
        return candidates

    def _release_paths(self, registry: EntariDrawingRegistry) -> None:
        for root in registry._roots:
            _, users = self._paths[root]
            users.discard(registry)
        registry._roots.clear()
        registry._claimed.clear()
        self._registries.discard(registry)
        self._prune_paths()

    def _prune_paths(self) -> None:
        retained = [
            Path(filename).resolve()
            for name in self._owned
            if (plugin := find_plugin(name)) is not None
            and (filename := getattr(plugin.module, "__file__", None))
        ]
        for root, (token, users) in tuple(self._paths.items()):
            if users or any(path.is_relative_to(root) for path in retained):
                continue
            if token is not None:
                sys.path[:] = [entry for entry in sys.path if entry is not token]
            del self._paths[root]
        importlib.invalidate_caches()

    def _release_now(self, registry: EntariDrawingRegistry) -> None:
        for name in sorted(self._release_candidates(registry), reverse=True):
            Context().run(unload_plugin, name)
            self._owned.pop(name, None)
        self._release_paths(registry)

    async def _release(self, registry: EntariDrawingRegistry) -> None:
        for name in sorted(self._release_candidates(registry), reverse=True):
            await _independent(unload_plugin_async(name))
            self._owned.pop(name, None)
        self._release_paths(registry)

    async def aclose(self) -> None:
        for registry in tuple(self._registries):
            await registry.aclose()
        async with self._lock:
            for name in sorted(self._release_candidates(), reverse=True):
                await _independent(unload_plugin_async(name))
                self._owned.pop(name, None)
            self._prune_paths()


class EntariDrawingRegistry:
    """A named view over Entari's canonical plugin registry and binding index."""

    def __init__(
        self,
        pool: EntariDrawingPool,
        definitions: Mapping[str, DrawingSpec],
        *,
        worker: WorkerExecutor,
    ) -> None:
        self._pool = pool
        self._specs = dict(definitions)
        self._worker = worker
        self._sources: dict[str, _Source] = {}
        self._declared: set[str] = set()
        self._roots: set[Path] = set()
        self._claimed: set[str] = set()
        self._closing = False
        self._closed = False
        self._active = 0
        self._drained = anyio.Event()
        self._drained.set()
        self._close_lock = anyio.Lock()

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._specs)

    def spec(self, name: str) -> DrawingSpec:
        try:
            return self._specs[name]
        except KeyError:
            raise DrawingNotFoundError(name) from None

    def _initialize(self) -> None:
        before = set(_plugin_roots().values())
        preexisting = set(plugin_service.plugins)
        observed: dict[Path, str] = {}
        try:
            for name, spec in self._specs.items():
                source = _source_for(spec)
                existing = _module_spec(source.name)
                if existing is not None and (
                    not existing.origin
                    or Path(existing.origin).resolve() != source.path
                ):
                    raise DrawingLoadError(
                        f"Drawing module {source.name!r} already resolves to a different source.",
                        backend=spec.backend,
                    )
                loaded = sys.modules.get(source.name)
                if loaded is not None and find_plugin(source.name) is None:
                    raise DrawingLoadError(
                        f"Drawing module {source.name!r} is already imported outside Entari; "
                        "load it through Entari before configuring it as a drawing.",
                        backend=spec.backend,
                    )
                self._sources[name] = source
                self._pool._mount(self, source.root)
                aliases = {
                    other.name
                    for registry in self._pool._registries
                    for other in registry._sources.values()
                    if other.path == source.path
                }
                aliases.update(
                    plugin.id
                    for plugin in get_plugins(subplugged=True)
                    if (filename := getattr(plugin.module, "__file__", None))
                    and Path(filename).resolve() == source.path
                )
                if aliases != {source.name}:
                    raise DrawingLoadError(
                        f"Drawing source {source.path} has conflicting module names: "
                        f"{', '.join(sorted(aliases))}.",
                        backend=spec.backend,
                    )
                observed[source.path] = _digest(source.path)
            self._declare()
            for source in self._sources.values():
                if existing_plugin := find_plugin(source.name):
                    if (
                        Path(existing_plugin.module.__file__ or "").resolve()
                        != source.path
                    ):
                        raise DrawingLoadError(
                            f"Entari plugin {source.name!r} owns a different source file."
                        )
                    continue
                loaded = Context().run(load_plugin, source.name)
                if not loaded:
                    raise DrawingLoadError(
                        f"Could not load Entari drawing module {source.name!r}: {loaded.error}",
                        source=loaded.error,
                    )
            for name in self._specs:
                self._callback(name)
            self._declare()
            for module, path in self._tracked_files().items():
                plugin = plugin_service.plugins[module]
                # A borrowed plugin may have been loaded from an earlier version
                # of its file. Its imported baseline is unknown until we reload.
                digest = (
                    observed.get(path, _digest(path))
                    if module not in preexisting
                    else None
                )
                self._pool._fingerprints.setdefault(
                    module, _Fingerprint(path, plugin.module, digest)
                )
            for name, spec in self._specs.items():
                if spec.reload:
                    self._check_managed_dependencies(name)
        finally:
            self._pool._claim(self, before)

    def _declare(self, *, for_reload: str | None = None) -> dict[str, Path]:
        files: dict[str, Path] = {}
        declarations: set[str] = set()
        for name, source in self._sources.items():
            modules = _package_modules(source)
            if self._specs[name].reload or name == for_reload:
                for module in modules:
                    if parent := plugin_service._subplugined.get(module):
                        raise DrawingLoadError(
                            f"Drawing helper {module!r} is already an Entari subplugin "
                            f"of {parent!r}; reload requires independent package modules. "
                            "Configure drawings or declare helpers with requires(...) "
                            "before their first import, and keep package __init__.py "
                            "free of eager local helper imports.",
                            backend=self._specs[name].backend,
                        )
            files.update(modules)
            files[source.name] = source.path
            declarations.update((*source.ancestors, source.name, *modules))
        if missing := declarations - self._declared:
            requires(*sorted(missing))
            self._declared.update(missing)
        return files

    def _dependencies(self, name: str | None = None) -> set[str]:
        sources = [self._sources[name]] if name is not None else self._sources.values()
        pending = [
            item for source in sources for item in (source.name, *source.ancestors)
        ]
        seen: set[str] = set()
        while pending:
            module = pending.pop()
            if module in seen:
                continue
            seen.add(module)
            plugin = plugin_service.plugins.get(module)
            if plugin is None:
                continue
            pending.extend(plugin.subplugins)
            pending.extend(get_plugin_references(plugin))
            pending.extend(
                binding.target for binding in plugin_service.bindings.get(module, ())
            )
        return seen

    def _tracked_files(self, name: str | None = None) -> dict[str, Path]:
        files: dict[str, Path] = {}
        for module in self._dependencies(name):
            if plugin := plugin_service.plugins.get(module):
                filename = getattr(plugin.module, "__file__", None)
                if filename and filename.endswith(".py"):
                    files[module] = Path(filename).resolve()
        return files

    def _check_managed_dependencies(self, name: str) -> None:
        source = self._sources[name]
        for module in self._dependencies(name):
            if module in plugin_service.plugins:
                continue
            loaded = sys.modules.get(module)
            filename = getattr(loaded, "__file__", None)
            if not filename or not filename.endswith(".py"):
                continue
            path = Path(filename).resolve()
            if path.is_relative_to(source.root) and "site-packages" not in path.parts:
                raise DrawingLoadError(
                    f"Drawing dependency {module!r} is not managed by Entari. "
                    "Use a real Python package with __init__.py or mark the "
                    "dependency import with '# entari: plugin' for reload support.",
                    backend=self._specs[name].backend,
                )

    def _callback(self, name: str) -> DrawingFunction:
        spec = self._specs[name]
        source = self._sources[name]
        plugin = find_plugin(source.name)
        if plugin is None or not plugin.available or not plugin.is_available:
            raise DrawingLoadError(
                f"Entari drawing module {source.name!r} is not available.",
                backend=spec.backend,
            )
        return _validate_draw(
            getattr(plugin.module, spec.function, None),
            function=spec.function,
            backend=spec.backend,
        )

    def _ensure_open(self) -> None:
        if self._closing or self._closed:
            raise DrawingLoadError("The Entari drawing registry is closed.")

    async def _refresh(self, name: str, *, explicit: bool) -> None:
        files = self._declare(for_reload=name)
        self._check_managed_dependencies(name)
        watched = self._tracked_files(name)
        for registry in self._pool._registries:
            files.update(registry._tracked_files())
        digests = await self._worker.run_sync(
            lambda: {module: _digest(path) for module, path in files.items()}
        )
        observed = {
            module: _Fingerprint(
                files[module], plugin_service.plugins[module].module, digest
            )
            for module, digest in digests.items()
            if module in plugin_service.plugins
        }
        changed = {
            module
            for module, fingerprint in observed.items()
            if module in watched
            and self._pool._fingerprints.get(module) != fingerprint
            and (explicit or self._pool._failed.get(module) != fingerprint)
        }
        if explicit:
            changed.add(self._sources[name].name)
        before = set(_plugin_roots().values())
        refreshed: set[str] = set()
        try:
            roots = _plugin_roots()
            for module in plugin_service.topo_dependents(changed):
                if module in refreshed or module not in plugin_service.plugins:
                    continue
                previous = {
                    item: plugin.module
                    for item, plugin in plugin_service.plugins.items()
                }
                operation = (
                    reload_subplugin
                    if roots.get(module, module) != module
                    else reload_plugin
                )
                result = await _independent(operation(module))
                if not result:
                    if module in observed:
                        self._pool._failed[module] = observed[module]
                    raise DrawingLoadError(
                        f"Could not reload Entari drawing dependency {module!r}: {result.error}",
                        backend=self._specs[name].backend,
                        source=result.error,
                    )
                # Native reloads also rebuild module-level dependents. Record
                # their new identities against the source observed before the
                # transaction, rather than reloading them on the next lease.
                for registry in self._pool._registries:
                    for item, path in registry._tracked_files().items():
                        current = plugin_service.plugins[item].module
                        if previous.get(item) is current:
                            continue
                        self._pool._fingerprints[item] = _Fingerprint(
                            path,
                            current,
                            digests.get(item) if files.get(item) == path else None,
                        )
                        self._pool._failed.pop(item, None)
                        refreshed.add(item)
            self._callback(name)
            for module, path in self._tracked_files(name).items():
                self._pool._fingerprints.setdefault(
                    module,
                    _Fingerprint(path, plugin_service.plugins[module].module, None),
                )
        finally:
            self._pool._claim(self, before)

    @asynccontextmanager
    async def lease(self, name: str) -> AsyncIterator[DrawingFunction]:
        spec = self.spec(name)
        async with self._pool._lock:
            self._ensure_open()
            if spec.reload:
                try:
                    await self._refresh(name, explicit=False)
                except DrawingLoadError as error:
                    logger.error("Could not refresh Entari drawing %r: %s", name, error)
            else:
                # Name-only discovery also covers new helpers imported lazily
                # by a drawing with source polling disabled. No bodies execute.
                self._declare()
            self._ensure_open()
            callback = self._callback(name)
            before = set(_plugin_roots().values())
            if self._active == 0:
                self._drained = anyio.Event()
            self._active += 1
        try:
            yield callback
        finally:
            self._pool._claim(self, before, dependencies_only=True)
            self._active -= 1
            if self._active == 0:
                self._drained.set()

    async def reload(self, name: str) -> None:
        self.spec(name)
        async with self._pool._lock:
            self._ensure_open()
            await self._refresh(name, explicit=True)

    async def aclose(self) -> None:
        async with self._close_lock:
            if self._closed:
                return
            self._closing = True
            with anyio.CancelScope(shield=True):
                await self._drained.wait()
                async with self._pool._lock:
                    await self._pool._release(self)
            self._closed = True
