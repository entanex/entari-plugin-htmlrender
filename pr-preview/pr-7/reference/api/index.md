# 公开 API 参考

本页由 `mkdocstrings` 根据源码与类型标注自动生成，保证签名与代码始终一致。

- 日常业务调用优先从包根 `entari_plugin_htmlrender` 导入核心接口与值对象。
- 异常体系与常见触发场景的中文说明见[错误类型与处理](<https://entanex.github.io/entari-plugin-htmlrender/pr-preview/pr-7/reference/errors/index.md>)。

## 核心入口（`entari_plugin_htmlrender`）

### entari\_plugin\_htmlrender

Caller-first contracts and values for HTMLRender.

The package root deliberately excludes runtime composition, Provider SDK, adapter, and Entari lifecycle types. Ordinary code receives the contracts exported here through constructor or host injection.

#### CapabilityUnavailableError

Bases: `HtmlRenderError`

An optional typed capability is absent from the composition.

#### HtmlRenderError

Bases: `_DetailedError`

Root of every stable failure exposed to HTMLRender callers.

#### InvalidRenderInputError

Bases: `HtmlRenderError`

A caller supplied an invalid value for one rendering operation.

#### ProviderError

Bases: `HtmlRenderError`

Base for failures attributed to one selected render provider.

#### RenderOutputLimitError

Bases: `HtmlRenderError`

A provider result exceeded a configured output safety limit.

#### RenderTimeoutError

Bases: `HtmlRenderError`

A complete public operation exceeded its caller-visible deadline.

#### ResourceError

Bases: `HtmlRenderError`

Base for failures while fetching or publishing one resource.

#### RuntimeUnavailableError

Bases: `HtmlRenderError`

The runtime state does not admit new caller operations.

#### UnsupportedOperationError

Bases: `HtmlRenderError`

The selected composition does not implement a requested operation.

#### DocumentBase

Resolved document-base semantics carried by a prepared document.

`declared_href` is the value of an in-document `<base href>` parsed once by `parse_html`: `None` means no `<base href>` was declared, while an empty string is an explicit `<base href="">` that resolves to the document URL itself. `preparation_base_url` is the base URL the document was prepared with. `resolve` combines them with an optional execution-time fallback so every consumer derives one canonical base instead of re-parsing the markup.

#### DocumentRequirement

Bases: `StrEnum`

Execution features required by prepared content.

#### PreparedAsset

Binary resource addressable by its exact document URL.

#### PreparedHtml

Canonical HTML payload shared by browser and native renderers.

`html` always retains the original browser document. Build instances through :func:`entari_plugin_htmlrender.preparation.parse_html` — the sole place that parses the markup; `document_base` and `structure` are that parse's results and consumers never re-derive them. The resource-resolution root lives in `document_base.preparation_base_url`.

##### document\_base

```python
document_base: DocumentBase = field(kw_only=True)
```

Document-base semantics fixed at preparation time.

Consumers call `document_base.resolve(fallback_base_url=...)` instead of re-deriving the base from the markup.

##### structure

```python
structure: DocumentStructureSnapshot = field(kw_only=True)
```

Reference and insertion-point facts for the exact `html` string.

#### PreparedStylesheet

One stylesheet with its own resource-resolution base.

#### RasterOptions

Portable raster options shared by HTML-capable engines.

#### TemplateRef

Immutable locator for one filesystem template.

`root` identifies the template collection while `name` is a logical, POSIX-style name inside that collection. The reference carries no renderer, environment, filters, or other Jinja implementation state.

#### HtmlPreparer

Bases: `Protocol`

Prepare reusable HTML documents independently of a rendering provider.

#### RenderedHtml

HTML output of a template-to-html render operation.

#### RenderedImage

PNG or JPEG output with metadata derived from its encoded bytes.

The bounded inspection reads only the container metadata needed for format and dimensions; full pixel decoding remains the renderer's responsibility.

##### from\_bytes

```python
from_bytes(
    data: bytes,
    *,
    expected_format: RasterImageFormat | None = None,
) -> RenderedImage
```

Build an artifact after bounded inspection of encoded metadata.

#### HtmlRenderer

Bases: `Protocol`

Rasterize caller content without exposing provider implementation types.

#### TemplateRenderer

Bases: `Protocol`

Render one logical template into an HTML artifact.

#### RenderOperation

Bases: `StrEnum`

Stable domain identities for renderer operations.

Values describe both the input domain and output artifact. They are not coupled to Python method names, so an implementation can evolve without changing capability identity.

#### ResourceMaterializationPolicy

Bases: `StrEnum`

Whether document-local resources are resolved before execution.

#### parse\_html

```python
parse_html(
    html: str,
    *,
    base_url: str | None = None,
    stylesheets: Iterable[str | PreparedStylesheet] = (),
    assets: Iterable[PreparedAsset] = (),
) -> PreparedHtml
```

Build a canonical payload without performing backend-specific transport.

## Entari 集成（`entari_plugin_htmlrender.entari`）

### entari\_plugin\_htmlrender.entari

Explicit Entari integration surface for HTMLRender.

#### HtmlRenderConfig

Bases: `_StrictRenderModel`

Complete configuration accepted by the Entari plugin.

#### RuntimeStartupPolicy

Bases: `StrEnum`

Provider runtime initialization policy.

#### HtmlRenderService

Bases: `Service`

Concrete Entari service exposing only caller-facing render contracts.

##### launch

```python
launch(manager: Launart) -> None
```

Participate in Entari startup, blocking, and hot-unload cleanup.

## 配置模型（`entari_plugin_htmlrender.config`）

### entari\_plugin\_htmlrender.config

Framework-neutral configuration for one HTMLRender composition.

#### RuntimeStartupPolicy

Bases: `StrEnum`

Provider runtime initialization policy.

#### CacheSettings

Bases: `_StrictRenderModel`

Sizing of the shared resource cache budget.

#### TemplateSettings

Bases: `_StrictRenderModel`

Sizing of the template environment cache.

##### environment\_compiled\_cache\_size

```python
environment_compiled_cache_size: int = Field(
    default=256, ge=0
)
```

Compiled-template cache size per Jinja environment; 0 disables it.

#### ResourceTraversalSettings

Bases: `_StrictRenderModel`

Bounds for resolving nested template-variable resources.

#### LocalAccessSettings

Bases: `_StrictRenderModel`

Security policy for local filesystem resource access.

#### RemoteAccessSettings

Bases: `_StrictRenderModel`

Security policy for remote (http/https) resource fetches.

#### FilehostSettings

Bases: `_StrictRenderModel`

Core-owned settings for the optional asset publisher adapter.

##### public\_base\_url

```python
public_base_url: str | None = Field(default=None)
```

Externally reachable absolute base of the hosted asset collection.

Required whenever the selected resource strategy uses the filehost transport; deployment configuration mapped by the reverse proxy to the fixed internal mount, never derived from bind addresses, `Host` / `Forwarded` headers, or request context.

#### ObservabilitySettings

Bases: `_StrictRenderModel`

Which observability integrations this plugin exports to.

#### PythonDrawingSettings

Bases: `_StrictRenderModel`

One explicitly configured, trusted Python drawing entry point.

#### GraphicsSettings

Bases: `_StrictRenderModel`

Selection and budgets for backend-neutral graphics renderers.

#### HtmlRenderSettings

Bases: `_StrictRenderModel`

Shared limits for provider-neutral HTML raster operations.

#### ResourceSettings

Bases: `_StrictRenderModel`

Core-validated resource, cache, and security configuration.

#### HtmlRenderConfig

Bases: `_StrictRenderModel`

Complete configuration accepted by the Entari plugin.

## 资源访问（`entari_plugin_htmlrender.resources`）

### entari\_plugin\_htmlrender.resources

Curated resource-domain contract surface.

#### ResourceMaterializationPolicy

Bases: `StrEnum`

Whether document-local resources are resolved before execution.

#### ResourceAccessDeniedError

Bases: `ResourceError`

Policy or remote authorization denied access to the resource.

#### ResourceAuthenticationError

Bases: `ResourceRemoteResponseError`

A remote server rejected the request's authentication or authority.

#### ResourceError

Bases: `HtmlRenderError`

Base for failures while fetching or publishing one resource.

#### ResourceFetchError

Bases: `ResourceError`

A file or network transport failed to fetch resource content.

#### ResourceNetworkError

Bases: `ResourceFetchError`

Name resolution, connection, or TLS transport failed.

#### ResourceNotFoundError

Bases: `ResourceError`

The referenced resource does not exist.

#### ResourcePublishError

Bases: `ResourceError`

A publication transport failed to expose resource content.

#### ResourceRemoteResponseError

Bases: `ResourceFetchError`

A remote server returned a final HTTP response that was not usable.

#### ResourceTimeoutError

Bases: `ResourceFetchError`

A resource operation exceeded its end-to-end deadline.

#### ResourceTooLargeError

Bases: `ResourceError`

A resource exceeded an explicit byte limit.

#### InlineResource

Caller-owned bytes that need no source lookup.

Inline data is deliberately not a :class:`ResourceRef`: references locate content, while this value already *is* content. Keeping it outside the locator union prevents caches and access policies from pretending that an in-memory payload has a filesystem or network identity.

#### PublishedResource

A published asset URL bundled with the exact request authorization.

`request_headers` are the headers a consumer must send to fetch this specific URL. The authorization travels with the URL so callers never infer it from host, path prefix or network location. Both the URL and headers are valid only while the `ResourceAccess.publish()` context that yielded this value remains open.

#### ResourceContent

One immutable resource snapshot.

##### final\_url

```python
final_url: str | None = None
```

Final HTTP URL when a fetch followed a redirect; otherwise `None`.

#### ResourceResolution

Bases: `Generic[T]`

A resolved value with exact request authorization for rewritten URLs.

`request_headers_by_url` is keyed by the final HTTP request URL, without a fragment and with its query preserved. Consumers must apply each header set only to that exact URL, rather than inferring access from the host or a path prefix.

#### ResourceRevision

Opaque source revision used by caching readers.

#### ResourceAccess

Bases: `Protocol`

Caller contract for resource access and explicit local staging.

#### ResourceFetcher

Bases: `Protocol`

Fetch content for explicit resource locators.

This source-side port does not accept :class:`InlineResource`, because an inline payload has no source to fetch or revalidate.

##### fetch\_if\_changed

```python
fetch_if_changed(
    reference: ResourceRef, revision: ResourceRevision
) -> ResourceContent | NotModified
```

Fetch only when the source moved past `revision`.

The caller supplies the revision it already holds; the reader maps it to a source-native conditional read (`If-None-Match` / `If-Modified-Since` for HTTP, a stat compare for files) and returns :class:`NotModified` when the cached bytes are still current. Fetchers keep no validator state of their own.

#### ResourceMaterializer

Bases: `Protocol`

Asynchronously materialize one document-local value.

## Python 绘图（`entari_plugin_htmlrender.graphics`）

### entari\_plugin\_htmlrender.graphics

Backend-neutral raster-scene values and rendering contract.

#### DrawingLoadError

Bases: `GraphicsError`

A configured drawing source could not be loaded or validated.

#### DrawingNotFoundError

Bases: `GraphicsError`

A drawing name is absent from the configured registry.

#### DrawingCanvas

Physical-pixel dimensions and background for one native draw call.

#### DrawingRenderer

Bases: `Protocol`

Render a configured Python drawing using a fresh native canvas.

#### DrawingBackendExecutionError

Bases: `GraphicsError`

A backend-native Python drawing failed during draw or encoding.

#### GraphicsBackendUnavailableError

Bases: `GraphicsError`

The selected in-process graphics backend cannot run.

#### GraphicsError

Bases: `HtmlRenderError`

Base for failures attributed to one configured graphics backend.

#### RasterBackendExecutionError

Bases: `GraphicsError`

A raster-scene backend failed without leaking a native exception type.

#### FillRect

Paint one rectangle using conceptual Porter-Duff source-over.

Native backends control their 8-bit premultiplication and quantization. Cross-backend encoded bytes and exact channel values are not equivalent output contracts.

#### PixelRect

Half-open, integer-pixel rectangle that may extend beyond a scene.

##### clipped\_to

```python
clipped_to(width: int, height: int) -> PixelRect | None
```

Intersect this rectangle with a canvas using half-open bounds.

#### RasterEncodeOptions

Backend-neutral PNG/JPEG encoding semantics for a raster scene.

JPEG first composites the complete RGBA scene source-over onto the opaque matte. `quality` is the common encoder input, not a promise that native encoders produce equivalent compression or bytes.

##### jpeg\_quality

```python
jpeg_quality: int
```

Resolve the common JPEG encoder input used by every adapter.

##### jpeg\_matte

```python
jpeg_matte: RGBAColor
```

Resolve the opaque destination beneath the complete RGBA scene.

#### RasterScene

Physical-pixel scene shared by raster drawing backends.

Commands execute in tuple order, clip to the canvas, and use conceptual source-over composition over 8-bit sRGB inputs. Native premultiplication, channel quantization, and encoders may differ, so scenes do not promise byte-for-byte or pixel-identical output across backends. The first contract intentionally contains only solid, integer-aligned rectangles: it does not pretend to provide HTML layout, text shaping, or backend-native transport.

#### RGBAColor

Straight-alpha, 8-bit sRGB input color.

Adapters may use premultiplied native storage. RGB channels are not observable when alpha is zero and need not survive an encode round trip.

#### GraphicsRenderer

Bases: `Protocol`

Rasterize neutral physical-pixel scenes without exposing backend selection.

## 独立组装（`entari_plugin_htmlrender.composition`）

### entari\_plugin\_htmlrender.composition

Framework-neutral composition root for one complete render runtime.

#### RuntimePlan

Immutable inputs from which the host builds one isolated runtime graph.

##### build\_runtime

```python
build_runtime(
    *,
    drawing_registry_factory: DrawingRegistryFactory
    | None = None,
) -> RenderRuntime
```

Consume this plan to build one graph without external I/O.

#### build\_runtime\_plan

```python
build_runtime_plan(
    config: HtmlRenderConfig,
    *,
    provider_override: RenderProvider[Any] | None = None,
) -> RuntimePlan
```

Resolve and validate only the selected Provider; perform no runtime I/O.

## Provider SDK（`entari_plugin_htmlrender.providers.sdk`）

### entari\_plugin\_htmlrender.providers.sdk

Provider SDK: stable contracts for render-provider composition.

A provider is loaded either from an explicit composition-root override or from the versioned `entari_plugin_htmlrender.providers.v2` entry-point group. Raw mappings cross the boundary once through :meth:`RenderProvider.parse_config`; the resulting provider-owned value flows unchanged through availability, resource planning, and composition.

#### LocalResourceStrategy

Resource transport for a provider running in this process.

#### RemoteResourceStrategy

Resource transport for a provider running across a process boundary.

#### ProviderAvailable

The provider can run with the parsed configuration.

#### ProviderUnavailable

The provider cannot currently run with the parsed configuration.

#### ProviderDependencies

Services the composition root hands to `RenderProvider.compose`.

Providers never read global configuration or construct their own observers; everything they need arrives here.

#### ProviderBinding

Immutable composition value produced by `RenderProvider.compose`.

Only the composition root consumes this; caller code receives the contained lifecycle and executor through constructor injection.

#### RenderProvider

Bases: `Protocol[ConfigT]`

A discoverable implementation of HTML rendering operations.

#### validate\_provider\_id

```python
validate_provider_id(value: object) -> ProviderId
```

Validate the stable identifier shared by config and entry points.
