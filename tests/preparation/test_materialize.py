from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from entari_plugin_htmlrender.adapters.resources import (
    AnyioWorkerExecutor,
    ConfiguredLocalAccessPolicy,
    RemoteTransportExecutor,
    build_resource_fetcher,
)
from entari_plugin_htmlrender.preparation import PreparedStylesheet, parse_html
from entari_plugin_htmlrender.preparation.materialize import (
    AssetMaterializationError,
    materialize_local_assets,
)
from entari_plugin_htmlrender.resources.config import (
    LocalResourceStrategy,
    ResourceCacheSettings,
    ResourceMaterializationPolicy,
)
from entari_plugin_htmlrender.resources.models import FileResourceRef
from entari_plugin_htmlrender.resources.observation import NoopCacheObserver
from entari_plugin_htmlrender.resources.service import ResourceService

if TYPE_CHECKING:
    from pathlib import Path

    from entari_plugin_htmlrender.preparation.service import DefaultHtmlPreparer


async def test_materialize_recurses_through_stylesheets(
    tmp_path: Path,
    resources: ResourceService,
) -> None:
    styles = tmp_path / "styles"
    styles.mkdir()
    document = tmp_path / "document.html"
    image = tmp_path / "image.png"
    stylesheet = styles / "site.css"
    imported = styles / "theme.css"
    font = styles / "font.woff2"
    image.write_bytes(b"png")
    font.write_bytes(b"font")
    stylesheet.write_text(
        '@import "theme.css"; .hero { background: url(../image.png) }'
    )
    imported.write_text('@font-face { src: url("font.woff2") }')
    prepared = parse_html(
        '<link rel="stylesheet" href="styles/site.css"><img src="image.png">',
        base_url=document.as_uri(),
    )
    materialized = await materialize_local_assets(prepared, resources=resources)
    assert {asset.source for asset in materialized.assets} == {
        stylesheet.as_uri(),
        imported.as_uri(),
        image.as_uri(),
        font.as_uri(),
    }


async def test_materialize_strict_and_tolerant_modes(
    resources: ResourceService,
) -> None:
    prepared = parse_html('<img src="relative.png">')
    with pytest.raises(AssetMaterializationError, match="no filesystem base"):
        await materialize_local_assets(prepared, resources=resources)
    assert (
        await materialize_local_assets(prepared, resources=resources, strict=False)
    ).assets == ()


@pytest.mark.parametrize(
    "filename",
    (
        "literal%20name.png",
        "中文 空格.png",
        "hash#fragment.png",
        "literal%25name.png",
    ),
)
async def test_materialize_decodes_file_url_path_once(
    tmp_path: Path,
    resources: ResourceService,
    filename: str,
) -> None:
    image = tmp_path / filename
    image.write_bytes(filename.encode())
    prepared = parse_html(f'<img src="{image.as_uri()}">')

    materialized = await materialize_local_assets(prepared, resources=resources)

    assert [asset.source for asset in materialized.assets] == [image.as_uri()]
    assert [asset.data for asset in materialized.assets] == [filename.encode()]
    assert [asset.media_type for asset in materialized.assets] == ["image/png"]


async def test_materialize_preserves_file_url_authority_limits(
    tmp_path: Path,
    resources: ResourceService,
) -> None:
    image = tmp_path / "authority.png"
    image.write_bytes(b"localhost")
    file_url = image.as_uri()
    localhost_url = file_url.replace("file://", "file://localhost", 1)
    remote_url = file_url.replace("file://", "file://assets.example", 1)

    local = await materialize_local_assets(
        parse_html(f'<img src="{localhost_url}">'),
        resources=resources,
    )
    assert local.assets[0].data == b"localhost"

    with pytest.raises(
        AssetMaterializationError,
        match="Remote file URL authorities are not supported",
    ):
        await materialize_local_assets(
            parse_html(f'<img src="{remote_url}">'),
            resources=resources,
        )


@pytest.mark.parametrize("strict", (True, False))
async def test_materialize_ignores_fragment_only_references_before_base_resolution(
    tmp_path: Path,
    resources: ResourceService,
    mocker,
    *,
    strict: bool,
) -> None:
    document_dir = tmp_path / "documents"
    declared_base = tmp_path / "declared"
    stylesheet_base = tmp_path / "stylesheets"
    document_dir.mkdir()
    declared_base.mkdir()
    stylesheet_base.mkdir()
    sprite = declared_base / "sprite.svg"
    sprite.write_bytes(b"<svg/>")
    prepared = parse_html(
        (
            f'<base href="{declared_base.as_uri()}/">'
            '<img src="#html-fragment">'
            '<svg><use href="#svg-fragment"></use>'
            '<use href="sprite.svg#icon"></use></svg>'
            "<style>.inline { fill: url(#inline-css-fragment) }</style>"
        ),
        base_url=(document_dir / "document.html").as_uri(),
        stylesheets=(
            PreparedStylesheet(
                css='.external { mask: url("#external-css-fragment") }',
                base_url=f"{stylesheet_base.as_uri()}/",
            ),
        ),
    )
    authorize_local = mocker.spy(resources, "authorize_local")
    fetch_bytes = mocker.patch.object(
        resources,
        "fetch_bytes",
        new=mocker.AsyncMock(wraps=resources.fetch_bytes),
    )

    materialized = await materialize_local_assets(
        prepared,
        resources=resources,
        strict=strict,
    )

    assert [asset.source for asset in materialized.assets] == [sprite.as_uri()]
    assert [asset.data for asset in materialized.assets] == [b"<svg/>"]
    authorize_local.assert_called_once_with(sprite.resolve())
    fetch_bytes.assert_awaited_once_with(FileResourceRef(sprite.resolve()))


async def test_worker_executor_forwards_keyword_arguments() -> None:
    def work(value: int, *, suffix: str) -> str:
        return f"{value}{suffix}"

    assert await AnyioWorkerExecutor().run_sync(work, 12, suffix="px") == "12px"


async def test_materialize_enforces_document_root(
    tmp_path: Path,
) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret")
    prepared = parse_html(
        f'<base href="{tmp_path.as_uri()}/"><img src="secret.txt">',
        base_url=(allowed / "document.html").as_uri(),
    )
    observer = NoopCacheObserver()
    worker = AnyioWorkerExecutor()
    resources = ResourceService(
        fetcher=build_resource_fetcher(
            ResourceCacheSettings(),
            observer,
            worker,
            local_access=ConfiguredLocalAccessPolicy(
                allowed_roots=(),
                allow_any=False,
            ),
            remote_transport=RemoteTransportExecutor(max_concurrent_fetches=2),
        ),
        local_access=ConfiguredLocalAccessPolicy(
            allowed_roots=(),
            allow_any=False,
        ),
        strategy=LocalResourceStrategy(),
    )
    with pytest.raises(AssetMaterializationError):
        await materialize_local_assets(prepared, resources=resources)


async def test_markdown_keeps_independent_resource_bases(
    tmp_path: Path,
    preparer: DefaultHtmlPreparer,
    resources: ResourceService,
) -> None:
    markdown_dir = tmp_path / "markdown"
    css_dir = tmp_path / "theme"
    markdown_dir.mkdir()
    css_dir.mkdir()
    markdown_path = markdown_dir / "document.md"
    image = markdown_dir / "image.png"
    css_path = css_dir / "theme.css"
    font = css_dir / "font.woff2"
    markdown_path.write_text("![image](image.png)")
    image.write_bytes(b"image")
    css_path.write_text('@font-face { src: url("font.woff2") }')
    font.write_bytes(b"font")
    prepared = await preparer.prepare_markdown(
        FileResourceRef(markdown_path),
        stylesheet=FileResourceRef(css_path),
    )
    materialized = await materialize_local_assets(prepared, resources=resources)
    assert {asset.source for asset in materialized.assets} == {
        image.as_uri(),
        font.as_uri(),
    }


async def test_strict_markdown_preparation_exposes_stable_resource_error(
    preparer: DefaultHtmlPreparer,
) -> None:
    with pytest.raises(AssetMaterializationError, match="no filesystem base"):
        await preparer.prepare_markdown(
            "![missing](missing.png)",
            materialization_policy=ResourceMaterializationPolicy.STRICT,
        )
