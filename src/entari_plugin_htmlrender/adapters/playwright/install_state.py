from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
import json
import os
from pathlib import Path
import platform
import sys
from typing import TYPE_CHECKING, TypedDict

import playwright

from entari_plugin_htmlrender._logging import logger

from .config import BrowserEngine

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .config import PlaywrightConfig

_BROWSERS_PATH_VAR = "PLAYWRIGHT_BROWSERS_PATH"


class _BrowserEntry(TypedDict, total=False):
    """Playwright `browsers.json` 中单个浏览器条目的关心字段。"""

    name: str
    revision: str
    browserVersion: str
    revisionOverrides: dict[str, str]


class _BrowsersJson(TypedDict, total=False):
    """Playwright `browsers.json` 顶层结构的关心字段。"""

    browsers: list[_BrowserEntry]


_RuntimeSnapshot = dict[str, object]
_RuntimeSnapshotHistory = dict[str, _RuntimeSnapshot]

_BROWSER_NAMES_BY_ENGINE: dict[BrowserEngine, tuple[str, ...]] = {
    BrowserEngine.CHROMIUM: ("chromium", "chromium-headless-shell"),
    BrowserEngine.FIREFOX: ("firefox",),
    BrowserEngine.WEBKIT: ("webkit",),
}
_PLAYWRIGHT_RUNTIME_STATE_FILE = "playwright-runtime.json"
_MAX_RUNTIME_STATE_ENTRIES = 20


def _default_playwright_cache_path() -> Path:
    """Return a host-neutral cache path without importing a framework.

    Entari injects its ``local_data`` path into ``PlaywrightConfig`` at the
    plugin boundary.  This fallback keeps the provider usable by standalone
    library embeddings without installing an Entari import hook.
    """
    system = platform.system()
    if system == "Windows":
        root = Path(
            os.environ.get(
                "LOCALAPPDATA",
                Path.home() / "AppData" / "Local",
            )
        )
    elif system == "Darwin":
        root = Path.home() / "Library" / "Caches"
    else:
        root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return root / "entari-plugin-htmlrender" / "playwright"


def get_playwright_storage_path(config: PlaywrightConfig) -> Path:
    """获取 Playwright 浏览器存储路径。"""
    configured = config.storage_path
    if configured is not None:
        return Path(configured).expanduser()
    return _default_playwright_cache_path()


def _browser_directory_name(name: str, revision: str) -> str:
    """生成浏览器目录名称。"""
    return f"{name.replace('-', '_')}-{revision}"


def _playwright_browsers_json_path() -> Path:
    """获取 Playwright browsers.json 文件路径。"""
    return (
        Path(playwright.__file__).resolve().parent
        / "driver"
        / "package"
        / "browsers.json"
    )


def _load_playwright_browsers_json() -> _BrowsersJson:
    """加载 Playwright browsers.json 配置。"""
    with _playwright_browsers_json_path().open(encoding="utf-8") as fp:
        value = json.load(fp)
    if not isinstance(value, dict):
        return {}
    raw_browsers = value.get("browsers")
    if not isinstance(raw_browsers, list):
        return {}

    browsers: list[_BrowserEntry] = []
    for raw_entry in raw_browsers:
        if not isinstance(raw_entry, dict):
            continue
        entry: _BrowserEntry = {}
        for name in ("name", "revision", "browserVersion"):
            field_value = raw_entry.get(name)
            if isinstance(field_value, str):
                entry[name] = field_value
        raw_overrides = raw_entry.get("revisionOverrides")
        if isinstance(raw_overrides, dict):
            entry["revisionOverrides"] = {
                key: override
                for key, override in raw_overrides.items()
                if isinstance(key, str) and isinstance(override, str)
            }
        browsers.append(entry)
    return {"browsers": browsers}


def _browser_metadata_by_name(data: _BrowsersJson) -> dict[str, dict[str, str]]:
    """按浏览器名称索引元数据（revision 和 browserVersion）。"""
    browsers: list[_BrowserEntry] = data.get("browsers") or []

    metadata: dict[str, dict[str, str]] = {}
    for item in browsers:
        name = item.get("name")
        revision = item.get("revision")
        if not isinstance(name, str) or not isinstance(revision, str):
            continue
        browser_version = item.get("browserVersion")
        metadata[name] = {
            "revision": revision,
            "browser_version": browser_version
            if isinstance(browser_version, str)
            else "",
        }
    return metadata


def _expected_browser_directory_groups(
    engine: BrowserEngine,
    data: _BrowsersJson | None = None,
) -> tuple[tuple[str, ...], ...]:
    """获取指定引擎期望的浏览器目录名称分组。"""
    browser_data = _load_playwright_browsers_json() if data is None else data
    browsers: list[_BrowserEntry] = browser_data.get("browsers") or []

    expected_names = set(_BROWSER_NAMES_BY_ENGINE[engine])
    groups: list[tuple[str, ...]] = []
    for item in browsers:
        name = item.get("name")
        revision = item.get("revision")
        if not isinstance(name, str) or not isinstance(revision, str):
            continue
        if name not in expected_names:
            continue
        revisions = [revision]
        revision_overrides = item.get("revisionOverrides") or {}
        revisions.extend(revision_overrides.values())
        groups.append(
            tuple(
                dict.fromkeys(
                    _browser_directory_name(name, candidate_revision)
                    for candidate_revision in revisions
                )
            )
        )

    return tuple(groups)


def _playwright_package_version() -> str:
    """获取 playwright 包版本号。"""
    try:
        return pkg_version("playwright")
    except PackageNotFoundError:
        return "unknown"


def _runtime_state_path(config: PlaywrightConfig) -> Path:
    """获取运行时状态 JSON 文件路径。"""
    return get_playwright_storage_path(config).parent / _PLAYWRIGHT_RUNTIME_STATE_FILE


def _installed_browser_directories(
    base_path: Path, engine: BrowserEngine
) -> tuple[str, ...]:
    """获取指定路径下已安装的浏览器目录列表。"""
    names = tuple(name.replace("-", "_") for name in _BROWSER_NAMES_BY_ENGINE[engine])
    if not base_path.exists():
        return ()
    directories = [
        path.name
        for path in base_path.iterdir()
        if path.is_dir() and any(path.name.startswith(f"{name}-") for name in names)
    ]
    return tuple(sorted(directories))


def _browser_cache_snapshot(
    engine: BrowserEngine,
    expected_directory_groups: tuple[tuple[str, ...], ...],
    metadata: dict[str, dict[str, str]],
    *,
    storage_path: Path,
) -> dict[str, object]:
    """构建浏览器缓存状态快照。"""
    installed_directories = _installed_browser_directories(storage_path, engine)
    matched = tuple(
        next(
            (
                directory
                for directory in directory_group
                if directory in installed_directories
            ),
            "",
        )
        for directory_group in expected_directory_groups
    )
    available = bool(expected_directory_groups) and all(matched)

    return {
        "available": available,
        "expected_directory_groups": [
            list(group) for group in expected_directory_groups
        ],
        "browser_versions": {
            name: metadata.get(name, {}) for name in _BROWSER_NAMES_BY_ENGINE[engine]
        },
        "paths": [
            {
                "path": str(storage_path),
                "exists": storage_path.exists(),
                "available": available,
                "installed_directories": list(installed_directories),
                "matched_directories": [
                    directory for directory in matched if directory
                ],
            }
        ],
    }


def _venv_info() -> dict[str, str]:
    """获取当前虚拟环境信息。"""
    return {
        "prefix": sys.prefix,
        "executable": sys.executable,
    }


def build_playwright_runtime_snapshot(config: PlaywrightConfig) -> _RuntimeSnapshot:
    """构建当前 Playwright 运行时环境的完整快照。"""
    browser_data = _load_playwright_browsers_json()
    metadata = _browser_metadata_by_name(browser_data)
    return {
        "venv": _venv_info(),
        "playwright_version": _playwright_package_version(),
        "browsers_json": str(_playwright_browsers_json_path()),
        "engines": {
            engine.value: _browser_cache_snapshot(
                engine,
                _expected_browser_directory_groups(engine, browser_data),
                metadata,
                storage_path=get_playwright_storage_path(config),
            )
            for engine in BrowserEngine
        },
    }


def _load_runtime_state_history(config: PlaywrightConfig) -> _RuntimeSnapshotHistory:
    """从磁盘加载运行时状态历史记录。"""
    state_path = _runtime_state_path(config)
    if not state_path.exists():
        return {}
    try:
        with state_path.open(encoding="utf-8") as fp:
            value = json.load(fp)
    except Exception as e:
        logger.warning(f"Failed to read Playwright runtime state {state_path}: {e}")
        return {}
    if not isinstance(value, dict):
        return {}
    history: _RuntimeSnapshotHistory = {}
    for key, raw_snapshot in value.items():
        if not isinstance(key, str) or not isinstance(raw_snapshot, dict):
            continue
        history[key] = {
            field: field_value
            for field, field_value in raw_snapshot.items()
            if isinstance(field, str)
        }
    return history


def _latest_snapshot_from_history(
    history: _RuntimeSnapshotHistory,
) -> _RuntimeSnapshot | None:
    """从历史记录中获取最新的快照。"""
    if not history:
        return None
    return history[max(history.keys())]


def _engine_states_from(
    snapshot: _RuntimeSnapshot | None,
) -> dict[str, dict[str, object]]:
    """从快照中提取按引擎索引的状态映射。"""
    if not snapshot:
        return {}
    engines = snapshot.get("engines")
    if not isinstance(engines, dict):
        return {}
    states: dict[str, dict[str, object]] = {}
    for name, raw_state in engines.items():
        if not isinstance(name, str) or not isinstance(raw_state, dict):
            continue
        states[name] = {
            field: field_value
            for field, field_value in raw_state.items()
            if isinstance(field, str)
        }
    return states


def _warn_runtime_snapshot_mismatch(
    previous: _RuntimeSnapshot | None,
    current: _RuntimeSnapshot,
    *,
    configured_engine: BrowserEngine,
) -> None:
    """比较前后运行时快照并记录版本变更警告。"""
    current_version = current.get("playwright_version")
    previous_version = previous.get("playwright_version") if previous else None
    if previous_version and previous_version != current_version:
        logger.warning(
            "Playwright package version changed since last htmlrender startup: "
            f"{previous_version} -> {current_version}. Browser cache compatibility "
            "will be rechecked."
        )

    previous_engines = _engine_states_from(previous)
    current_engines = _engine_states_from(current)

    for engine in BrowserEngine:
        engine_state = current_engines.get(engine.value, {})
        if engine is configured_engine and not engine_state.get("available", False):
            logger.warning(
                "Playwright browser cache does not match current package metadata for "
                f"`{engine.value}`. Expected directory groups: "
                f"{engine_state.get('expected_directory_groups', [])}; cache paths: "
                f"{engine_state.get('paths', [])}."
            )

        previous_state = previous_engines.get(engine.value, {})
        previous_versions = previous_state.get("browser_versions")
        current_versions = engine_state.get("browser_versions")
        if previous_versions != current_versions:
            logger.warning(
                f"Playwright browser metadata for `{engine.value}` changed since last "
                f"htmlrender startup: {previous_versions} -> {current_versions}."
            )


def record_playwright_runtime_state(config: PlaywrightConfig) -> None:
    """记录当前 Playwright 运行时状态到 JSON 文件。"""
    current = build_playwright_runtime_snapshot(config)
    history = _load_runtime_state_history(config)
    previous = _latest_snapshot_from_history(history)
    _warn_runtime_snapshot_mismatch(
        previous,
        current,
        configured_engine=config.engine,
    )

    timestamp = datetime.now(tz=timezone.utc).isoformat()
    history[timestamp] = current

    if len(history) > _MAX_RUNTIME_STATE_ENTRIES:
        for key in sorted(history)[: len(history) - _MAX_RUNTIME_STATE_ENTRIES]:
            del history[key]

    state_path = _runtime_state_path(config)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("w", encoding="utf-8") as fp:
        json.dump(history, fp, ensure_ascii=False, indent=2, sort_keys=True)
        fp.write("\n")


def has_installed_browser(
    engine: BrowserEngine,
    *,
    storage_path: Path,
) -> bool:
    """检查指定引擎的 Playwright 浏览器是否已安装。

    Args:
        engine: 浏览器引擎类型。

    Returns:
        浏览器已安装返回 True，否则返回 False。
    """
    expected_directory_groups = _expected_browser_directory_groups(engine)
    if not expected_directory_groups:
        logger.warning(
            f"Could not determine expected Playwright browser revision for `{engine.value}`."
        )
        return False

    if not storage_path.exists():
        return False
    return all(
        any((storage_path / directory).is_dir() for directory in directory_group)
        for directory_group in expected_directory_groups
    )


@contextmanager
def browsers_path_scope(config: PlaywrightConfig) -> Iterator[None]:
    """Temporarily point ``PLAYWRIGHT_BROWSERS_PATH`` at the configured store.

    The Python Playwright driver has no per-start env argument, so the value
    is set only for the duration of ``async_playwright().start()`` and then
    restored to its exact prior state (value or absence). ``executable_path``
    mode never touches the variable. The caller serializes concurrent driver
    spawns so overlapping scopes cannot corrupt each other's snapshot.
    """
    if config.executable_path:
        yield
        return

    had_original = _BROWSERS_PATH_VAR in os.environ
    original_value = os.environ.get(_BROWSERS_PATH_VAR)
    storage_path = os.path.abspath(str(get_playwright_storage_path(config)))
    os.environ[_BROWSERS_PATH_VAR] = storage_path
    logger.debug(f'Setting {_BROWSERS_PATH_VAR}="{storage_path}" for driver start')
    try:
        yield
    finally:
        if had_original and original_value is not None:
            os.environ[_BROWSERS_PATH_VAR] = original_value
        else:
            os.environ.pop(_BROWSERS_PATH_VAR, None)
