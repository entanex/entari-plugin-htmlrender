from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import anyio
import pytest

from entari_plugin_htmlrender.adapters.resources.reader import (
    AnyioWorkerExecutor,
    CompositeResourceFetcher,
    ConfiguredLocalAccessPolicy,
    RemoteTransportExecutor,
)
from entari_plugin_htmlrender.resources.config import (
    LocalLocalResourcePolicy,
    LocalResourceStrategy,
    RemoteLocalResourcePolicy,
    RemoteResourceStrategy,
    ResourceMaterializationPolicy,
    ResourceStrategy,
)
from entari_plugin_htmlrender.resources.models import (
    InlineResource,
    PublicationLeaseId,
    PublishedResource,
)
from entari_plugin_htmlrender.resources.service import ResourceService


def _published(url: str, headers: dict[str, str] | None = None) -> PublishedResource:
    return PublishedResource(url=url, request_headers=headers or {})


if TYPE_CHECKING:
    from pathlib import Path

    from playwright.async_api import Route, WebSocketRoute
    from pytest_mock import MockerFixture

    from entari_plugin_htmlrender.adapters.playwright.render import PlaywrightLease
    from entari_plugin_htmlrender.resources.ports import AssetPublisher


@dataclass(slots=True)
class _LeaseStub:
    mode: str
    browser: object = field(default_factory=object)


def _lease(mode: str, *, browser: object | None = None) -> PlaywrightLease:
    return cast(
        "PlaywrightLease",
        _LeaseStub(mode=mode, browser=object() if browser is None else browser),
    )


def _resources(
    *,
    remote: bool = True,
    remote_policy: RemoteLocalResourcePolicy = RemoteLocalResourcePolicy.MEMORY,
    local_policy: LocalLocalResourcePolicy = LocalLocalResourcePolicy.FILE,
    materialization_policy: ResourceMaterializationPolicy = (
        ResourceMaterializationPolicy.AUTO
    ),
    publisher: AssetPublisher | None = None,
) -> ResourceService:
    strategy: ResourceStrategy
    if remote:
        strategy = RemoteResourceStrategy(
            materialization_policy=materialization_policy,
            local_resource_policy=remote_policy,
        )
    else:
        strategy = LocalResourceStrategy(
            materialization_policy=materialization_policy,
            local_resource_policy=local_policy,
        )
    local_access = ConfiguredLocalAccessPolicy(allowed_roots=(), allow_any=True)
    return ResourceService(
        fetcher=CompositeResourceFetcher(
            AnyioWorkerExecutor(),
            local_access=local_access,
            remote_transport=RemoteTransportExecutor(max_concurrent_fetches=2),
        ),
        local_access=local_access,
        strategy=strategy,
        publisher=publisher,
    )


def _route(mocker: MockerFixture, url: str) -> SimpleNamespace:
    return _route_with_method(mocker, url, "GET")


def _route_with_method(
    mocker: MockerFixture,
    url: str,
    method: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        request=SimpleNamespace(url=url, method=method),
        abort=mocker.AsyncMock(),
        fulfill=mocker.AsyncMock(),
    )


def _write_font_stylesheet(root: Path) -> Path:
    stylesheet = root / "site.css"
    stylesheet.write_text(
        '@font-face { src: url("font.woff2") }',
        encoding="utf-8",
    )
    return stylesheet


def test_page_config_roundtrips_document_url() -> None:
    from entari_plugin_htmlrender.adapters.playwright.models import (  # noqa: PLC0415
        PageConfig,
        RenderConfig,
    )

    page = PageConfig(document_url="https://render/document")
    assert page.document_url == "https://render/document"
    page_dump = page.model_dump()
    assert page_dump["document_url"] == "https://render/document"
    assert "base_url" not in page_dump
    assert PageConfig.model_validate(page_dump) == page

    render = RenderConfig(page=page)
    restored_render = RenderConfig.model_validate_json(render.model_dump_json())
    assert restored_render == render
    assert restored_render.page.document_url == "https://render/document"


@pytest.mark.anyio
async def test_remote_http_navigation_is_resource_fallback(
    mocker: MockerFixture,
) -> None:
    from entari_plugin_htmlrender.adapters.playwright import (  # noqa: PLC0415
        operations,
    )
    from entari_plugin_htmlrender.adapters.playwright.models import (  # noqa: PLC0415
        ContentConfig,
        PageConfig,
        RenderConfig,
    )
    from entari_plugin_htmlrender.preparation import parse_html  # noqa: PLC0415

    document_url = "https://render.example/cards/card.html"
    page = PageConfig(document_url=document_url)
    execute = mocker.patch.object(
        operations,
        "_execute_browser_load_plan",
        new=mocker.AsyncMock(return_value=b"image"),
    )
    resources = _resources()
    prepared = parse_html('<img src="avatar.png">')

    assert (
        await operations.render_prepared_html(
            prepared,
            content=ContentConfig(html=prepared.html),
            render=RenderConfig(page=page),
            lease=_lease("remote_ws"),
            resources=resources,
            asset_publisher=None,
            resolve_mode=ResourceMaterializationPolicy.STRICT,
        )
        == b"image"
    )

    assert execute.await_count == 1
    for call in execute.await_args_list:
        plan = call.args[0]
        assert plan.document_url == document_url
        assert plan.base_href == document_url
        assert '<base href="https://render.example/cards/card.html">' in plan.html


@pytest.mark.anyio
async def test_remote_prepared_render_routes_local_assets_without_file_navigation(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    from entari_plugin_htmlrender.adapters.playwright.models import (  # noqa: PLC0415
        ContentConfig,
        PageConfig,
        RenderConfig,
    )
    from entari_plugin_htmlrender.adapters.playwright.operations import (  # noqa: PLC0415
        render_prepared_html,
    )
    from entari_plugin_htmlrender.preparation import parse_html  # noqa: PLC0415

    (tmp_path / "avatar.png").write_bytes(b"avatar")
    base_url = f"{tmp_path.as_uri().rstrip('/')}/"
    prepared = parse_html('<img src="avatar.png">', base_url=base_url)
    render = RenderConfig(page=PageConfig())
    page = mocker.AsyncMock()
    page.on = mocker.MagicMock()
    page.screenshot = mocker.AsyncMock(return_value=b"image")
    context_manager = mocker.MagicMock()
    context_manager.__aenter__ = mocker.AsyncMock(return_value=page)
    context_manager.__aexit__ = mocker.AsyncMock(return_value=None)
    mocker.patch(
        "entari_plugin_htmlrender.adapters.playwright.operations.PageContext.open",
        return_value=context_manager,
    )
    mocker.patch(
        "entari_plugin_htmlrender.adapters.playwright.operations.log_page_telemetry",
        new=mocker.AsyncMock(),
    )

    result = await render_prepared_html(
        prepared,
        content=ContentConfig(html=prepared.html),
        render=render,
        lease=_lease("remote_ws"),
        resources=_resources(),
        asset_publisher=None,
        resolve_mode=ResourceMaterializationPolicy.STRICT,
    )

    assert result == b"image"
    page.goto.assert_not_awaited()
    injected = page.set_content.await_args.args[0]
    assert "file://" not in injected
    assert "https://htmlrender.invalid/.htmlrender/assets/" in injected
    page.context.route.assert_awaited_once_with("**/*", mocker.ANY)
    page.route.assert_awaited_once_with(
        "https://htmlrender.invalid/.htmlrender/assets/**",
        mocker.ANY,
    )
    page.context.route_web_socket.assert_awaited_once_with("**/*", mocker.ANY)


@pytest.mark.anyio
async def test_remote_passthrough_preserves_shared_file_navigation(
    mocker: MockerFixture,
) -> None:
    from entari_plugin_htmlrender.adapters.playwright.models import (  # noqa: PLC0415
        ContentConfig,
        PageConfig,
        RenderConfig,
    )
    from entari_plugin_htmlrender.adapters.playwright.operations import (  # noqa: PLC0415
        render_prepared_html,
    )
    from entari_plugin_htmlrender.preparation import parse_html  # noqa: PLC0415

    prepared = parse_html(
        '<img src="avatar.png">',
        base_url="file:///shared/card/",
    )
    execute = mocker.patch(
        "entari_plugin_htmlrender.adapters.playwright.operations._execute_browser_load_plan",
        new=mocker.AsyncMock(return_value=b"image"),
    )

    result = await render_prepared_html(
        prepared,
        content=ContentConfig(html=prepared.html),
        render=RenderConfig(
            page=PageConfig(document_url="file:///shared/card/document.html")
        ),
        lease=_lease("remote_ws"),
        resources=_resources(remote_policy=RemoteLocalResourcePolicy.PASSTHROUGH),
        asset_publisher=None,
    )

    assert result == b"image"
    call = execute.await_args
    assert call is not None
    plan = call.args[0]
    assert plan.document_url == "file:///shared/card/document.html"
    assert plan.base_href == "file:///shared/card/"
    assert "avatar.png" in plan.html
    assert plan.asset_routes == ()


@pytest.mark.parametrize(
    "mode",
    [
        pytest.param("local_pw", id="local-file"),
        pytest.param("remote_ws", id="remote-passthrough"),
    ],
)
@pytest.mark.anyio
async def test_direct_file_policies_canonicalize_relative_document_base(
    mocker: MockerFixture,
    mode: str,
) -> None:
    from entari_plugin_htmlrender.adapters.playwright.models import (  # noqa: PLC0415
        ContentConfig,
        PageConfig,
        RenderConfig,
    )
    from entari_plugin_htmlrender.adapters.playwright.operations import (  # noqa: PLC0415
        render_prepared_html,
    )
    from entari_plugin_htmlrender.preparation import parse_html  # noqa: PLC0415

    prepared = parse_html(
        '<head><base href="assets/"></head><img src="avatar.png">',
        base_url="file:///shared/cards/document.html",
    )
    execute = mocker.patch(
        "entari_plugin_htmlrender.adapters.playwright.operations._execute_browser_load_plan",
        new=mocker.AsyncMock(return_value=b"image"),
    )
    resources = _resources(
        remote=mode != "local_pw",
        remote_policy=RemoteLocalResourcePolicy.PASSTHROUGH,
    )

    result = await render_prepared_html(
        prepared,
        content=ContentConfig(html=prepared.html),
        render=RenderConfig(page=PageConfig()),
        lease=_lease(mode),
        resources=resources,
        asset_publisher=None,
    )

    assert result == b"image"
    assert execute.await_args is not None
    plan = execute.await_args.args[0]
    assert plan.document_url is None
    assert plan.base_href == "file:///shared/cards/assets/"
    assert '<base href="file:///shared/cards/assets/">' in plan.html
    assert 'src="avatar.png"' in plan.html
    assert plan.asset_routes == ()


@pytest.mark.anyio
async def test_remote_error_policy_rejects_local_resources_before_page_open(
    mocker: MockerFixture,
) -> None:
    from entari_plugin_htmlrender.adapters.playwright.models import (  # noqa: PLC0415
        ContentConfig,
        RenderConfig,
    )
    from entari_plugin_htmlrender.adapters.playwright.operations import (  # noqa: PLC0415
        render_prepared_html,
    )
    from entari_plugin_htmlrender.preparation import parse_html  # noqa: PLC0415
    from entari_plugin_htmlrender.preparation.materialize import (  # noqa: PLC0415
        AssetMaterializationError,
    )

    prepared = parse_html(
        '<img src="avatar.png">',
        base_url="file:///private/card/",
    )
    execute = mocker.patch(
        "entari_plugin_htmlrender.adapters.playwright.operations._execute_browser_load_plan",
        new=mocker.AsyncMock(return_value=b"unexpected"),
    )

    with pytest.raises(AssetMaterializationError, match="not allowed"):
        await render_prepared_html(
            prepared,
            content=ContentConfig(html=prepared.html),
            render=RenderConfig(),
            lease=_lease("remote_ws"),
            resources=_resources(remote_policy=RemoteLocalResourcePolicy.ERROR),
            asset_publisher=None,
            resolve_mode=ResourceMaterializationPolicy.AUTO,
        )

    execute.assert_not_awaited()


@pytest.mark.anyio
async def test_remote_error_policy_accepts_http_fallback_with_relative_base(
    mocker: MockerFixture,
) -> None:
    from entari_plugin_htmlrender.adapters.playwright.models import (  # noqa: PLC0415
        ContentConfig,
        PageConfig,
        RenderConfig,
    )
    from entari_plugin_htmlrender.adapters.playwright.operations import (  # noqa: PLC0415
        render_prepared_html,
    )
    from entari_plugin_htmlrender.preparation import parse_html  # noqa: PLC0415

    prepared = parse_html(
        '<base href="assets/"><img src="avatar.png">',
    )
    execute = mocker.patch(
        "entari_plugin_htmlrender.adapters.playwright.operations._execute_browser_load_plan",
        new=mocker.AsyncMock(return_value=b"image"),
    )

    result = await render_prepared_html(
        prepared,
        content=ContentConfig(html=prepared.html),
        render=RenderConfig(
            page=PageConfig(document_url="https://render.example/cards/card.html")
        ),
        lease=_lease("remote_ws"),
        resources=_resources(remote_policy=RemoteLocalResourcePolicy.ERROR),
        asset_publisher=None,
        resolve_mode=ResourceMaterializationPolicy.STRICT,
    )

    assert result == b"image"
    assert execute.await_args is not None
    plan = execute.await_args.args[0]
    assert plan.base_href == "https://render.example/cards/assets/"


@pytest.mark.anyio
async def test_remote_filehost_policy_publishes_materialized_assets(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    from entari_plugin_htmlrender.adapters.playwright.models import (  # noqa: PLC0415
        ContentConfig,
        RenderConfig,
    )
    from entari_plugin_htmlrender.adapters.playwright.operations import (  # noqa: PLC0415
        render_prepared_html,
    )
    from entari_plugin_htmlrender.preparation import parse_html  # noqa: PLC0415

    (tmp_path / "avatar.png").write_bytes(b"avatar")
    prepared = parse_html(
        '<img src="avatar.png">',
        base_url=f"{tmp_path.as_uri().rstrip('/')}/",
    )
    execute = mocker.patch(
        "entari_plugin_htmlrender.adapters.playwright.operations._execute_browser_load_plan",
        new=mocker.AsyncMock(return_value=b"image"),
    )
    publisher = mocker.Mock()
    publisher.create_lease.return_value = "lease"
    publisher.publish = mocker.AsyncMock(
        return_value=_published(
            "http://filehost/filehost/avatar",
            {"X-HTMLRender-Filehost-Request": "unit-token"},
        )
    )
    publisher.release = mocker.AsyncMock()

    result = await render_prepared_html(
        prepared,
        content=ContentConfig(html=prepared.html),
        render=RenderConfig(),
        lease=_lease("remote_ws"),
        resources=_resources(
            remote_policy=RemoteLocalResourcePolicy.FILEHOST,
        ),
        asset_publisher=publisher,
        resolve_mode=ResourceMaterializationPolicy.STRICT,
    )

    assert result == b"image"
    publisher.publish.assert_awaited_once_with(
        InlineResource(b"avatar", "image/png"),
        lease_id="lease",
        suffix=".png",
    )
    publisher.release.assert_awaited_once_with("lease")
    call = execute.await_args
    assert call is not None
    plan = call.args[0]
    assert "http://filehost/filehost/avatar" in plan.html
    assert plan.asset_routes == ()


@pytest.mark.anyio
async def test_resolve_mode_off_bypasses_filehost_without_a_publisher(
    mocker: MockerFixture,
) -> None:
    from entari_plugin_htmlrender.adapters.playwright.models import (  # noqa: PLC0415
        ContentConfig,
        RenderConfig,
    )
    from entari_plugin_htmlrender.adapters.playwright.operations import (  # noqa: PLC0415
        render_prepared_html,
    )
    from entari_plugin_htmlrender.preparation import parse_html  # noqa: PLC0415

    prepared = parse_html(
        '<img src="avatar.png">',
        base_url="file:///shared/card/",
    )
    execute = mocker.patch(
        "entari_plugin_htmlrender.adapters.playwright.operations._execute_browser_load_plan",
        new=mocker.AsyncMock(return_value=b"image"),
    )

    result = await render_prepared_html(
        prepared,
        content=ContentConfig(html=prepared.html),
        render=RenderConfig(),
        lease=_lease("remote_ws"),
        resources=_resources(
            remote_policy=RemoteLocalResourcePolicy.FILEHOST,
            materialization_policy=ResourceMaterializationPolicy.OFF,
        ),
        asset_publisher=None,
    )

    assert result == b"image"
    assert execute.await_args is not None
    plan = execute.await_args.args[0]
    assert plan.base_href == "file:///shared/card/"
    assert plan.asset_routes == ()
    assert execute.await_args.kwargs["filehost_authorization"] == {}


@pytest.mark.anyio
async def test_per_call_off_does_not_touch_composed_filehost_publisher(
    mocker: MockerFixture,
) -> None:
    from entari_plugin_htmlrender.adapters.playwright.models import (  # noqa: PLC0415
        ContentConfig,
        RenderConfig,
    )
    from entari_plugin_htmlrender.adapters.playwright.operations import (  # noqa: PLC0415
        render_prepared_html,
    )
    from entari_plugin_htmlrender.preparation import parse_html  # noqa: PLC0415

    prepared = parse_html(
        '<img src="avatar.png">',
        base_url="file:///shared/card/",
    )
    mocker.patch(
        "entari_plugin_htmlrender.adapters.playwright.operations._execute_browser_load_plan",
        new=mocker.AsyncMock(return_value=b"image"),
    )
    publisher = mocker.Mock()

    result = await render_prepared_html(
        prepared,
        content=ContentConfig(html=prepared.html),
        render=RenderConfig(),
        lease=_lease("remote_ws"),
        resources=_resources(remote_policy=RemoteLocalResourcePolicy.FILEHOST),
        asset_publisher=publisher,
        resolve_mode=ResourceMaterializationPolicy.OFF,
    )

    assert result == b"image"
    assert publisher.mock_calls == []


@pytest.mark.anyio
async def test_filehost_render_releases_owned_lease_under_cancellation(
    mocker: MockerFixture,
) -> None:
    from entari_plugin_htmlrender.adapters.playwright import (  # noqa: PLC0415
        operations,
    )
    from entari_plugin_htmlrender.adapters.playwright.models import (  # noqa: PLC0415
        ContentConfig,
        RenderConfig,
    )
    from entari_plugin_htmlrender.preparation import (  # noqa: PLC0415
        PreparedAsset,
        parse_html,
    )

    prepared = parse_html(
        '<img src="memory:avatar">',
        assets=(PreparedAsset("memory:avatar", b"avatar", "image/png"),),
    )
    started = anyio.Event()
    owner_scope: anyio.CancelScope | None = None

    async def execute(*args: object, **kwargs: object) -> bytes:
        del args, kwargs
        started.set()
        await anyio.sleep_forever()
        raise AssertionError("unreachable")

    publisher = mocker.Mock()
    publisher.create_lease.return_value = "lease"
    publisher.publish = mocker.AsyncMock(
        return_value=_published("https://filehost.example/avatar.png")
    )
    mocker.patch.object(operations, "_execute_browser_load_plan", side_effect=execute)
    publisher.release = mocker.AsyncMock()

    async def render() -> None:
        nonlocal owner_scope
        with anyio.CancelScope() as scope:
            owner_scope = scope
            await operations.render_prepared_html(
                prepared,
                content=ContentConfig(html=prepared.html),
                render=RenderConfig(),
                lease=_lease("remote_ws"),
                resources=_resources(
                    remote_policy=RemoteLocalResourcePolicy.FILEHOST,
                ),
                asset_publisher=publisher,
            )

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(render)
        await started.wait()
        if owner_scope is None:
            raise RuntimeError("render cancellation scope was not initialized")
        owner_scope.cancel()

    publisher.release.assert_awaited_once_with("lease")


@pytest.mark.anyio
async def test_filehost_asset_graph_preserves_css_and_font_suffixes(
    mocker: MockerFixture,
) -> None:
    from entari_plugin_htmlrender.adapters.playwright.operations import (  # noqa: PLC0415
        _publish_prepared_assets,
    )
    from entari_plugin_htmlrender.preparation import (  # noqa: PLC0415
        PreparedAsset,
        parse_html,
    )

    font = PreparedAsset(
        "file:///card/font.woff2",
        b"font",
        "font/woff2",
    )
    stylesheet = PreparedAsset(
        "file:///card/site.css",
        b'@font-face { src: url("font.woff2") }',
        "text/css",
    )
    prepared = parse_html(
        '<link rel="stylesheet" href="site.css">',
        base_url="file:///card/document.html",
        assets=(stylesheet, font),
    )

    async def publish(
        payload: InlineResource,
        *,
        lease_id: PublicationLeaseId,
        suffix: str | None,
    ) -> PublishedResource:
        assert lease_id == "lease"
        return _published(
            f"http://filehost/filehost/{len(payload.data)}{suffix or ''}",
            {"X-HTMLRender-Filehost-Request": "unit-token"},
        )

    publisher = mocker.Mock()
    publisher.publish = mocker.AsyncMock(side_effect=publish)

    urls, authorization = await _publish_prepared_assets(
        prepared,
        publisher=publisher,
        lease_id=PublicationLeaseId("lease"),
    )

    assert urls[font.source].endswith(".woff2")
    assert urls[stylesheet.source].endswith(".css")
    calls = publisher.publish.await_args_list
    assert calls[0].kwargs["suffix"] == ".woff2"
    assert calls[1].kwargs["suffix"] == ".css"
    assert urls[font.source].encode() in calls[1].args[0].data
    # Every publication's exact URL carries its own authorization.
    assert set(authorization) == {urls[font.source], urls[stylesheet.source]}
    assert all(
        headers["X-HTMLRender-Filehost-Request"] == "unit-token"
        for headers in authorization.values()
    )


@pytest.mark.anyio
async def test_local_file_policy_keeps_stylesheet_io_in_browser(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    from entari_plugin_htmlrender.adapters.playwright.models import (  # noqa: PLC0415
        ContentConfig,
        RenderConfig,
    )
    from entari_plugin_htmlrender.adapters.playwright.operations import (  # noqa: PLC0415
        render_prepared_html,
    )
    from entari_plugin_htmlrender.preparation import (  # noqa: PLC0415
        PreparedStylesheet,
        parse_html,
    )

    stylesheet = _write_font_stylesheet(tmp_path)
    prepared = parse_html(
        "<p>ok</p>",
        stylesheets=(
            PreparedStylesheet(
                css=stylesheet.read_text(encoding="utf-8"),
                base_url=stylesheet.as_uri(),
            ),
        ),
    )
    execute = mocker.patch(
        "entari_plugin_htmlrender.adapters.playwright.operations._execute_browser_load_plan",
        new=mocker.AsyncMock(return_value=b"image"),
    )
    materialize = mocker.patch(
        "entari_plugin_htmlrender.adapters.playwright.operations.materialize_local_assets",
        new=mocker.AsyncMock(),
    )

    result = await render_prepared_html(
        prepared,
        content=ContentConfig(html=prepared.html),
        render=RenderConfig(),
        lease=_lease("local_pw"),
        resources=_resources(remote=False),
        asset_publisher=None,
    )

    assert result == b"image"
    materialize.assert_not_awaited()
    call = execute.await_args
    assert call is not None
    plan = call.args[0]
    assert (tmp_path / "font.woff2").as_uri() in plan.html
    assert "https://htmlrender.invalid" not in plan.html


@pytest.mark.anyio
async def test_resource_url_token_authorization_matches_playwright_request_without_fragment(
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    from entari_plugin_htmlrender.adapters.playwright._page import (  # noqa: PLC0415
        ManagedRequestGuard,
    )

    asset = tmp_path / "asset one.svg"
    payload = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
    asset.write_bytes(payload)
    publisher = mocker.Mock()
    publisher.publish = mocker.AsyncMock(
        return_value=_published(
            "https://assets.example/asset.svg",
            {"X-HTMLRender-Filehost-Request": "unit-token"},
        )
    )
    resources = _resources(
        remote_policy=RemoteLocalResourcePolicy.FILEHOST,
        publisher=publisher,
    )

    resolution = await resources.resolve_url_tokens(
        ["asset%20one.svg?theme=dark#icon"],
        template_base=tmp_path,
        strict=True,
    )

    published = "https://assets.example/asset.svg?theme=dark#icon"
    normalized = "https://assets.example/asset.svg?theme=dark"
    assert resolution.value == [published]
    assert resolution.request_headers_by_url == {
        normalized: {"X-HTMLRender-Filehost-Request": "unit-token"}
    }
    publication = publisher.publish.await_args
    assert publication is not None
    assert publication.args[0].data == payload

    exact = _route(mocker, normalized)
    resources.fetch_published = mocker.AsyncMock(
        return_value=SimpleNamespace(
            data=payload,
            media_type="image/svg+xml",
            final_url=None,
        )
    )
    resources.fetch = mocker.AsyncMock()
    guard = ManagedRequestGuard(
        resources,
        authorization=resolution.request_headers_by_url,
    )

    await guard._handle_route(cast("Route", exact))
    captured = resources.fetch_published.await_args
    assert captured is not None
    published_capability = captured.args[0]
    assert published_capability.url == normalized
    assert published_capability.request_headers == {
        "X-HTMLRender-Filehost-Request": "unit-token"
    }
    resources.fetch.assert_not_awaited()
    exact.fulfill.assert_awaited_once_with(
        status=200,
        body=payload,
        content_type="image/svg+xml",
        headers={"access-control-allow-origin": "*"},
    )

    other_query = _route(
        mocker,
        "https://assets.example/asset.svg?theme=light",
    )
    resources.fetch.return_value = SimpleNamespace(
        data=b"other",
        media_type=None,
        final_url=None,
    )
    await guard._handle_route(cast("Route", other_query))
    captured = resources.fetch.await_args
    assert captured is not None
    fallback = captured.args[0]
    assert fallback.url == "https://assets.example/asset.svg?theme=light"
    other_query.fulfill.assert_awaited_once_with(
        status=200,
        body=b"other",
        content_type="application/octet-stream",
        headers={"access-control-allow-origin": "*"},
    )

    exact.abort.assert_not_awaited()


@pytest.mark.anyio
async def test_managed_request_guard_rewrites_redirected_css_against_final_url(
    mocker: MockerFixture,
) -> None:
    from entari_plugin_htmlrender.adapters.playwright._page import (  # noqa: PLC0415
        ManagedRequestGuard,
    )

    resources = mocker.Mock()
    resources.fetch = mocker.AsyncMock(
        return_value=SimpleNamespace(
            data=b"body { background: url('pixel.png') }",
            media_type="text/css",
            final_url="https://example.com/assets/style.css",
        )
    )
    resources.fetch_published = mocker.AsyncMock()
    guard = ManagedRequestGuard(resources, authorization={})
    route = _route(mocker, "https://example.com/style.css")

    await guard._handle_route(cast("Route", route))

    route.fulfill.assert_awaited_once_with(
        status=200,
        body=b"body { background: url('https://example.com/assets/pixel.png') }",
        content_type="text/css",
        headers={"access-control-allow-origin": "*"},
    )
    route.abort.assert_not_awaited()


@pytest.mark.anyio
async def test_managed_request_guard_applies_presets_and_publication_override(
    mocker: MockerFixture,
) -> None:
    from entari_plugin_htmlrender.adapters.playwright._page import (  # noqa: PLC0415
        ManagedRequestGuard,
    )

    payload = b"asset"
    resources = mocker.Mock()
    resources.fetch_published = mocker.AsyncMock(
        return_value=SimpleNamespace(
            data=payload,
            media_type="application/octet-stream",
            final_url=None,
        )
    )
    resources.fetch = mocker.AsyncMock()
    guard = ManagedRequestGuard(
        resources,
        authorization={
            "https://example.com/asset": {
                "authorization": "publication",
                "X-Publication": "yes",
            }
        },
        preset_request_headers={
            "Authorization": "preset",
            "User-Agent": "Configured UA",
            "X-Trace": "trace",
        },
    )
    route = _route(mocker, "https://example.com/asset")
    route.request.headers = {
        "Cookie": "untrusted-browser-cookie",
        "X-Browser": "untrusted",
    }

    await guard._handle_route(cast("Route", route))

    fetched = resources.fetch_published.await_args
    assert fetched is not None
    capability = fetched.args[0]
    assert capability.url == "https://example.com/asset"
    assert capability.request_headers == {
        "User-Agent": "Configured UA",
        "X-Trace": "trace",
        "authorization": "publication",
        "X-Publication": "yes",
    }
    resources.fetch.assert_not_awaited()
    route.fulfill.assert_awaited_once_with(
        status=200,
        body=payload,
        content_type="application/octet-stream",
        headers={"access-control-allow-origin": "*"},
    )


@pytest.mark.anyio
async def test_managed_request_guard_preserves_css_fragment_and_blocks_html_redirect(
    mocker: MockerFixture,
) -> None:
    from entari_plugin_htmlrender.adapters.playwright._page import (  # noqa: PLC0415
        ManagedRequestGuard,
    )
    from entari_plugin_htmlrender.resources.errors import (  # noqa: PLC0415
        ResourceFetchError,
    )

    resources = mocker.Mock()
    resources.fetch = mocker.AsyncMock(
        return_value=SimpleNamespace(
            data=b"body { background: url('pixel.svg#icon') }",
            media_type="text/css",
            final_url="https://example.com/assets/style.css",
        )
    )
    guard = ManagedRequestGuard(resources, authorization={})
    route = _route(mocker, "https://example.com/style.css")
    await guard._handle_route(cast("Route", route))
    route.fulfill.assert_awaited_once_with(
        status=200,
        body=b"body { background: url('https://example.com/assets/pixel.svg#icon') }",
        content_type="text/css",
        headers={"access-control-allow-origin": "*"},
    )

    resources.fetch.return_value = SimpleNamespace(
        data=b"<p>redirected</p>",
        media_type="text/html",
        final_url="https://example.com/final.html",
    )
    html = _route(mocker, "https://example.com/start.html")
    html_guard = ManagedRequestGuard(resources, authorization={})
    await html_guard._handle_route(cast("Route", html))
    html.abort.assert_awaited_once_with(error_code="blockedbyclient")
    html.fulfill.assert_not_awaited()
    with pytest.raises(ResourceFetchError, match="Redirected HTML"):
        html_guard.raise_if_failed()


@pytest.mark.anyio
async def test_managed_request_guard_rejects_non_get_and_surfaces_failure(
    mocker: MockerFixture,
) -> None:
    from entari_plugin_htmlrender.adapters.playwright._page import (  # noqa: PLC0415
        ManagedRequestGuard,
    )
    from entari_plugin_htmlrender.resources.errors import (  # noqa: PLC0415
        ResourceAccessDeniedError,
    )

    resources = mocker.Mock()
    resources.fetch = mocker.AsyncMock()
    resources.fetch_published = mocker.AsyncMock()
    guard = ManagedRequestGuard(
        resources,
        authorization={
            "https://assets.example/filehost/a": {
                "X-HTMLRender-Filehost-Request": "token"
            }
        },
    )

    post = _route_with_method(
        mocker,
        "https://assets.example/filehost/a",
        "POST",
    )
    await guard._handle_route(cast("Route", post))
    post.abort.assert_awaited_once_with(error_code="blockedbyclient")
    post.fulfill.assert_not_awaited()
    resources.fetch.assert_not_awaited()
    resources.fetch_published.assert_not_awaited()
    with pytest.raises(ResourceAccessDeniedError, match="only allow GET"):
        guard.raise_if_failed()


@pytest.mark.anyio
async def test_managed_request_guard_preserves_cancellation(
    mocker: MockerFixture,
) -> None:
    from entari_plugin_htmlrender.adapters.playwright._page import (  # noqa: PLC0415
        ManagedRequestGuard,
    )

    cancelled = anyio.get_cancelled_exc_class()
    resources = mocker.Mock()
    resources.fetch = mocker.AsyncMock(side_effect=cancelled())
    resources.fetch_published = mocker.AsyncMock()
    guard = ManagedRequestGuard(resources, authorization={})
    route = _route(mocker, "https://example.com/asset.png")

    with pytest.raises(cancelled):
        await guard._handle_route(cast("Route", route))
    route.abort.assert_awaited_once_with(error_code="aborted")


@pytest.mark.anyio
async def test_managed_request_guard_closes_web_socket_and_records_denial(
    mocker: MockerFixture,
) -> None:
    from entari_plugin_htmlrender.adapters.playwright._page import (  # noqa: PLC0415
        ManagedRequestGuard,
    )
    from entari_plugin_htmlrender.resources.errors import (  # noqa: PLC0415
        ResourceAccessDeniedError,
    )

    resources = mocker.Mock()
    guard = ManagedRequestGuard(resources, authorization={})
    socket = SimpleNamespace(
        url="wss://example.com/socket",
        close=mocker.AsyncMock(),
    )

    await guard._reject_web_socket(cast("WebSocketRoute", socket))

    socket.close.assert_awaited_once_with(
        code=1008,
        reason="WebSocket access is blocked",
    )
    with pytest.raises(ResourceAccessDeniedError, match="WebSocket"):
        guard.raise_if_failed()


@pytest.mark.anyio
async def test_page_context_uses_injected_lease(
    mocker: MockerFixture,
) -> None:
    from playwright.async_api import Browser  # noqa: PLC0415

    from entari_plugin_htmlrender.adapters.playwright import _page  # noqa: PLC0415

    page = mocker.AsyncMock()
    browser = mocker.AsyncMock(spec=Browser)
    browser.new_page.return_value = page
    instrument = mocker.patch(
        "entari_plugin_htmlrender.adapters.playwright._page.instrument_page"
    )
    detach = mocker.patch(
        "entari_plugin_htmlrender.adapters.playwright._page.detach_page"
    )
    lease = _lease("local_pw", browser=browser)
    async with _page.PageContext(lease).open(
        viewport={"width": 1, "height": 1},
    ) as page2:
        assert page2 is page
    browser.new_page.assert_awaited_once_with(viewport={"width": 1, "height": 1})
    instrument.assert_called_once()
    detach.assert_called_once_with(page)


@pytest.mark.anyio
async def test_managed_execution_blocks_service_workers(
    mocker: MockerFixture,
) -> None:
    from playwright.async_api import Browser  # noqa: PLC0415

    from entari_plugin_htmlrender.adapters.playwright import (  # noqa: PLC0415
        _page,
        operations,
    )
    from entari_plugin_htmlrender.adapters.playwright.models import (  # noqa: PLC0415
        ContentConfig,
        PageConfig,
        RenderConfig,
    )
    from entari_plugin_htmlrender.adapters.playwright.prepared import (  # noqa: PLC0415
        BrowserLoadPlan,
    )
    from entari_plugin_htmlrender.preparation import parse_html  # noqa: PLC0415

    browser = mocker.AsyncMock(spec=Browser)
    page = browser.new_page.return_value
    page.on = mocker.MagicMock()
    page.set_content = mocker.AsyncMock()
    page.wait_for_timeout = mocker.AsyncMock()
    page.screenshot = mocker.AsyncMock(return_value=b"image")
    mocker.patch.object(_page, "instrument_page")
    mocker.patch.object(_page, "detach_page")
    mocker.patch.object(
        operations,
        "log_page_telemetry",
        new=mocker.AsyncMock(),
    )
    mocker.patch.object(
        operations,
        "install_browser_asset_routes",
        new=mocker.AsyncMock(),
    )
    guard = mocker.Mock()
    guard.install = mocker.AsyncMock()
    guard.raise_if_failed = mocker.Mock()
    guard_factory = mocker.patch.object(
        operations,
        "ManagedRequestGuard",
        return_value=guard,
    )
    prepared = parse_html("<main>managed</main>")
    resources = _resources()

    result = await operations._execute_browser_load_plan(
        BrowserLoadPlan(html=prepared.html),
        content=ContentConfig(html=prepared.html),
        render=RenderConfig(
            page=PageConfig(
                user_agent="Configured UA",
                extra_http_headers={
                    "user-agent": "Header UA",
                    "X-Trace": "trace",
                },
            )
        ),
        lease=_lease("local_pw", browser=browser),
        resources=resources,
        filehost_authorization={},
        telemetry_op="test",
    )

    assert result == b"image"
    assert browser.new_page.await_args.kwargs["service_workers"] == "block"
    assert browser.new_page.await_args.kwargs["user_agent"] == "Configured UA"
    guard_factory.assert_called_once_with(
        resources,
        authorization={},
        preset_request_headers={
            "user-agent": "Header UA",
            "X-Trace": "trace",
        },
    )
    guard.install.assert_awaited_once_with(page)
    page.close.assert_awaited_once_with()


@pytest.mark.anyio
async def test_page_context_detaches_telemetry_on_error_and_cancellation(
    mocker: MockerFixture,
) -> None:
    from playwright.async_api import Browser  # noqa: PLC0415

    from entari_plugin_htmlrender.adapters.playwright import (  # noqa: PLC0415
        _page,
        telemetry,
    )

    error_page = mocker.AsyncMock()
    error_page.on = mocker.MagicMock()
    error_browser = mocker.AsyncMock(spec=Browser)
    error_browser.new_page.return_value = error_page
    error_lease = _lease("local_pw", browser=error_browser)

    with pytest.raises(RuntimeError, match="render failed"):
        async with _page.PageContext(error_lease).open() as opened:
            assert telemetry.get_page_collector(opened) is not None
            raise RuntimeError("render failed")
    assert telemetry.get_page_collector(error_page) is None
    error_page.close.assert_awaited_once_with()

    cancelled_page = mocker.AsyncMock()
    cancelled_page.on = mocker.MagicMock()
    cancelled_browser = mocker.AsyncMock(spec=Browser)
    cancelled_browser.new_page.return_value = cancelled_page
    cancelled_lease = _lease("local_pw", browser=cancelled_browser)
    started = anyio.Event()
    owner_scope: anyio.CancelScope | None = None

    async def hold_page() -> None:
        nonlocal owner_scope
        with anyio.CancelScope() as scope:
            owner_scope = scope
            async with _page.PageContext(cancelled_lease).open() as opened:
                assert telemetry.get_page_collector(opened) is not None
                started.set()
                await anyio.sleep_forever()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(hold_page)
        await started.wait()
        if owner_scope is None:
            raise RuntimeError("page cancellation scope was not initialized")
        owner_scope.cancel()

    assert telemetry.get_page_collector(cancelled_page) is None
    cancelled_page.close.assert_awaited_once_with()


def test_normalize_request_url_drops_default_port_and_fragment() -> None:
    from entari_plugin_htmlrender.adapters.playwright._page import (  # noqa: PLC0415
        _normalize_request_url,
    )

    assert (
        _normalize_request_url("HTTP://Render:80/filehost/a?v=1#frag")
        == "http://render/filehost/a?v=1"
    )
    assert (
        _normalize_request_url("https://render:8443/filehost/a")
        == "https://render:8443/filehost/a"
    )
