"""Isolated, reloadable Python drawing templates."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
import hashlib
import importlib
from importlib.abc import MetaPathFinder
from importlib.machinery import ModuleSpec, PathFinder, SourceFileLoader
from importlib.util import find_spec, spec_from_file_location
import inspect
from pathlib import Path
import sys
import threading
import types
from typing import TYPE_CHECKING, cast, final
import uuid

import anyio

from entari_plugin_htmlrender._logging import logger
from entari_plugin_htmlrender.errors import GraphicsError

if TYPE_CHECKING:
    from entari_plugin_htmlrender.graphics.models import GraphicsBackendName
    from entari_plugin_htmlrender.resources.ports import WorkerExecutor

DrawingCallable = Callable[[object, Mapping[str, object]], None]

_PRIVATE_ROOT = "_entari_htmlrender_drawings"


class DrawingLoadError(GraphicsError):
    """A configured drawing source could not be loaded or validated."""

    def __init__(
        self,
        message: str,
        *,
        backend: str | None = None,
        source: BaseException | None = None,
    ) -> None:
        super().__init__(
            message,
            backend=backend,
            operation="drawing_load",
            retryable=True,
            source=source,
        )


class DrawingNotFoundError(GraphicsError):
    """A drawing name is absent from the configured registry."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(
            f"Drawing template {name!r} is not configured.",
            backend=None,
            operation="drawing_load",
            retryable=False,
        )


@dataclass(frozen=True, slots=True)
class DrawingSpec:
    """One named drawing source and its backend metadata."""

    backend: GraphicsBackendName
    path: Path | None = None
    module: str | None = None
    function: str = "draw"
    reload: bool = False

    def __post_init__(self) -> None:
        if (self.path is None) == (self.module is None):
            raise ValueError("DrawingSpec requires exactly one of path or module")
        if self.path is not None and not isinstance(self.path, Path):
            raise TypeError("DrawingSpec.path must be a pathlib.Path")
        if self.module is not None:
            if not isinstance(self.module, str) or not self.module.strip():
                raise TypeError("DrawingSpec.module must be a non-empty string")
            if self.module.startswith("."):
                raise ValueError("DrawingSpec.module must be absolute")
        if not isinstance(self.function, str) or not self.function.isidentifier():
            raise ValueError("DrawingSpec.function must be a Python identifier")
        if not isinstance(self.reload, bool):
            raise TypeError("DrawingSpec.reload must be a bool")


@dataclass(slots=True)
class _LeaseState:
    active: int = 0
    retired: bool = False
    drained: anyio.Event = field(default_factory=anyio.Event)

    def __post_init__(self) -> None:
        self.drained.set()


@dataclass(slots=True, eq=False)
class _Generation:
    namespace: str
    package: types.ModuleType
    source: _Source
    finder: _DrawingFinder
    draw: DrawingCallable
    paths: dict[str, Path]
    probes: dict[str, tuple[Path, ...]]
    fingerprint: str
    lease: _LeaseState = field(default_factory=_LeaseState)
    closed: bool = False


@dataclass(frozen=True, slots=True)
class _Failure:
    source: _Source
    fingerprint: str
    error: DrawingLoadError
    paths: dict[str, Path]
    probes: dict[str, tuple[Path, ...]]


@dataclass(frozen=True, slots=True)
class _Observation:
    kind: str
    data: bytes = b""


class _CandidateLoadError(DrawingLoadError):
    def __init__(
        self,
        error: DrawingLoadError,
        *,
        paths: dict[str, Path],
        probes: dict[str, tuple[Path, ...]],
        observations: dict[Path, _Observation],
    ) -> None:
        self.error = error
        self.paths = paths
        self.probes = probes
        self.observations = observations
        self.fingerprint = _fingerprint(
            paths,
            probes,
            observations=observations,
        )
        super().__init__(
            error.message,
            backend=error.backend,
            source=error,
        )
        self.message = error.message


@dataclass(frozen=True, slots=True)
class _Source:
    path: Path
    root: Path
    logical_parts: tuple[str, ...]
    is_package: bool

    @property
    def module_parts(self) -> tuple[str, ...]:
        return self.logical_parts if self.is_package else self.logical_parts[:-1]


class _DrawingFinder(MetaPathFinder):
    """Resolve only one generation's private filesystem imports."""

    def __init__(self, namespace: str, source: _Source) -> None:
        self.namespace = namespace
        self.source = source
        self.paths: dict[str, Path] = {}
        self.probes: dict[str, tuple[Path, ...]] = {}
        self.observations: dict[Path, _Observation] = {}
        self.source_bytes: dict[str, bytes] = {}
        self.lock = threading.RLock()

    def find_spec(
        self,
        fullname: str,
        path: object = None,
        target: types.ModuleType | None = None,
    ) -> ModuleSpec | None:
        del path, target
        prefix = f"{self.namespace}."
        if not fullname.startswith(prefix):
            return None
        suffix = fullname.removeprefix(prefix)
        logical = suffix
        source_logical = ".".join(self.source.logical_parts)
        candidates = (
            (self.source.path,)
            if logical == source_logical
            else _module_paths(
                self.source.root,
                tuple(suffix.split(".")),
            )
        )
        with self.lock:
            self.probes[logical] = candidates
        for path in candidates:
            observation = _observe_file(path)
            with self.lock:
                self.observations[path] = observation
            if observation.kind != "file":
                continue
            spec = spec_from_file_location(
                fullname,
                path,
                loader=_SourceLoader(fullname, path, observation.data),
                submodule_search_locations=(
                    [str(path.parent)] if path.name == "__init__.py" else None
                ),
            )
            if spec is not None:
                with self.lock:
                    self.paths[logical] = path
                    self.source_bytes[logical] = observation.data
                return spec
        return None


class _SourceLoader(SourceFileLoader):
    """Read current source bytes without consulting or writing bytecode."""

    def __init__(self, fullname: str, path: Path, data: bytes) -> None:
        super().__init__(fullname, str(path))
        self._data = data

    def get_code(self, fullname: str) -> types.CodeType:
        path = self.get_filename(fullname)
        return self.source_to_code(self._data, path)


def _module_paths(
    root: Path,
    parts: tuple[str, ...],
) -> tuple[Path, ...]:
    if not parts:
        return ()
    relative = Path(*parts)
    return (
        root.joinpath(relative, "__init__.py"),
        root.joinpath(relative).with_suffix(".py"),
    )


def _observe_file(path: Path) -> _Observation:
    try:
        if not path.is_file():
            return _Observation("missing")
        return _Observation("file", path.read_bytes())
    except OSError as error:
        return _Observation(f"error:{type(error).__name__}")


def _find_canonical_spec(module: str) -> ModuleSpec | None:
    parts = module.split(".")
    search_path: list[str] | None = None
    spec: ModuleSpec | None = None
    for index in range(len(parts)):
        name = ".".join(parts[: index + 1])
        spec = PathFinder.find_spec(name, search_path)
        if spec is None and index == 0:
            spec = find_spec(name)
        if spec is None:
            return None
        search_path = spec.submodule_search_locations
        if search_path is None and index < len(parts) - 1:
            return None
    return spec


def _package_layout(path: Path) -> tuple[Path, tuple[str, ...]]:
    is_package = path.name == "__init__.py"
    probe = path.parent
    package_parts: list[str] = []
    while (probe / "__init__.py").is_file():
        package_parts.append(probe.name)
        probe = probe.parent
    parts = tuple(reversed(package_parts))
    leaf = path.stem if "." not in path.stem else "_drawing"
    return probe, parts if is_package else (*parts, leaf)


def _source_for(definition: DrawingSpec) -> _Source:
    if definition.path is not None:
        path = definition.path.expanduser().resolve()
        root, logical_parts = _package_layout(path)
        return _Source(
            path=path,
            root=root,
            logical_parts=logical_parts,
            is_package=path.name == "__init__.py",
        )

    assert definition.module is not None
    spec = _find_canonical_spec(definition.module)
    if spec is None or spec.origin is None or not spec.origin.endswith(".py"):
        raise DrawingLoadError(
            f"Drawing module {definition.module!r} does not resolve to a Python source file.",
            backend=definition.backend,
        )
    path = Path(spec.origin).resolve()
    parts = tuple(definition.module.split("."))
    if path.name == "__init__.py":
        root = path.parent
        for _ in range(len(parts)):
            root = root.parent
        return _Source(path=path, root=root, logical_parts=parts, is_package=True)
    root = path.parent
    for _ in range(len(parts) - 1):
        root = root.parent
    return _Source(path=path, root=root, logical_parts=parts, is_package=False)


def _fingerprint(
    paths: Mapping[str, Path],
    probes: Mapping[str, tuple[Path, ...]],
    *,
    observations: Mapping[Path, _Observation],
) -> str:
    digest = hashlib.sha256()
    for name, path in sorted(paths.items()):
        observation = observations.get(path, _Observation("missing"))
        for value in (
            name.encode(),
            str(path).encode(),
            observation.kind.encode(),
            observation.data,
        ):
            digest.update(value)
            digest.update(b"\0")
    for name, candidates in sorted(probes.items()):
        digest.update(name.encode())
        digest.update(b"\0")
        for path in candidates:
            observation = observations.get(path, _Observation("missing"))
            digest.update(str(path).encode())
            digest.update(b"\0")
            digest.update(observation.kind.encode())
            digest.update(b"\0")
            if paths.get(name) == path:
                break
    return digest.hexdigest()


def _observations_for(
    paths: Mapping[str, Path],
    probes: Mapping[str, tuple[Path, ...]],
) -> dict[Path, _Observation]:
    return {
        path: _observe_file(path)
        for path in dict.fromkeys(
            (*paths.values(), *(item for items in probes.values() for item in items))
        )
    }


def _current_snapshot(
    source: _Source,
    tracked: _Generation | _Failure | None = None,
) -> tuple[str, dict[str, Path], dict[str, tuple[Path, ...]]]:
    probes: dict[str, tuple[Path, ...]]
    if tracked is None:
        paths = _base_paths(source)
        probes = {".".join(source.logical_parts): (source.path,)}
    else:
        paths = dict(tracked.paths)
        probes = dict(tracked.probes)
        if isinstance(tracked, _Generation):
            # Imports inside draw() are discovered after the initial module load.
            # Their baseline must use the bytes actually compiled by the finder.
            with tracked.finder.lock:
                paths.update(tracked.finder.paths)
                probes.update(tracked.finder.probes)
                observations = dict(tracked.finder.observations)
            tracked.paths = paths
            tracked.probes = probes
            tracked.fingerprint = _fingerprint(paths, probes, observations=observations)
        paths = dict(paths)
        paths[_PRIVATE_ROOT] = source.path
    return (
        _fingerprint(paths, probes, observations=_observations_for(paths, probes)),
        paths,
        probes,
    )


def _claim(name: str, module: types.ModuleType) -> None:
    if name in sys.modules:
        raise DrawingLoadError(
            f"Private drawing namespace {name!r} is already occupied."
        )
    sys.modules[name] = module


def _private_package(name: str, path: Path) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    module.__package__ = name
    module.__spec__ = ModuleSpec(name, loader=None, is_package=True)
    module.__spec__.submodule_search_locations = module.__path__
    return module


def _visible_positional_count(signature: inspect.Signature) -> int:
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
    ]
    required = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.default is inspect.Parameter.empty
        and parameter.kind
        not in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }
    ]
    return len(positional) if len(required) <= 2 and len(positional) >= 2 else -1


def _validate_draw(
    value: object,
    *,
    function: str,
    backend: str,
) -> DrawingCallable:
    if not callable(value):
        raise DrawingLoadError(
            f"Drawing function {function!r} is not callable.",
            backend=backend,
        )
    if inspect.iscoroutinefunction(value):
        raise DrawingLoadError(
            f"Drawing function {function!r} must be synchronous.",
            backend=backend,
        )
    try:
        signature = inspect.signature(value)
    except (TypeError, ValueError) as error:
        raise DrawingLoadError(
            f"Drawing function {function!r} has an uninspectable signature.",
            backend=backend,
            source=error,
        ) from error
    if _visible_positional_count(signature) < 0:
        raise DrawingLoadError(
            f"Drawing function {function!r} must accept the canvas and request "
            "as its two bindable positional arguments.",
            backend=backend,
        )
    try:
        signature.bind(object(), {})
    except TypeError as error:
        raise DrawingLoadError(
            f"Drawing function {function!r} cannot bind the canvas and request.",
            backend=backend,
            source=error,
        ) from error
    return cast("DrawingCallable", value)


def _remove_generation(generation: _Generation) -> None:
    _discard_owned_namespace(
        generation.namespace, generation.package, generation.finder
    )


def _discard_owned_namespace(
    namespace: str,
    module: types.ModuleType,
    finder: _DrawingFinder,
) -> None:
    with suppress(ValueError):
        sys.meta_path.remove(finder)
    if sys.modules.get(namespace) is not module:
        return
    prefix = f"{namespace}."
    for name in list(sys.modules):
        if name == namespace or name.startswith(prefix):
            sys.modules.pop(name, None)


def _module_paths_for(source: _Source) -> tuple[Path, ...]:
    paths: list[Path] = []
    current = source.root
    for part in source.logical_parts[:-1]:
        current = current / part
        paths.append(current / "__init__.py")
    paths.append(source.path)
    return tuple(paths)


def _base_paths(source: _Source) -> dict[str, Path]:
    paths = {_PRIVATE_ROOT: source.path}
    for path in _module_paths_for(source)[:-1]:
        parent = path.parent
        relative = parent.relative_to(source.root)
        paths[".".join(relative.parts)] = path
    return paths


def _load_generation(
    definition: DrawingSpec,
    source: _Source,
    namespace: str,
) -> _Generation:
    finder = _DrawingFinder(namespace, source)
    paths = _base_paths(source)
    logical = ".".join(source.logical_parts)
    probes: dict[str, tuple[Path, ...]] = {logical: (source.path,)}
    observations = _observations_for(paths, probes)
    root_package = _private_package(namespace, source.root)
    claimed = False
    success = False

    def tracking() -> None:
        with finder.lock:
            paths.update(finder.paths)
            probes.update(finder.probes)
            observations.update(finder.observations)
            # Keep baseline observations for aliases and unexecuted parent paths.
            finder.observations.update(observations)

    try:
        _claim(namespace, root_package)
        claimed = True
        sys.meta_path.insert(0, finder)
        module = importlib.import_module(f"{namespace}.{logical}")
        draw = _validate_draw(
            getattr(module, definition.function, None),
            function=definition.function,
            backend=definition.backend,
        )
        tracking()
        candidate_fingerprint = _fingerprint(paths, probes, observations=observations)
        if candidate_fingerprint != _fingerprint(
            paths, probes, observations=_observations_for(paths, probes)
        ):
            raise DrawingLoadError(
                f"Drawing source {source.path} changed during import.",
                backend=definition.backend,
            )
        generation = _Generation(
            namespace=namespace,
            package=root_package,
            source=source,
            finder=finder,
            draw=draw,
            paths=paths,
            probes=probes,
            fingerprint=candidate_fingerprint,
        )
        success = True
        return generation
    except BaseException as error:
        tracking()
        wrapped = (
            error
            if isinstance(error, DrawingLoadError)
            else DrawingLoadError(
                f"Could not load drawing source {source.path}: {error}",
                backend=definition.backend,
                source=error,
            )
        )
        raise _CandidateLoadError(
            wrapped,
            paths=paths,
            probes=probes,
            observations=observations,
        ) from error
    finally:
        if claimed and not success:
            _discard_owned_namespace(namespace, root_package, finder)


@final
class DrawingRegistry:
    """Own lazily loaded, atomically replaceable drawing generations."""

    def __init__(
        self,
        specs: Mapping[str, DrawingSpec],
        *,
        worker: WorkerExecutor,
    ) -> None:
        self._specs = dict(specs)
        self._worker = worker
        self._state_lock = threading.RLock()
        self._locks_guard = threading.Lock()
        self._refresh_locks: dict[str, anyio.Lock] = {}
        self._generations: dict[str, _Generation] = {}
        self._retired: dict[str, set[_Generation]] = {}
        self._failed: dict[str, _Failure] = {}
        self._closed = False
        self._close_lock = anyio.Lock()

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._specs)

    def spec(self, name: str) -> DrawingSpec:
        try:
            return self._specs[name]
        except KeyError:
            raise DrawingNotFoundError(name) from None

    @asynccontextmanager
    async def lease(
        self,
        name: str,
    ) -> AsyncIterator[DrawingCallable]:
        definition = self.spec(name)
        generation = await self._lease_generation(name, definition)
        try:
            yield generation.draw
        finally:
            with anyio.CancelScope(shield=True):
                await self._release(name, generation)

    async def reload(self, name: str) -> None:
        definition = self.spec(name)
        async with self._refresh_lock_for(name):
            with self._state_lock:
                self._ensure_open(name, definition=definition)
                tracked = self._generations.get(name) or self._failed.get(name)
            source = await self._resolve_source(definition, tracked)
            await self._load(name, definition, source, explicit=True, pin=False)

    async def aclose(self) -> None:
        with self._state_lock:
            self._closed = True
        async with self._close_lock:
            acquired: list[anyio.Lock] = []
            try:
                for lock in self._all_refresh_locks():
                    await lock.acquire()
                    acquired.append(lock)
                with self._state_lock:
                    for name, generation in self._generations.items():
                        generation.lease.retired = True
                        self._retired.setdefault(name, set()).add(generation)
                    self._generations.clear()
                    retired = [
                        (name, generation)
                        for name, generations in self._retired.items()
                        for generation in generations
                    ]
                for name, generation in retired:
                    if generation.lease.active == 0:
                        await self._retire(name, generation)
                    await generation.lease.drained.wait()
            finally:
                for lock in reversed(acquired):
                    lock.release()

    async def _resolve_source(
        self,
        definition: DrawingSpec,
        tracked: _Generation | _Failure | None,
    ) -> _Source:
        try:
            return await self._worker.run_sync(_source_for, definition)
        except (ImportError, ValueError, OSError, DrawingLoadError) as error:
            if tracked is not None:
                # A removed module must still use last-good fallback and recover
                # when its source reappears at the original location.
                return tracked.source
            if isinstance(error, DrawingLoadError):
                raise
            raise DrawingLoadError(
                f"Could not resolve drawing source: {error}",
                backend=definition.backend,
                source=error,
            ) from error

    def _pin(self, generation: _Generation) -> None:
        if generation.lease.active == 0:
            generation.lease.drained = anyio.Event()
        generation.lease.active += 1

    async def _lease_generation(
        self,
        name: str,
        definition: DrawingSpec,
    ) -> _Generation:
        async with self._refresh_lock_for(name):
            with self._state_lock:
                self._ensure_open(name, definition=definition)
                current = self._generations.get(name)
                failure = self._failed.get(name)
                if not definition.reload and current is not None:
                    self._pin(current)
                    return current
            source = await self._resolve_source(definition, current or failure)
            if current is not None:
                fingerprint, _, _ = await self._worker.run_sync(
                    _current_snapshot, source, current
                )
                with self._state_lock:
                    self._ensure_open(name, definition=definition)
                    if fingerprint == current.fingerprint:
                        self._failed.pop(name, None)
                        self._pin(current)
                        return current
            if failure is not None:
                fingerprint, _, _ = await self._worker.run_sync(
                    _current_snapshot, source, failure
                )
                with self._state_lock:
                    self._ensure_open(name, definition=definition)
                    if fingerprint == failure.fingerprint:
                        if current is not None:
                            self._pin(current)
                            return current
                        raise failure.error
            generation = await self._load(
                name,
                definition,
                source,
                explicit=not definition.reload,
                pin=True,
            )
            assert generation is not None
            return generation

    async def _load(
        self,
        name: str,
        definition: DrawingSpec,
        source: _Source,
        *,
        explicit: bool,
        pin: bool,
    ) -> _Generation | None:
        namespace = _generation_namespace()
        candidate: _Generation | None = None
        installed = False
        try:
            try:
                # Keep the worker attached until its namespace can be cleaned.
                with anyio.CancelScope(shield=True):
                    candidate = await self._worker.run_sync(
                        _load_generation, definition, source, namespace
                    )
                assert candidate is not None
                fingerprint, _, _ = await self._worker.run_sync(
                    _current_snapshot, source, candidate
                )
                if fingerprint != candidate.fingerprint:
                    raise DrawingLoadError(
                        f"Drawing source {source.path} changed during import.",
                        backend=definition.backend,
                    )
            except DrawingLoadError as error:
                if isinstance(error, _CandidateLoadError):
                    failure = _Failure(
                        source,
                        error.fingerprint,
                        error.error,
                        error.paths,
                        error.probes,
                    )
                    reported = error.error
                else:
                    assert candidate is not None
                    failure = _Failure(
                        source,
                        candidate.fingerprint,
                        error,
                        candidate.paths,
                        candidate.probes,
                    )
                    reported = error
                with self._state_lock:
                    previous = self._generations.get(name)
                    old_failure = self._failed.get(name)
                    self._failed[name] = failure
                if previous is not None and (
                    old_failure is None
                    or old_failure.fingerprint != failure.fingerprint
                ):
                    logger.error(
                        "Could not reload drawing %r from %s; keeping the prior "
                        "generation: %s",
                        name,
                        source.path,
                        reported,
                    )
                if explicit or previous is None:
                    raise reported from None
                with self._state_lock:
                    self._ensure_open(name, definition=definition)
                    if pin:
                        self._pin(previous)
                return previous

            assert candidate is not None
            with self._state_lock:
                self._ensure_open(name, definition=definition)
                previous = self._generations.get(name)
                self._generations[name] = candidate
                self._failed.pop(name, None)
                installed = True
                if previous is not None:
                    previous.lease.retired = True
                    self._retired.setdefault(name, set()).add(previous)
            if previous is not None and previous.lease.active == 0:
                await self._retire(name, previous)
            with self._state_lock:
                if pin:
                    self._pin(candidate)
            return candidate
        finally:
            if candidate is not None and not installed:
                with anyio.CancelScope(shield=True):
                    await self._worker.run_sync(_remove_generation, candidate)

    def _ensure_open(
        self,
        name: str,
        *,
        definition: DrawingSpec,
    ) -> None:
        if self._closed:
            raise DrawingLoadError(
                f"Drawing registry is closed while refreshing {name!r}.",
                backend=definition.backend,
            )

    async def _release(self, name: str, generation: _Generation) -> None:
        with self._state_lock:
            generation.lease.active -= 1
            idle = generation.lease.active == 0
            should_close = generation.lease.retired and idle
        if should_close:
            await self._retire(name, generation)
        if idle:
            generation.lease.drained.set()

    async def _retire(self, name: str, generation: _Generation) -> None:
        with self._state_lock:
            if generation.closed:
                return
            generation.closed = True
            self._retired.get(name, set()).discard(generation)
        with anyio.CancelScope(shield=True):
            await self._worker.run_sync(_remove_generation, generation)

    def _refresh_lock_for(self, name: str) -> anyio.Lock:
        with self._locks_guard:
            lock = self._refresh_locks.get(name)
            if lock is None:
                lock = self._refresh_locks[name] = anyio.Lock()
            return lock

    def _all_refresh_locks(self) -> list[anyio.Lock]:
        with self._locks_guard:
            return list(self._refresh_locks.values())


def _generation_namespace() -> str:
    return f"{_PRIVATE_ROOT}_gen_{uuid.uuid4().hex}"


__all__ = [
    "DrawingCallable",
    "DrawingLoadError",
    "DrawingNotFoundError",
    "DrawingRegistry",
    "DrawingSpec",
]
