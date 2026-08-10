from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import anyio
from anyio import wait_all_tasks_blocked
import pytest

from entari_plugin_htmlrender.adapters.resources import (
    AnyioWorkerExecutor,
    ConfiguredLocalAccessPolicy,
    FilehostAssetPublisher,
    HostedAssetCapacityError,
    HostedAssetHttpServer,
    HostedAssetStore,
)
from entari_plugin_htmlrender.adapters.resources import publisher as publisher_module
from entari_plugin_htmlrender.errors import InvalidRenderInputError
from entari_plugin_htmlrender.rendering.errors import ProviderLifecycleError
from entari_plugin_htmlrender.resources.config import AssetPublisherSettings
from entari_plugin_htmlrender.resources.errors import (
    ResourcePublishError,
    ResourceTooLargeError,
)
from entari_plugin_htmlrender.resources.models import (
    InlineResource,
    PublicationLeaseId,
)
from entari_plugin_htmlrender.resources.observation import NoopCacheObserver

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

    from tests.resources.conftest import (
        FailingCacheObserver,
        RecordingCacheObserver,
    )


def _publisher(
    *,
    ttl: float = 300.0,
    header_value: str = "test-header-value",
    observer: RecordingCacheObserver | FailingCacheObserver | None = None,
    max_resource_bytes: int = 64 * 1024 * 1024,
    store: HostedAssetStore | None = None,
    public_base_url: str | None = None,
) -> FilehostAssetPublisher:
    return FilehostAssetPublisher(
        settings=AssetPublisherSettings(
            cache_ttl_seconds=ttl,
            request_header_name="X-Test-Filehost",
            request_header_value=header_value,
            max_resource_bytes=max_resource_bytes,
            public_base_url=public_base_url,
        ),
        observer=observer or NoopCacheObserver(),
        worker=AnyioWorkerExecutor(),
        local_access=ConfiguredLocalAccessPolicy(
            allowed_roots=(),
            allow_any=True,
        ),
        store=store or _unused_store(),
    )


class _UnusedHostedAssetStore:
    def open_namespace(self, **kwargs: object) -> None:
        del kwargs
        raise AssertionError("This unit test unexpectedly used the hosted store")


def _unused_store() -> HostedAssetStore:
    return cast("HostedAssetStore", _UnusedHostedAssetStore())


def _inline(data: bytes) -> InlineResource:
    return InlineResource(data)


@pytest.mark.anyio
async def test_content_addressed_cache_normalizes_suffix_and_reports_events(
    mocker: MockerFixture,
    recording_observer: RecordingCacheObserver,
) -> None:
    publisher = _publisher(observer=recording_observer)
    upload = mocker.patch.object(
        publisher,
        "_upload",
        new=mocker.AsyncMock(return_value="https://assets.example/value.css"),
    )

    assert (await publisher.publish(_inline(b"value"), suffix="css")).url == (
        "https://assets.example/value.css"
    )
    assert (await publisher.publish(_inline(b"value"), suffix=".CSS")).url == (
        "https://assets.example/value.css"
    )

    upload.assert_awaited_once_with(
        (sha256(b"value").hexdigest(), ".css"), b"value", set()
    )
    assert recording_observer.calls[-2:] == [
        ("filehost", {"miss": 1, "load": 1}, 1, None),
        ("filehost", {"hit": 1}, 1, None),
    ]


@pytest.mark.anyio
async def test_same_content_with_different_suffixes_has_distinct_assets(
    mocker: MockerFixture,
) -> None:
    publisher = _publisher()

    async def upload(
        key: tuple[str, str], data: bytes, lease_ids: set[PublicationLeaseId]
    ) -> str:
        del data, lease_ids
        return f"https://assets.example/value{key[1]}"

    upload_mock = mocker.patch.object(publisher, "_upload", side_effect=upload)

    assert (await publisher.publish(_inline(b"value"), suffix="css")).url == (
        "https://assets.example/value.css"
    )
    assert (await publisher.publish(_inline(b"value"), suffix="woff2")).url == (
        "https://assets.example/value.woff2"
    )
    assert upload_mock.await_count == 2


@pytest.mark.anyio
async def test_publisher_enforces_resource_size_limit() -> None:
    publisher = _publisher(max_resource_bytes=4)

    with pytest.raises(ResourceTooLargeError, match="4-byte publish limit"):
        await publisher.publish(_inline(b"12345"))


@pytest.mark.anyio
async def test_publisher_rejects_unsafe_suffix_defensively() -> None:
    publisher = _publisher()

    with pytest.raises(InvalidRenderInputError) as captured:
        await publisher.publish(_inline(b"value"), suffix="../../escape")

    assert captured.value.operation == "publish"
    assert captured.value.field == "suffix"


@pytest.mark.anyio
async def test_concurrent_publish_is_singleflight(mocker: MockerFixture) -> None:
    publisher = _publisher()
    upload_started = anyio.Event()
    release_upload = anyio.Event()
    calls = 0

    async def upload(
        key: tuple[str, str], data: bytes, lease_ids: set[PublicationLeaseId]
    ) -> str:
        nonlocal calls
        del key, data, lease_ids
        calls += 1
        upload_started.set()
        await release_upload.wait()
        return "https://assets.example/shared"

    mocker.patch.object(publisher, "_upload", side_effect=upload)
    results: list[str] = []

    async def publish() -> None:
        results.append((await publisher.publish(_inline(b"shared"))).url)

    async with anyio.create_task_group() as group:
        group.start_soon(publish)
        await upload_started.wait()
        for _ in range(12):
            group.start_soon(publish)
        await wait_all_tasks_blocked()
        release_upload.set()

    assert calls == 1
    assert results == ["https://assets.example/shared"] * 13


@pytest.mark.anyio
async def test_singleflight_broadcasts_errors_and_allows_retry(
    mocker: MockerFixture,
) -> None:
    publisher = _publisher()
    upload_started = anyio.Event()
    release_upload = anyio.Event()
    failing = True
    calls = 0

    async def upload(
        key: tuple[str, str], data: bytes, lease_ids: set[PublicationLeaseId]
    ) -> str:
        nonlocal calls
        del key, data, lease_ids
        calls += 1
        upload_started.set()
        await release_upload.wait()
        if failing:
            raise RuntimeError("upload failed")
        return "https://assets.example/retry"

    mocker.patch.object(publisher, "_upload", side_effect=upload)
    errors: list[str] = []

    async def publish() -> None:
        with pytest.raises(
            ResourcePublishError,
            match=r"Could not publish resource.*RuntimeError: upload failed",
        ) as captured:
            await publisher.publish(_inline(b"shared"))
        errors.append(str(captured.value))

    async with anyio.create_task_group() as group:
        group.start_soon(publish)
        await upload_started.wait()
        for _ in range(4):
            group.start_soon(publish)
        await wait_all_tasks_blocked()
        release_upload.set()

    assert (
        errors
        == ["Could not publish resource. Caused by RuntimeError: upload failed"] * 5
    )
    assert calls == 1

    failing = False
    assert (
        await publisher.publish(_inline(b"shared"))
    ).url == "https://assets.example/retry"
    assert calls == 2


@pytest.mark.anyio
async def test_every_singleflight_waiter_attaches_its_lease(
    mocker: MockerFixture,
) -> None:
    publisher = _publisher(ttl=0)
    first_lease = publisher.create_lease()
    second_lease = publisher.create_lease()
    upload_started = anyio.Event()
    release_upload = anyio.Event()
    calls = 0

    async def upload(
        key: tuple[str, str], data: bytes, lease_ids: set[PublicationLeaseId]
    ) -> str:
        nonlocal calls
        del key, data, lease_ids
        calls += 1
        upload_started.set()
        await release_upload.wait()
        return f"https://assets.example/{calls}"

    mocker.patch.object(publisher, "_upload", side_effect=upload)
    results: list[str] = []

    async def publish(lease_id: PublicationLeaseId) -> None:
        results.append(
            (await publisher.publish(_inline(b"shared"), lease_id=lease_id)).url
        )

    async with anyio.create_task_group() as group:
        group.start_soon(publish, first_lease)
        await upload_started.wait()
        group.start_soon(publish, second_lease)
        await wait_all_tasks_blocked()
        release_upload.set()

    assert results == ["https://assets.example/1"] * 2
    await publisher.release(first_lease)
    assert (
        await publisher.publish(_inline(b"shared"))
    ).url == "https://assets.example/1"
    assert calls == 1

    await publisher.release(second_lease)
    assert (
        await publisher.publish(_inline(b"shared"))
    ).url == "https://assets.example/2"
    assert calls == 2


@pytest.mark.anyio
async def test_release_detaches_lease_from_inflight_publish(
    mocker: MockerFixture,
) -> None:
    publisher = _publisher(ttl=0)
    lease = publisher.create_lease()
    upload_started = anyio.Event()
    release_upload = anyio.Event()
    calls = 0

    async def upload(
        key: tuple[str, str], data: bytes, lease_ids: set[PublicationLeaseId]
    ) -> str:
        nonlocal calls
        del key, data, lease_ids
        calls += 1
        upload_started.set()
        await release_upload.wait()
        return f"https://assets.example/{calls}"

    mocker.patch.object(publisher, "_upload", side_effect=upload)

    async def publish() -> None:
        await publisher.publish(_inline(b"shared"), lease_id=lease)

    async with anyio.create_task_group() as group:
        group.start_soon(publish)
        await upload_started.wait()
        await publisher.release(lease)
        release_upload.set()

    assert (
        await publisher.publish(_inline(b"shared"))
    ).url == "https://assets.example/2"
    assert calls == 2


@pytest.mark.anyio
async def test_clear_does_not_admit_an_older_inflight_mapping(
    mocker: MockerFixture,
) -> None:
    publisher = _publisher()
    upload_started = anyio.Event()
    release_upload = anyio.Event()
    calls = 0

    async def upload(
        key: tuple[str, str], data: bytes, lease_ids: set[PublicationLeaseId]
    ) -> str:
        nonlocal calls
        del key, data, lease_ids
        calls += 1
        if calls == 1:
            upload_started.set()
            await release_upload.wait()
        return f"https://assets.example/{calls}"

    mocker.patch.object(publisher, "_upload", side_effect=upload)

    async with anyio.create_task_group() as group:
        group.start_soon(publisher.publish, _inline(b"shared"))
        await upload_started.wait()
        await publisher.clear()
        release_upload.set()

    assert (
        await publisher.publish(_inline(b"shared"))
    ).url == "https://assets.example/2"
    assert calls == 2


@pytest.mark.anyio
async def test_aclose_terminates_only_the_target_instance(
    mocker: MockerFixture,
) -> None:
    first = _publisher()
    second = _publisher()
    first_upload = mocker.patch.object(
        first,
        "_upload",
        new=mocker.AsyncMock(
            side_effect=["https://first.example/1", "https://first.example/2"]
        ),
    )
    second_upload = mocker.patch.object(
        second,
        "_upload",
        new=mocker.AsyncMock(return_value="https://second.example/1"),
    )

    assert (await first.publish(_inline(b"value"))).url == "https://first.example/1"
    assert (await second.publish(_inline(b"value"))).url == ("https://second.example/1")
    await first.aclose()
    with pytest.raises(ResourcePublishError, match="closed"):
        await first.publish(_inline(b"value"))
    assert (await second.publish(_inline(b"value"))).url == ("https://second.example/1")

    assert first_upload.await_count == 1
    assert second_upload.await_count == 1


@pytest.mark.anyio
async def test_aclose_drains_an_inflight_publish_before_terminating(
    mocker: MockerFixture,
) -> None:
    publisher = _publisher()
    upload_started = anyio.Event()
    release_upload = anyio.Event()
    close_finished = anyio.Event()
    result: list[str] = []

    async def upload(
        key: tuple[str, str], data: bytes, lease_ids: set[PublicationLeaseId]
    ) -> str:
        del key, data, lease_ids
        upload_started.set()
        await release_upload.wait()
        return "https://assets.example/drained"

    mocker.patch.object(publisher, "_upload", side_effect=upload)

    async def publish() -> None:
        result.append((await publisher.publish(_inline(b"value"))).url)

    async def close() -> None:
        await publisher.aclose()
        close_finished.set()

    async with anyio.create_task_group() as group:
        group.start_soon(publish)
        await upload_started.wait()
        group.start_soon(close)
        await wait_all_tasks_blocked()
        assert not close_finished.is_set()
        release_upload.set()

    assert result == ["https://assets.example/drained"]
    assert close_finished.is_set()
    with pytest.raises(ResourcePublishError, match="closed"):
        await publisher.publish(_inline(b"value"))


@pytest.mark.anyio
async def test_publisher_survives_failing_observer(
    mocker: MockerFixture,
    failing_observer: FailingCacheObserver,
) -> None:
    publisher = _publisher(observer=failing_observer)
    mocker.patch.object(
        publisher,
        "_upload",
        new=mocker.AsyncMock(return_value="https://assets.example/value"),
    )

    assert (
        await publisher.publish(_inline(b"value"))
    ).url == "https://assets.example/value"
    assert (
        await publisher.publish(_inline(b"value"))
    ).url == "https://assets.example/value"


@pytest.mark.anyio
async def test_published_headers_and_leases_are_instance_owned(
    mocker: MockerFixture,
) -> None:
    first = _publisher(header_value="first-token")
    second = _publisher(header_value="second-token")
    mocker.patch.object(
        first, "_upload", new=mocker.AsyncMock(return_value="https://a/1")
    )
    mocker.patch.object(
        second, "_upload", new=mocker.AsyncMock(return_value="https://a/2")
    )

    first_published = await first.publish(_inline(b"value"))
    second_published = await second.publish(_inline(b"value"))
    assert dict(first_published.request_headers) == {"X-Test-Filehost": "first-token"}
    assert dict(second_published.request_headers) == {"X-Test-Filehost": "second-token"}
    assert first.create_lease() != first.create_lease()


@pytest.mark.anyio
async def test_request_header_can_be_derived_from_injected_settings(
    mocker: MockerFixture,
) -> None:
    mocker.patch.object(
        publisher_module,
        "import_module",
        return_value=SimpleNamespace(id=lambda: "device-id"),
    )
    settings = AssetPublisherSettings(
        request_header_name="X-Custom-Filehost",
        request_header_value=None,
        request_header_salt="custom-salt",
    )
    publisher = FilehostAssetPublisher(
        settings=settings,
        observer=NoopCacheObserver(),
        worker=AnyioWorkerExecutor(),
        local_access=ConfiguredLocalAccessPolicy(
            allowed_roots=(),
            allow_any=True,
        ),
        store=_unused_store(),
    )
    mocker.patch.object(
        publisher, "_upload", new=mocker.AsyncMock(return_value="https://a/x")
    )

    published = await publisher.publish(_inline(b"value"))
    assert dict(published.request_headers) == {
        "X-Custom-Filehost": sha256(b"custom-salt:device-id").hexdigest()
    }


@pytest.mark.anyio
async def test_startup_prewarms_only_configured_asset_extensions(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    root = tmp_path / "assets"
    root.mkdir()
    (root / "first.css").write_bytes(b"first")
    (root / "second.CSS").write_bytes(b"second")
    (root / "template.html").write_bytes(b"template")
    settings = AssetPublisherSettings(
        request_header_value="prewarm-header",
        prewarm_enabled=True,
        prewarm_max_files=8,
        prewarm_paths=(root,),
        prewarm_extensions=("css",),
    )
    publisher = FilehostAssetPublisher(
        settings=settings,
        observer=NoopCacheObserver(),
        worker=AnyioWorkerExecutor(),
        local_access=ConfiguredLocalAccessPolicy(
            allowed_roots=(root,),
            allow_any=False,
        ),
        store=_unused_store(),
    )
    upload = mocker.patch.object(
        publisher,
        "_upload",
        new=mocker.AsyncMock(return_value="https://assets.example/prewarmed"),
    )
    # startup() binds the hosted-store namespace; these tests exercise the
    # prewarm scan only, so the binding is stubbed alongside the upload.
    mocker.patch.object(publisher, "_attach_namespace", return_value=None)

    await publisher.startup()

    assert upload.await_count == 2
    assert {(call.args[1], call.args[0][1]) for call in upload.await_args_list} == {
        (b"first", ".css"),
        (b"second", ".css"),
    }


@pytest.mark.anyio
async def test_startup_failure_rolls_back_partial_prewarm_state(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    root = tmp_path / "assets"
    root.mkdir()
    first = root / "first.css"
    second = root / "second.css"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    settings = AssetPublisherSettings(
        request_header_value="prewarm-header",
        prewarm_enabled=True,
        prewarm_max_files=8,
        # File roots keep the prewarm order deterministic across platforms.
        prewarm_paths=(first, second),
        prewarm_extensions=("css",),
    )
    publisher = FilehostAssetPublisher(
        settings=settings,
        observer=NoopCacheObserver(),
        worker=AnyioWorkerExecutor(),
        local_access=ConfiguredLocalAccessPolicy(
            allowed_roots=(root,),
            allow_any=False,
        ),
        store=_unused_store(),
    )

    async def fake_upload(
        key: tuple[str, str],
        data: bytes,
        lease_ids: set[PublicationLeaseId],
    ) -> str:
        del key, lease_ids
        if data == b"second":
            raise KeyboardInterrupt
        return "https://assets.example/prewarmed-first"

    upload = mocker.patch.object(
        publisher,
        "_upload",
        new=mocker.AsyncMock(side_effect=fake_upload),
    )
    mocker.patch.object(publisher, "_attach_namespace", return_value=None)

    with pytest.raises(KeyboardInterrupt):
        await publisher.startup()

    # The partially prewarmed publication must not survive the failed step:
    # republishing the same payload uploads again instead of reusing a stale
    # cache entry.
    upload.side_effect = None
    upload.return_value = "https://assets.example/after-rollback"
    published = await publisher.publish(_inline(b"first"), suffix=".css")
    assert published.url == "https://assets.example/after-rollback"


@pytest.mark.anyio
async def test_hosted_http_server_enforces_guards_404_and_lifecycle() -> None:
    from aiohttp import ClientSession  # noqa: PLC0415

    store = HostedAssetStore(max_entries=8, max_bytes=1024)
    namespace = store.open_namespace(
        headers={"X-Test-Filehost": "guard-token"},
        public_base_url="http://public.example/assets/",
    )
    namespace_id = namespace.url_for("x").rsplit("/", 2)[-2]

    server = HostedAssetHttpServer(store, bind_host="127.0.0.1", bind_port=0)
    assert server.store is store
    await server.startup()
    published_url = await namespace.put("abc.css", b"body{}")
    assert published_url == (f"http://public.example/assets/{namespace_id}/abc.css")
    runner = server._runner
    assert runner is not None
    await server.startup()
    assert server._runner is runner
    host, port = runner.addresses[0][:2]
    asset_url = f"http://{host}:{port}/_htmlrender/assets/{namespace_id}/abc.css"
    missing_url = f"http://{host}:{port}/_htmlrender/assets/{namespace_id}/missing.css"

    try:
        async with ClientSession() as client:
            async with client.get(asset_url) as rejected:
                assert rejected.status == 403

            async with client.get(
                asset_url,
                headers={"X-Test-Filehost": "guard-token"},
            ) as response:
                assert response.status == 200
                assert await response.read() == b"body{}"
                assert response.headers["Access-Control-Allow-Origin"] == "*"
                assert response.headers["Cache-Control"] == (
                    "public, max-age=31536000, immutable"
                )

            async with client.get(
                missing_url,
                headers={"X-Test-Filehost": "guard-token"},
            ) as missing:
                assert missing.status == 404
    finally:
        await server.aclose()

    await server.aclose()
    with pytest.raises(ProviderLifecycleError, match="closed"):
        await server.startup()
    with pytest.raises(ResourcePublishError, match="closed"):
        await namespace.put("after-close", b"value")


@pytest.mark.anyio
async def test_hosted_store_capacity_evicts_lease_free_and_rejects_when_pinned() -> (
    None
):
    store = HostedAssetStore(max_entries=2, max_bytes=1024)
    await store.startup()
    namespace = store.open_namespace(
        headers={},
        public_base_url="http://public.example/a/",
    )
    ns_id = namespace.url_for("x").rsplit("/", 2)[-2]

    await namespace.put(
        "a",
        b"aa",
        lease_ids=(PublicationLeaseId("lease-a"),),
    )
    await namespace.put("b", b"bb")
    resident = store.lookup(ns_id, "b")
    assert resident is not None
    evicted_path = resident.path

    await namespace.put("c", b"cc")
    assert store.lookup(ns_id, "b") is None
    assert not evicted_path.exists()
    assert store.lookup(ns_id, "a") is not None

    assert await namespace.attach("c", PublicationLeaseId("lease-c"))
    with pytest.raises(HostedAssetCapacityError):
        await namespace.put("d", b"dd")

    await store.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize("name", ["../escape", "nested/asset", "/absolute", ".."])
async def test_hosted_store_rejects_paths_outside_namespace(name: str) -> None:
    store = HostedAssetStore(max_entries=8, max_bytes=1024)
    await store.startup()
    namespace = store.open_namespace(
        headers={},
        public_base_url="http://public.example/a/",
    )

    with pytest.raises(ResourcePublishError, match="single path segments"):
        await namespace.put(name, b"value")

    directory = store._directory
    assert directory is not None
    assert not tuple(path for path in directory.rglob("*") if path.is_file())
    await store.aclose()


@pytest.mark.anyio
async def test_hosted_store_rejects_symlinked_namespace_escape(tmp_path: Path) -> None:
    store = HostedAssetStore(max_entries=8, max_bytes=1024)
    await store.startup()
    namespace = store.open_namespace(
        headers={},
        public_base_url="http://public.example/a/",
    )
    namespace_id = namespace.url_for("asset").rsplit("/", 2)[-2]
    directory = store._directory
    assert directory is not None
    outside = tmp_path / "outside"
    outside.mkdir()
    (directory / namespace_id).symlink_to(outside, target_is_directory=True)

    with pytest.raises(ResourcePublishError, match="escapes"):
        await namespace.put("asset.css", b"value")

    assert not (outside / "asset.css").exists()
    await store.aclose()


@pytest.mark.anyio
async def test_publisher_and_store_share_lease_and_residency_state() -> None:
    store = HostedAssetStore(max_entries=8, max_bytes=1024)
    await store.startup()
    publisher = _publisher(
        store=store,
        public_base_url="http://public.example/assets/",
    )
    await publisher.startup()
    namespace = publisher._namespace
    assert namespace is not None
    namespace_id = namespace.url_for("x").rsplit("/", 2)[-2]
    lease = publisher.create_lease()

    published = await publisher.publish(
        _inline(b"asset"), lease_id=lease, suffix=".css"
    )
    name = published.url.rsplit("/", 1)[-1]
    asset = store.lookup(namespace_id, name)
    assert asset is not None
    assert lease in asset.leases

    # A cache hit re-confirms residency and pins the second lease in the
    # store as well.
    second_lease = publisher.create_lease()
    again = await publisher.publish(
        _inline(b"asset"), lease_id=second_lease, suffix=".css"
    )
    assert again.url == published.url
    assert second_lease in asset.leases

    # Releasing forwards to the store.
    await publisher.release(lease)
    await publisher.release(second_lease)
    assert asset.leases == set()

    # If the store dropped the asset, a reused URL mapping must not survive:
    # the publisher republishes instead of serving a dead URL.
    await store.close_namespace(namespace_id)
    assert store.lookup(namespace_id, name) is None
    replay = await publisher.publish(_inline(b"asset"), suffix=".css")
    assert store.lookup(namespace_id, replay.url.rsplit("/", 1)[-1]) is not None

    # clear() drops the namespace's lease-free assets and their files.
    replayed = store.lookup(namespace_id, name)
    assert replayed is not None
    path = replayed.path
    await publisher.clear()
    assert store.lookup(namespace_id, name) is None
    assert not path.exists()

    await publisher.aclose()
    await store.aclose()
