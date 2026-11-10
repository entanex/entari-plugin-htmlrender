"""ResourceService caller, preparation, and scoped-publication contracts."""

from __future__ import annotations

from inspect import signature
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, cast, get_type_hints
from urllib.parse import quote, urlsplit, urlunsplit

import anyio
import anyio.lowlevel
import pytest

from entari_plugin_htmlrender.adapters.resources import ConfiguredLocalAccessPolicy
from entari_plugin_htmlrender.errors import (
    InvalidRenderInputError,
    ResourceAccessDeniedError,
    ResourceError,
    ResourceFetchError,
    ResourceNotFoundError,
    ResourcePublishError,
)
from entari_plugin_htmlrender.resources._traversal import ResourceTraversalBudget
from entari_plugin_htmlrender.resources.config import (
    LocalResourceStrategy,
    RemoteLocalResourcePolicy,
    RemoteResourceStrategy,
    ResourceMaterializationPolicy,
)
from entari_plugin_htmlrender.resources.models import (
    FileResourceRef,
    InlineResource,
    NotModified,
    PublicationLeaseId,
    PublishedResource,
    ResourceContent,
    ResourceRef,
    ResourceResolution,
    ResourceRevision,
)
from entari_plugin_htmlrender.resources.ports import (
    AssetPublisher,
    PreparationResourceAccess,
    ProviderResourceAccess,
    ResourceAccess,
    ResourceFetcher,
    ResourceMaterializer,
)
from entari_plugin_htmlrender.resources.service import ResourceService

if TYPE_CHECKING:
    from collections.abc import Mapping


class RecordingFetcher:
    def __init__(self, content: ResourceContent) -> None:
        self.content = content
        self.fetches: list[tuple[ResourceRef, bool]] = []
        self.invalidated: list[ResourceRef] = []
        self.clear_calls = 0

    async def fetch(
        self,
        reference: ResourceRef,
        *,
        refresh: bool = False,
    ) -> ResourceContent:
        self.fetches.append((reference, refresh))
        return self.content

    async def fetch_if_changed(
        self,
        reference: ResourceRef,
        revision: ResourceRevision,
    ) -> ResourceContent | NotModified:
        if self.content.revision == revision:
            return NotModified(revision)
        return await self.fetch(reference)

    async def fetch_revision(
        self,
        reference: ResourceRef,
    ) -> ResourceRevision | None:
        del reference
        return self.content.revision

    async def invalidate(self, reference: ResourceRef) -> None:
        self.invalidated.append(reference)

    async def clear(self) -> None:
        self.clear_calls += 1


class FailingFetcher(RecordingFetcher):
    async def fetch(
        self,
        reference: ResourceRef,
        *,
        refresh: bool = False,
    ) -> ResourceContent:
        del reference, refresh
        raise RuntimeError("custom fetcher failed")


class RecordingPublisher:
    def __init__(self) -> None:
        self.headers = {"X-Test-Asset": "token"}
        self.published: list[
            tuple[
                ResourceContent | InlineResource,
                PublicationLeaseId | None,
                str | None,
            ]
        ] = []
        self.released: list[PublicationLeaseId] = []
        self.release_started = anyio.Event()
        self.release_finished = False
        self.publish_error: Exception | None = None
        self.release_error: Exception | None = None
        self._next_lease = 0

    def create_lease(self) -> PublicationLeaseId:
        self._next_lease += 1
        return PublicationLeaseId(f"lease:{self._next_lease}")

    async def release(self, lease_id: PublicationLeaseId) -> None:
        self.release_started.set()
        await anyio.lowlevel.checkpoint()
        if self.release_error is not None:
            raise self.release_error
        self.released.append(lease_id)
        self.release_finished = True

    async def publish(
        self,
        content: ResourceContent | InlineResource,
        *,
        lease_id: PublicationLeaseId | None = None,
        suffix: str | None = None,
    ) -> PublishedResource:
        self.published.append((content, lease_id, suffix))
        if self.publish_error is not None:
            raise self.publish_error
        return PublishedResource(
            url="https://assets.example/resource",
            request_headers=self.headers,
        )

    async def startup(self) -> None:
        return None

    async def clear(self) -> None:
        return None

    async def aclose(self) -> None:
        return None


class ConcurrentMaterializer:
    def __init__(self) -> None:
        self.active = 0
        self.calls = 0
        self.max_active = 0
        self._lock = anyio.Lock()

    async def materialize(
        self,
        value: object,
        *,
        template_base: Path | None = None,
    ) -> object:
        del template_base
        async with self._lock:
            self.calls += 1
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        await anyio.sleep(0.01)
        async with self._lock:
            self.active -= 1
        if isinstance(value, Path):
            return f"materialized:{value.name}"
        return value


class FailingMaterializer:
    async def materialize(
        self,
        value: object,
        *,
        template_base: Path | None = None,
    ) -> object:
        del value, template_base
        raise RuntimeError("materializer unavailable")


class ExceptionMaterializer:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def materialize(
        self,
        value: object,
        *,
        template_base: Path | None = None,
    ) -> object:
        del value, template_base
        raise self.error


def _service(
    tmp_path: Path,
    *,
    fetcher: ResourceFetcher | None = None,
    publisher: RecordingPublisher | None = None,
    traversal_budget: ResourceTraversalBudget | None = None,
    strategy: LocalResourceStrategy | RemoteResourceStrategy | None = None,
) -> ResourceService:
    return ResourceService(
        fetcher=fetcher or RecordingFetcher(ResourceContent(b"value")),
        local_access=ConfiguredLocalAccessPolicy(
            allowed_roots=(tmp_path,),
            allow_any=False,
        ),
        strategy=strategy or LocalResourceStrategy(),
        publisher=publisher,
        traversal_budget=traversal_budget,
    )


@pytest.mark.anyio
async def test_fetch_contract_accepts_locators_and_forwards_refresh(
    tmp_path: Path,
) -> None:
    reference = FileResourceRef(tmp_path / "resource.txt")
    content = ResourceContent(
        b"value",
        "text/plain",
        ResourceRevision("revision"),
    )
    fetcher = RecordingFetcher(content)
    resources = _service(tmp_path, fetcher=fetcher)

    assert await resources.fetch(reference, refresh=True) is content
    assert await resources.fetch_bytes(reference) == b"value"
    assert await resources.fetch_text(reference) == "value"
    await resources.clear()

    assert fetcher.fetches == [
        (reference, True),
        (reference, False),
        (reference, False),
    ]
    assert fetcher.clear_calls == 1


@pytest.mark.anyio
async def test_fetch_translates_custom_fetcher_failures(
    tmp_path: Path,
) -> None:
    reference = FileResourceRef(tmp_path / "resource.txt")
    resources = _service(
        tmp_path,
        fetcher=FailingFetcher(ResourceContent(b"unused")),
    )

    with pytest.raises(ResourceFetchError) as captured:
        await resources.fetch(reference)

    assert captured.value.reference == reference
    assert captured.value.operation == "fetch"
    assert captured.value.retryable is False
    assert captured.value.causes[0].exception_type == "RuntimeError"


@pytest.mark.anyio
@pytest.mark.parametrize("refresh", [1, "false", None])
async def test_fetch_rejects_non_boolean_refresh(
    tmp_path: Path,
    refresh: object,
) -> None:
    resources = _service(tmp_path)

    with pytest.raises(InvalidRenderInputError) as captured:
        await resources.fetch(
            FileResourceRef(tmp_path / "resource.txt"),
            refresh=cast("bool", refresh),
        )

    assert captured.value.operation == "fetch"
    assert captured.value.field == "refresh"


@pytest.mark.anyio
async def test_fetch_text_maps_decode_failure_to_structured_error(
    tmp_path: Path,
) -> None:
    reference = FileResourceRef(tmp_path / "resource.bin")
    resources = _service(
        tmp_path,
        fetcher=RecordingFetcher(ResourceContent(b"\xff")),
    )

    with pytest.raises(ResourceFetchError) as captured:
        await resources.fetch_text(reference)

    assert captured.value.reference == reference
    assert captured.value.operation == "fetch_text"
    assert captured.value.retryable is False


@pytest.mark.anyio
async def test_caller_resource_methods_reject_crossed_domain_values(
    tmp_path: Path,
) -> None:
    publisher = RecordingPublisher()
    resources = _service(tmp_path, publisher=publisher)

    with pytest.raises(InvalidRenderInputError) as fetch_error:
        await resources.fetch(cast("ResourceRef", InlineResource(b"value")))
    assert fetch_error.value.operation == "fetch"
    assert fetch_error.value.field == "resource"

    with pytest.raises(InvalidRenderInputError) as publish_error:
        async with resources.publish(
            cast("InlineResource", FileResourceRef(tmp_path / "value.bin"))
        ):
            raise AssertionError("unreachable")
    assert publish_error.value.operation == "publish"
    assert publish_error.value.field == "content"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "suffix",
    [
        "",
        ".",
        "..",
        "/css",
        "a/b",
        "a\\b",
        "css\n",
        f".{('a' * 33)}",
    ],
)
async def test_publish_rejects_unsafe_suffix_at_caller_boundary(
    tmp_path: Path,
    suffix: str,
) -> None:
    publisher = RecordingPublisher()
    resources = _service(tmp_path, publisher=publisher)

    with pytest.raises(InvalidRenderInputError) as captured:
        async with resources.publish(InlineResource(b"value"), suffix=suffix):
            raise AssertionError("unreachable")

    assert captured.value.operation == "publish"
    assert captured.value.field == "suffix"
    assert publisher.published == []
    assert publisher.released == []


@pytest.mark.anyio
async def test_publish_canonicalizes_suffix_before_transport(tmp_path: Path) -> None:
    publisher = RecordingPublisher()
    resources = _service(tmp_path, publisher=publisher)

    async with resources.publish(InlineResource(b"value"), suffix="CSS"):
        pass

    assert publisher.published[0][2] == ".css"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("encoding", "missing-codec"),
        ("errors", "missing-handler"),
    ],
)
async def test_fetch_text_rejects_unknown_codec_configuration(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    resources = _service(tmp_path)
    reference = FileResourceRef(tmp_path / "resource.txt")

    with pytest.raises(InvalidRenderInputError) as captured:
        if field == "encoding":
            await resources.fetch_text(reference, encoding=value)
        else:
            await resources.fetch_text(reference, errors=value)

    assert captured.value.operation == "fetch_text"
    assert captured.value.field == field


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("field", "encoding", "errors"),
    [
        ("encoding", "", "strict"),
        ("encoding", 1, "strict"),
        ("errors", "utf-8", ""),
        ("errors", "utf-8", 1),
    ],
)
async def test_fetch_text_rejects_empty_or_non_text_codec_configuration(
    tmp_path: Path,
    field: str,
    encoding: object,
    errors: object,
) -> None:
    resources = _service(tmp_path)

    with pytest.raises(InvalidRenderInputError) as captured:
        await resources.fetch_text(
            FileResourceRef(tmp_path / "resource.txt"),
            encoding=cast("str", encoding),
            errors=cast("str", errors),
        )

    assert captured.value.operation == "fetch_text"
    assert captured.value.field == field


@pytest.mark.anyio
async def test_publish_is_scoped_and_returns_atomic_immutable_identity(
    tmp_path: Path,
) -> None:
    publisher = RecordingPublisher()
    resources = _service(tmp_path, publisher=publisher)
    content = InlineResource(b"body{}", "text/css")

    async with resources.publish(content, suffix=".css") as published:
        assert published.url == "https://assets.example/resource"
        assert dict(published.request_headers) == {"X-Test-Asset": "token"}
        assert publisher.released == []
        publisher.headers["X-Test-Asset"] = "changed"
        assert published.request_headers["X-Test-Asset"] == "token"
        with pytest.raises(TypeError):
            cast("dict[str, str]", published.request_headers)["X-Test-Asset"] = (
                "changed"
            )

    assert len(publisher.published) == 1
    assert publisher.published[0][0] is content
    assert publisher.published[0][2] == ".css"
    assert publisher.released == [publisher.published[0][1]]


@pytest.mark.anyio
async def test_publish_releases_lease_under_cancellation(tmp_path: Path) -> None:
    publisher = RecordingPublisher()
    resources = _service(tmp_path, publisher=publisher)

    with anyio.CancelScope() as scope:
        async with resources.publish(InlineResource(b"value")):
            scope.cancel()
            await anyio.sleep_forever()

    assert publisher.release_started.is_set()
    assert publisher.release_finished is True
    assert len(publisher.released) == 1


@pytest.mark.anyio
async def test_publish_groups_body_and_release_failures(tmp_path: Path) -> None:
    publisher = RecordingPublisher()
    publisher.release_error = RuntimeError("release failed")
    resources = _service(tmp_path, publisher=publisher)

    with pytest.raises(BaseExceptionGroup) as captured:
        async with resources.publish(InlineResource(b"value")):
            raise ValueError("body failed")

    assert len(captured.value.exceptions) == 2
    assert isinstance(captured.value.exceptions[0], ValueError)
    release_error = captured.value.exceptions[1]
    assert isinstance(release_error, ResourcePublishError)
    assert release_error.operation == "publish"


@pytest.mark.anyio
async def test_publish_failure_is_structured_and_still_releases(
    tmp_path: Path,
) -> None:
    publisher = RecordingPublisher()
    publisher.publish_error = RuntimeError("upload failed")
    resources = _service(tmp_path, publisher=publisher)

    with pytest.raises(ResourcePublishError, match="upload failed") as captured:
        async with resources.publish(InlineResource(b"value")):
            raise AssertionError("unreachable")

    assert captured.value.operation == "publish"
    assert len(publisher.released) == 1


@pytest.mark.anyio
async def test_publish_surfaces_release_failure_after_successful_scope(
    tmp_path: Path,
) -> None:
    publisher = RecordingPublisher()
    publisher.release_error = RuntimeError("release failed")
    resources = _service(tmp_path, publisher=publisher)

    with pytest.raises(ResourcePublishError, match="release failed") as captured:
        async with resources.publish(InlineResource(b"value")):
            pass

    assert captured.value.operation == "publish"
    assert publisher.release_started.is_set()


@pytest.mark.anyio
async def test_publish_requires_an_injected_transport(tmp_path: Path) -> None:
    resources = _service(tmp_path)

    with pytest.raises(ResourcePublishError) as captured:
        async with resources.publish(InlineResource(b"value")):
            raise AssertionError("unreachable")

    assert captured.value.operation == "publish"


@pytest.mark.anyio
async def test_preparation_materializer_is_bounded_and_recursive(
    tmp_path: Path,
) -> None:
    materializer = ConcurrentMaterializer()
    resources = _service(
        tmp_path,
        traversal_budget=ResourceTraversalBudget(max_concurrency=2),
    )
    paths = [tmp_path / f"{index}.bin" for index in range(6)]

    result = await resources.materialize_template_variables(
        {"paths": paths, "plain": "caption"},
        materializer=materializer,
        strict=True,
        template_base=tmp_path,
    )

    assert result == {
        "paths": [f"materialized:{index}.bin" for index in range(6)],
        "plain": "caption",
    }
    assert materializer.calls == len(paths)
    assert materializer.max_active == 2


@pytest.mark.anyio
async def test_public_resource_resolution_preserves_exact_filehost_headers(
    tmp_path: Path,
) -> None:
    publisher = RecordingPublisher()
    resources = _service(
        tmp_path,
        publisher=publisher,
        strategy=RemoteResourceStrategy(
            local_resource_policy=RemoteLocalResourcePolicy.FILEHOST
        ),
    )
    asset = tmp_path / "asset.png"

    variables = await resources.resolve_template_vars(
        {
            "nested": {"path": asset, "data": b"image"},
            "plain": "caption",
        },
        template_base=tmp_path,
        strict=True,
    )
    single = await resources.to_resource_url(asset, strict=True)
    tokens = await resources.resolve_url_tokens(
        ["asset.css?theme=dark#icon", "https://cdn.example/base.css", "#local"],
        template_base=tmp_path,
        strict=True,
    )

    assert isinstance(variables, ResourceResolution)
    assert variables.value == {
        "nested": {
            "path": "https://assets.example/resource",
            "data": "https://assets.example/resource",
        },
        "plain": "caption",
    }
    assert variables.request_headers_by_url == {
        "https://assets.example/resource": {"X-Test-Asset": "token"}
    }
    assert single.value == "https://assets.example/resource"
    assert single.request_headers_by_url == variables.request_headers_by_url
    assert tokens.value == [
        "https://assets.example/resource?theme=dark#icon",
        "https://cdn.example/base.css",
        "#local",
    ]
    assert tokens.request_headers_by_url == {
        "https://assets.example/resource?theme=dark": {"X-Test-Asset": "token"}
    }
    assert publisher.published
    assert all(lease_id is None for _, lease_id, _ in publisher.published)


@pytest.mark.anyio
async def test_public_template_resolution_honors_disabled_mode_and_override(
    tmp_path: Path,
) -> None:
    asset = tmp_path / "asset.bin"
    resources = _service(
        tmp_path,
        strategy=LocalResourceStrategy(
            materialization_policy=ResourceMaterializationPolicy.OFF
        ),
    )
    values = {"asset": asset}

    disabled = await resources.resolve_template_vars(values)
    overridden = await resources.resolve_template_vars(
        values,
        materializer="file",
        strict=True,
    )

    assert disabled.value == values
    assert disabled.request_headers_by_url == {}
    assert overridden.value == {"asset": asset.as_uri()}
    assert overridden.request_headers_by_url == {}


def test_resource_resolution_headers_are_deeply_immutable_and_validated() -> None:
    result = ResourceResolution(
        {"url": "https://assets.example/item"},
        {"https://assets.example/item": {"X-Test": "value"}},
    )

    with pytest.raises(TypeError):
        cast("dict[str, object]", result.request_headers_by_url)["new"] = {}
    with pytest.raises(TypeError):
        cast(
            "dict[str, str]",
            result.request_headers_by_url["https://assets.example/item"],
        )["X-Test"] = "changed"
    with pytest.raises(InvalidRenderInputError) as captured:
        ResourceResolution("value", {"relative-url": {}})

    assert captured.value.operation == "create_resource_resolution"
    assert captured.value.field == "request_headers_by_url"
    for fragment in ("#", "#fragment"):
        with pytest.raises(InvalidRenderInputError):
            ResourceResolution(
                "value", {f"https://assets.example/item?variant=1{fragment}": {}}
            )


@pytest.mark.anyio
@pytest.mark.parametrize("materializer", ["unknown", object()])
async def test_empty_resolution_validates_materializer(
    tmp_path: Path, materializer: object
) -> None:
    resources = _service(tmp_path)
    invalid = cast("ResourceMaterializer", materializer)
    with pytest.raises(InvalidRenderInputError) as template_error:
        await resources.resolve_template_vars({}, materializer=invalid)
    with pytest.raises(InvalidRenderInputError) as token_error:
        await resources.resolve_url_tokens([], materializer=invalid)
    with pytest.raises(InvalidRenderInputError) as url_error:
        await resources.to_resource_url("https://example.com", materializer=invalid)
    assert template_error.value.field == token_error.value.field == "materializer"
    assert url_error.value.field == "materializer"


@pytest.mark.anyio
async def test_url_token_budget_fails_before_publication(tmp_path: Path) -> None:
    publisher = RecordingPublisher()
    resources = _service(
        tmp_path,
        publisher=publisher,
        traversal_budget=ResourceTraversalBudget(max_nodes=3),
    )
    with pytest.raises(InvalidRenderInputError, match="node budget"):
        await resources.resolve_url_tokens(
            ["a.png", "b.png", "c.png"], materializer="filehost"
        )
    assert not publisher.published
    result = await resources.resolve_url_tokens(["#one", "#two"])
    assert result.value == ["#one", "#two"]


def test_public_resource_resolvers_do_not_expose_publisher_leases() -> None:
    for owner in (
        ResourceAccess.resolve_template_vars,
        ResourceAccess.to_resource_url,
        ResourceAccess.resolve_url_tokens,
        ResourceService.resolve_template_vars,
        ResourceService.to_resource_url,
        ResourceService.resolve_url_tokens,
    ):
        assert "lease_id" not in signature(owner).parameters


@pytest.mark.anyio
async def test_preparation_materializer_strictness_is_explicit(
    tmp_path: Path,
) -> None:
    resources = _service(tmp_path)
    asset = tmp_path / "asset.bin"

    assert await resources.materialize_template_variables(
        {"asset": asset},
        materializer=FailingMaterializer(),
        strict=False,
        template_base=tmp_path,
    ) == {"asset": asset}
    with pytest.raises(ResourceFetchError, match="materializer unavailable"):
        await resources.materialize_template_variables(
            {"asset": asset},
            materializer=FailingMaterializer(),
            strict=True,
            template_base=tmp_path,
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "expected_error"),
    [
        (FileNotFoundError("missing"), ResourceNotFoundError),
        (PermissionError("denied"), ResourceAccessDeniedError),
    ],
)
async def test_strict_materialization_normalizes_filesystem_failures(
    tmp_path: Path,
    error: Exception,
    expected_error: type[ResourceError],
) -> None:
    resources = _service(tmp_path)

    with pytest.raises(expected_error) as captured:
        await resources._materialize_resource_url(
            tmp_path / "asset.bin",
            materializer=ExceptionMaterializer(error),
            strict=True,
        )

    assert captured.value.operation == "materialize"


@pytest.mark.anyio
async def test_materialization_policy_rejects_unknown_and_disabled_transports(
    tmp_path: Path,
) -> None:
    resources = _service(tmp_path)
    asset = tmp_path / "asset.bin"

    with pytest.raises(InvalidRenderInputError) as unknown:
        await resources._materialize_resource_url(
            asset,
            materializer="missing",
            strict=True,
        )
    assert unknown.value.field == "materializer"

    with pytest.raises(InvalidRenderInputError) as invalid:
        await resources._materialize_resource_url(
            asset,
            materializer=cast("ResourceMaterializer", object()),
            strict=True,
        )
    assert invalid.value.field == "materializer"

    disabled = ResourceService(
        fetcher=RecordingFetcher(ResourceContent(b"value")),
        local_access=ConfiguredLocalAccessPolicy(
            allowed_roots=(tmp_path,),
            allow_any=False,
        ),
        strategy=RemoteResourceStrategy(
            local_resource_policy=RemoteLocalResourcePolicy.ERROR
        ),
    )
    with pytest.raises(ResourceAccessDeniedError):
        await disabled._materialize_resource_url(asset)


@pytest.mark.anyio
async def test_filehost_materialization_normalizes_binary_payloads(
    tmp_path: Path,
) -> None:
    publisher = RecordingPublisher()
    resources = _service(tmp_path, publisher=publisher)
    lease_id = PublicationLeaseId("lease:binary")

    for value in (b"bytes", bytearray(b"bytearray"), BytesIO(b"stream")):
        result = await resources._materialize_template_vars(
            {"asset": value},
            materializer="filehost",
            strict=True,
            lease_id=lease_id,
        )
        assert result.value == {"asset": "https://assets.example/resource"}

    payloads = [cast("InlineResource", call[0]).data for call in publisher.published]
    assert payloads == [b"bytes", b"bytearray", b"stream"]
    assert all(call[1] == lease_id for call in publisher.published)


@pytest.mark.anyio
async def test_filehost_url_tokens_preserve_query_fragment_and_authorization(
    tmp_path: Path,
) -> None:
    publisher = RecordingPublisher()
    resources = _service(tmp_path, publisher=publisher)
    lease_id = PublicationLeaseId("lease:tokens")

    result = await resources._materialize_url_tokens(
        [
            "asset.css?theme=dark#icon",
            "https://cdn.example/base.css",
            "data:text/plain,ready",
            "#local-fragment",
        ],
        template_base=tmp_path,
        materializer="filehost",
        strict=True,
        lease_id=lease_id,
    )

    rewritten = "https://assets.example/resource?theme=dark#icon"
    assert result.value == [
        rewritten,
        "https://cdn.example/base.css",
        "data:text/plain,ready",
        "#local-fragment",
    ]
    request_parts = urlsplit(rewritten)
    normalized_request = urlunsplit(
        (
            request_parts.scheme,
            request_parts.netloc,
            request_parts.path,
            request_parts.query,
            "",
        )
    )
    assert normalized_request == "https://assets.example/resource?theme=dark"
    assert result.request_headers_by_url == {
        normalized_request: {"X-Test-Asset": "token"}
    }
    assert publisher.published[0][1] == lease_id


@pytest.mark.anyio
async def test_url_tokens_percent_decode_utf8_and_spaces_before_materialization(
    tmp_path: Path,
) -> None:
    resources = _service(tmp_path)
    paths = (tmp_path / "logo one.png", tmp_path / "图片 图.png")
    for path in paths:
        path.write_bytes(b"asset")

    result = await resources.resolve_url_tokens(
        ["logo%20one.png", "%E5%9B%BE%E7%89%87%20%E5%9B%BE.png"],
        template_base=tmp_path,
        strict=True,
    )

    assert result.value == [path.as_uri() for path in paths]
    assert result.request_headers_by_url == {}


@pytest.mark.anyio
async def test_url_tokens_reject_encoded_path_escape_after_decoding(
    tmp_path: Path,
) -> None:
    resources = _service(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside.png"
    outside.write_bytes(b"outside")
    token = quote(f"../{outside.name}", safe="")

    with pytest.raises(ResourceAccessDeniedError) as captured:
        await resources.resolve_url_tokens(
            [token],
            template_base=tmp_path,
            strict=True,
        )

    assert captured.value.operation == "authorize"


@pytest.mark.anyio
async def test_url_tokens_reject_invalid_utf8_path_escape(tmp_path: Path) -> None:
    resources = _service(tmp_path)

    with pytest.raises(ResourceFetchError) as captured:
        await resources.resolve_url_tokens(
            ["asset-%FF.svg"],
            template_base=tmp_path,
            strict=True,
        )

    assert captured.value.operation == "materialize"


@pytest.mark.anyio
async def test_preparation_rejects_cycles_before_materializer_io(
    tmp_path: Path,
) -> None:
    materializer = ConcurrentMaterializer()
    resources = _service(tmp_path)
    cyclic: list[object] = []
    cyclic.append(cyclic)

    with pytest.raises(InvalidRenderInputError) as captured:
        await resources.materialize_template_variables(
            {"cycle": cyclic},
            materializer=materializer,
            strict=True,
            template_base=tmp_path,
        )

    assert captured.value.operation == "materialize"
    assert captured.value.field == "template_vars"
    assert materializer.calls == 0


@pytest.mark.parametrize(
    "owner",
    [
        ResourceFetcher.fetch,
        ResourceFetcher.fetch_if_changed,
        AssetPublisher.publish,
        AssetPublisher.release,
        ProviderResourceAccess.fetch_bytes,
        ResourceMaterializer.materialize,
        ResourceAccess.fetch,
        ResourceAccess.publish,
        ResourceAccess.resolve_template_vars,
        ResourceAccess.to_resource_url,
        ResourceAccess.resolve_url_tokens,
        PreparationResourceAccess.materialize_template_variables,
        PublishedResource,
    ],
)
def test_resource_contract_type_hints_are_runtime_resolvable(owner: object) -> None:
    hints: Mapping[str, object] = get_type_hints(owner)

    assert hints


def test_fetch_and_publish_keep_locator_payload_boundary_explicit() -> None:
    assert get_type_hints(ResourceAccess.fetch)["resource"] == ResourceRef
    assert get_type_hints(ResourceAccess.fetch_bytes)["resource"] == ResourceRef
    assert get_type_hints(ResourceAccess.fetch_text)["resource"] == ResourceRef
    assert get_type_hints(ProviderResourceAccess.fetch_bytes)["resource"] == (
        ResourceRef
    )
    assert get_type_hints(ResourceAccess.publish)["content"] == (
        ResourceContent | InlineResource
    )
    assert (
        get_type_hints(ResourceAccess.resolve_template_vars)["return"]
        == (ResourceResolution[dict[str, object]])
    )
    assert (
        get_type_hints(ResourceAccess.to_resource_url)["return"]
        == (ResourceResolution[str])
    )
    assert (
        get_type_hints(ResourceAccess.resolve_url_tokens)["return"]
        == (ResourceResolution[list[str]])
    )
