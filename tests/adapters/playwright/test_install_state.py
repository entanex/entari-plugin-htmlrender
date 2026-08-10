"""Playwright browser-store state and runtime snapshot tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from entari_plugin_htmlrender.adapters.playwright import install_state
from entari_plugin_htmlrender.adapters.playwright.config import (
    BrowserEngine,
    PlaywrightConfig,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def test_configured_runtime_storage_path() -> None:
    configured = PlaywrightConfig.model_validate({"storage_path": "~/pw-cache"})
    storage = install_state.get_playwright_storage_path(configured)
    assert isinstance(storage, Path)
    assert storage == Path("~/pw-cache").expanduser()


def test_default_storage_and_runtime_state_paths_are_host_neutral(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    mocker.patch.object(install_state.platform, "system", return_value="Darwin")
    mocker.patch.object(install_state.Path, "home", return_value=tmp_path)
    config = PlaywrightConfig()

    storage_path = install_state.get_playwright_storage_path(config)

    assert storage_path == (
        tmp_path / "Library" / "Caches" / "entari-plugin-htmlrender" / "playwright"
    )
    assert install_state._runtime_state_path(config) == (
        storage_path.parent / "playwright-runtime.json"
    )


def test_default_storage_path_obeys_host_cache_conventions(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    system = mocker.patch.object(install_state.platform, "system")
    mocker.patch.object(install_state.Path, "home", return_value=tmp_path)
    mocker.patch.dict(
        install_state.os.environ,
        {
            "LOCALAPPDATA": str(tmp_path / "windows-cache"),
            "XDG_CACHE_HOME": str(tmp_path / "xdg-cache"),
        },
        clear=True,
    )

    system.return_value = "Windows"
    assert install_state._default_playwright_cache_path() == (
        tmp_path / "windows-cache" / "entari-plugin-htmlrender" / "playwright"
    )

    system.return_value = "Linux"
    assert install_state._default_playwright_cache_path() == (
        tmp_path / "xdg-cache" / "entari-plugin-htmlrender" / "playwright"
    )


def test_playwright_browsers_metadata_path_targets_installed_driver() -> None:
    expected = (
        Path(install_state.playwright.__file__).resolve().parent
        / "driver"
        / "package"
        / "browsers.json"
    )

    assert install_state._playwright_browsers_json_path() == expected


@pytest.mark.parametrize("payload", [[], {}, {"browsers": {}}])
def test_browsers_metadata_loader_rejects_invalid_document_shapes(
    mocker: MockerFixture,
    tmp_path: Path,
    payload: object,
) -> None:
    browsers_json = tmp_path / "browsers.json"
    browsers_json.write_text(json.dumps(payload), encoding="utf-8")
    mocker.patch.object(
        install_state,
        "_playwright_browsers_json_path",
        return_value=browsers_json,
    )

    assert install_state._load_playwright_browsers_json() == {}


def test_browsers_metadata_loader_filters_invalid_entries_and_fields(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    browsers_json = tmp_path / "browsers.json"
    browsers_json.write_text(
        json.dumps(
            {
                "browsers": [
                    None,
                    {},
                    {"name": 1, "revision": "ignored"},
                    {"name": "missing-revision"},
                    {
                        "name": "chromium",
                        "revision": "123",
                        "browserVersion": 123,
                        "revisionOverrides": {
                            "linux-arm64": "456",
                            "invalid": 789,
                        },
                    },
                    {
                        "name": "firefox",
                        "revision": "789",
                        "browserVersion": "128.0",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    mocker.patch.object(
        install_state,
        "_playwright_browsers_json_path",
        return_value=browsers_json,
    )

    loaded = install_state._load_playwright_browsers_json()

    assert install_state._browser_metadata_by_name(loaded) == {
        "chromium": {"revision": "123", "browser_version": ""},
        "firefox": {"revision": "789", "browser_version": "128.0"},
    }
    assert install_state._expected_browser_directory_groups(
        BrowserEngine.CHROMIUM,
        loaded,
    ) == (("chromium-123", "chromium-456"),)


def test_missing_playwright_distribution_has_explicit_unknown_version(
    mocker: MockerFixture,
) -> None:
    mocker.patch.object(
        install_state,
        "pkg_version",
        side_effect=install_state.PackageNotFoundError,
    )

    assert install_state._playwright_package_version() == "unknown"


def test_browser_cache_snapshot_reports_exact_installed_revision_groups(
    tmp_path: Path,
) -> None:
    missing_storage = tmp_path / "missing"
    assert (
        install_state._installed_browser_directories(
            missing_storage,
            BrowserEngine.CHROMIUM,
        )
        == ()
    )

    storage = tmp_path / "storage"
    storage.mkdir()
    (storage / "chromium-456").mkdir()
    (storage / "chromium-ignored.txt").write_text("not a directory", encoding="utf-8")
    (storage / "firefox-789").mkdir()
    groups = (("chromium-123", "chromium-456"), ("chromium_headless_shell-456",))
    metadata = {
        "chromium": {"revision": "123", "browser_version": "128.0"},
    }

    incomplete = install_state._browser_cache_snapshot(
        BrowserEngine.CHROMIUM,
        groups,
        metadata,
        storage_path=storage,
    )
    assert incomplete["available"] is False
    assert incomplete["paths"] == [
        {
            "path": str(storage),
            "exists": True,
            "available": False,
            "installed_directories": ["chromium-456"],
            "matched_directories": ["chromium-456"],
        }
    ]

    (storage / "chromium_headless_shell-456").mkdir()
    complete = install_state._browser_cache_snapshot(
        BrowserEngine.CHROMIUM,
        groups,
        metadata,
        storage_path=storage,
    )
    assert complete["available"] is True
    assert complete["expected_directory_groups"] == [list(group) for group in groups]
    assert complete["browser_versions"] == {
        "chromium": metadata["chromium"],
        "chromium-headless-shell": {},
    }


def test_runtime_snapshot_captures_process_and_all_engine_states(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    storage = tmp_path / "storage"
    browser_data: install_state._BrowsersJson = {
        "browsers": [
            {"name": "chromium", "revision": "1"},
            {"name": "chromium-headless-shell", "revision": "1"},
            {"name": "firefox", "revision": "2"},
            {"name": "webkit", "revision": "3"},
        ]
    }
    mocker.patch.object(
        install_state,
        "_load_playwright_browsers_json",
        return_value=browser_data,
    )
    mocker.patch.object(
        install_state,
        "_playwright_package_version",
        return_value="1.58.0",
    )
    browsers_json = tmp_path / "browsers.json"
    mocker.patch.object(
        install_state,
        "_playwright_browsers_json_path",
        return_value=browsers_json,
    )

    snapshot = install_state.build_playwright_runtime_snapshot(
        PlaywrightConfig(storage_path=storage)
    )

    assert snapshot["venv"] == {
        "prefix": install_state.sys.prefix,
        "executable": install_state.sys.executable,
    }
    assert snapshot["playwright_version"] == "1.58.0"
    assert snapshot["browsers_json"] == str(browsers_json)
    engines = snapshot["engines"]
    assert isinstance(engines, dict)
    assert set(engines) == {engine.value for engine in BrowserEngine}


def test_runtime_state_history_recovers_from_missing_and_corrupt_files(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "playwright-runtime.json"
    config = PlaywrightConfig(storage_path=tmp_path / "storage")
    mocker.patch.object(
        install_state,
        "_runtime_state_path",
        return_value=state_path,
    )

    assert install_state._load_runtime_state_history(config) == {}

    state_path.write_text("{", encoding="utf-8")
    warning = mocker.patch.object(install_state.logger, "warning")
    assert install_state._load_runtime_state_history(config) == {}
    assert "Failed to read Playwright runtime state" in warning.call_args.args[0]

    state_path.write_text("[]", encoding="utf-8")
    assert install_state._load_runtime_state_history(config) == {}


def test_runtime_state_history_filters_non_mapping_entries_and_fields(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "playwright-runtime.json"
    state_path.write_text("{}", encoding="utf-8")
    config = PlaywrightConfig(storage_path=tmp_path / "storage")
    mocker.patch.object(
        install_state,
        "_runtime_state_path",
        return_value=state_path,
    )
    mocker.patch.object(
        install_state.json,
        "load",
        return_value={
            1: {"ignored": True},
            "not-a-snapshot": [],
            "valid": {1: "ignored", "playwright_version": "1.58.0"},
        },
    )

    assert install_state._load_runtime_state_history(config) == {
        "valid": {"playwright_version": "1.58.0"}
    }


def test_runtime_snapshot_extractors_reject_invalid_shapes() -> None:
    assert install_state._latest_snapshot_from_history({}) is None
    assert install_state._engine_states_from(None) == {}
    assert install_state._engine_states_from({"engines": []}) == {}
    assert install_state._engine_states_from(
        {
            "engines": {
                1: {"available": True},
                "invalid": [],
                "chromium": {1: "ignored", "available": True},
            }
        }
    ) == {"chromium": {"available": True}}


def test_has_installed_browser_uses_managed_storage(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()
    (storage / "chromium-1234").mkdir()
    (storage / "chromium_headless_shell-1234").mkdir()
    (storage / "firefox-999").mkdir()
    mocker.patch.object(
        install_state,
        "_expected_browser_directory_groups",
        side_effect=lambda engine: {
            BrowserEngine.CHROMIUM: (
                ("chromium-1234",),
                ("chromium_headless_shell-1234",),
            ),
            BrowserEngine.FIREFOX: (("firefox-999",),),
            BrowserEngine.WEBKIT: (("webkit-777",),),
        }[engine],
    )

    assert (
        install_state.has_installed_browser(
            BrowserEngine.CHROMIUM,
            storage_path=storage,
        )
        is True
    )
    assert (
        install_state.has_installed_browser(BrowserEngine.FIREFOX, storage_path=storage)
        is True
    )
    assert (
        install_state.has_installed_browser(BrowserEngine.WEBKIT, storage_path=storage)
        is False
    )


def test_has_installed_browser_rejects_stale_revision(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()
    (storage / "chromium-older").mkdir()
    (storage / "chromium_headless_shell-older").mkdir()

    mocker.patch.object(
        install_state,
        "_expected_browser_directory_groups",
        return_value=(("chromium-new",), ("chromium_headless_shell-new",)),
    )

    assert (
        install_state.has_installed_browser(
            BrowserEngine.CHROMIUM,
            storage_path=storage,
        )
        is False
    )


def test_has_installed_browser_handles_unknown_metadata_and_missing_store(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    expected_groups = mocker.patch.object(
        install_state,
        "_expected_browser_directory_groups",
        return_value=(),
    )
    warning = mocker.patch.object(install_state.logger, "warning")

    assert (
        install_state.has_installed_browser(
            BrowserEngine.WEBKIT,
            storage_path=tmp_path / "missing",
        )
        is False
    )
    warning.assert_called_once_with(
        "Could not determine expected Playwright browser revision for `webkit`."
    )

    expected_groups.return_value = (("webkit-123",),)
    assert (
        install_state.has_installed_browser(
            BrowserEngine.WEBKIT,
            storage_path=tmp_path / "missing",
        )
        is False
    )


def test_browsers_path_scope_is_a_noop_for_explicit_executable(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    mocker.patch.dict(
        install_state.os.environ,
        {"PLAYWRIGHT_BROWSERS_PATH": "original"},
        clear=True,
    )
    config = PlaywrightConfig(executable_path=tmp_path / "chromium")

    with install_state.browsers_path_scope(config):
        assert install_state.os.environ["PLAYWRIGHT_BROWSERS_PATH"] == "original"

    assert install_state.os.environ["PLAYWRIGHT_BROWSERS_PATH"] == "original"


def test_browsers_path_scope_restores_absent_environment_after_failure(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    mocker.patch.dict(install_state.os.environ, {}, clear=True)
    storage = tmp_path / "relative" / "browser-store"

    with (
        pytest.raises(RuntimeError, match="driver failed"),
        install_state.browsers_path_scope(PlaywrightConfig(storage_path=storage)),
    ):
        assert install_state.os.environ["PLAYWRIGHT_BROWSERS_PATH"] == str(
            storage.absolute()
        )
        raise RuntimeError("driver failed")

    assert "PLAYWRIGHT_BROWSERS_PATH" not in install_state.os.environ


def test_browsers_path_scope_restores_original_environment(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    mocker.patch.dict(
        install_state.os.environ,
        {"PLAYWRIGHT_BROWSERS_PATH": "original"},
        clear=True,
    )

    with install_state.browsers_path_scope(
        PlaywrightConfig(storage_path=tmp_path / "browser-store")
    ):
        assert install_state.os.environ["PLAYWRIGHT_BROWSERS_PATH"] != "original"

    assert install_state.os.environ["PLAYWRIGHT_BROWSERS_PATH"] == "original"


def test_expected_browser_directory_groups_reads_current_playwright_metadata(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    browsers_json = tmp_path / "browsers.json"
    browsers_json.write_text(
        """
        {
          "browsers": [
            {"name": "chromium", "revision": "111"},
            {"name": "chromium-headless-shell", "revision": "111"},
            {"name": "webkit", "revision": "222", "revisionOverrides": {"mac": "333"}}
          ]
        }
        """,
        encoding="utf-8",
    )
    mocker.patch.object(
        install_state,
        "_playwright_browsers_json_path",
        return_value=browsers_json,
    )

    assert install_state._expected_browser_directory_groups(BrowserEngine.CHROMIUM) == (
        ("chromium-111",),
        ("chromium_headless_shell-111",),
    )
    assert install_state._expected_browser_directory_groups(BrowserEngine.WEBKIT) == (
        ("webkit-222", "webkit-333"),
    )


def test_record_playwright_runtime_state_warns_on_version_change(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "playwright-runtime.json"
    state_path.write_text(
        json.dumps(
            {
                "2026-01-01T00:00:00+00:00": {
                    "venv": {
                        "prefix": "/old/venv",
                        "executable": "/old/venv/bin/python",
                    },
                    "playwright_version": "1.0.0",
                    "engines": {
                        "chromium": {
                            "browser_versions": {
                                "chromium": {
                                    "revision": "old",
                                    "browser_version": "old",
                                }
                            }
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    mocker.patch.object(
        install_state,
        "_runtime_state_path",
        return_value=state_path,
    )
    mocker.patch.object(
        install_state,
        "build_playwright_runtime_snapshot",
        return_value={
            "venv": {"prefix": "/new/venv", "executable": "/new/venv/bin/python"},
            "playwright_version": "2.0.0",
            "browsers_json": str(tmp_path / "browsers.json"),
            "engines": {
                "chromium": {
                    "available": False,
                    "expected_directory_groups": [["chromium-new"]],
                    "browser_versions": {
                        "chromium": {
                            "revision": "new",
                            "browser_version": "new",
                        }
                    },
                    "paths": [],
                },
                "firefox": {"available": True, "browser_versions": {}, "paths": []},
                "webkit": {"available": True, "browser_versions": {}, "paths": []},
            },
        },
    )
    warning = mocker.patch.object(install_state.logger, "warning")

    install_state.record_playwright_runtime_state(PlaywrightConfig())

    warning.assert_any_call(
        "Playwright package version changed since last htmlrender startup: "
        "1.0.0 -> 2.0.0. Browser cache compatibility will be rechecked."
    )
    written = json.loads(state_path.read_text(encoding="utf-8"))
    assert len(written) == 2
    latest_key = max(written.keys())
    assert written[latest_key]["playwright_version"] == "2.0.0"
    assert "2026-01-01T00:00:00+00:00" in written


def test_record_playwright_runtime_state_evicts_oldest_entries(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    history: dict[str, dict[str, object]] = {
        f"2026-01-{i:02d}T00:00:00+00:00": {
            "venv": {"prefix": f"/venv{i}", "executable": f"/venv{i}/bin/python"},
            "playwright_version": "1.0.0",
            "engines": {},
        }
        for i in range(1, 21)
    }
    state_path = tmp_path / "playwright-runtime.json"
    state_path.write_text(json.dumps(history), encoding="utf-8")

    mocker.patch.object(
        install_state,
        "_runtime_state_path",
        return_value=state_path,
    )
    mocker.patch.object(
        install_state,
        "build_playwright_runtime_snapshot",
        return_value={
            "venv": {"prefix": "/new", "executable": "/new/bin/python"},
            "playwright_version": "1.0.0",
            "engines": {},
        },
    )
    mocker.patch.object(install_state.logger, "warning")

    install_state.record_playwright_runtime_state(PlaywrightConfig())

    written = json.loads(state_path.read_text(encoding="utf-8"))
    assert len(written) == 20
    assert "2026-01-01T00:00:00+00:00" not in written
