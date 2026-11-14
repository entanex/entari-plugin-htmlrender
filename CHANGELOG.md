# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and versioning follows the [release policy](docs/project/release.md).

<!-- insertion marker -->
## [v0.2.0](https://github.com/entanex/entari-plugin-htmlrender/releases/tag/v0.2.0) - Unreleased

<small>[Compare with v0.1.0](https://github.com/entanex/entari-plugin-htmlrender/compare/v0.1.0...v0.2.0)</small>

### Added

- expose managed `cache_font`, `cached_fonts`, `unregister_font`, and `clear_fonts` through `TakumiAPI`, and support `unicode_range` in both capability leases and configured fonts.
- render named Python drawing functions through `DrawingRenderer` and `graphics.drawings`, with native Pillow/Skia canvases and optional source reload.
- load standalone drawing sources in isolated module generations, and use Entari's plugin system for canonical imports, shared helpers, dependency reloads, and drawing lifecycle ownership.
- add the plugin-scoped `HtmlPreparer` caller contract through `service.preparation`, with explicit `prepare_html`, `prepare_text`, `prepare_markdown`, and `prepare_template` stages feeding `rasterize_prepared()`.
- expose complete managed Takumi compile, measure, SVG, node, animation, frame, and font operations through `lease_api()`, with lease and compiled-document ownership guards.
- support simultaneous Pillow and Skia backends with typed capabilities and independent budgets.
- expose independent template-variable and URL resolution with immutable, exact URL authorization mappings.
- forward custom Jinja filters and extensions through template rendering and preparation.
- inject `HtmlRenderer`, `TemplateRenderer`, `HtmlPreparer`, `ResourceAccess`, `GraphicsRenderer`, and `DrawingRenderer` directly in Entari handlers and refresh them with the plugin lifecycle.

### Changed

- pin the optional Takumi backend to the published `takumi-py==0.4.0`, with Takumi 2.17 rendering behavior and removal of upstream's deprecated resource APIs.
- expose native resource and font-cache budgets through `provider_config.cache_max_bytes` and `provider_config.font_cache_max_bytes`. `null` retains upstream defaults: 64 MiB for resource caching and no limit for the evictable font cache.
- register font subsets under a shared `name` with inclusive `unicode_range` codepoint pairs. Existing `subset_of` configuration remains compatible and takes precedence over `name`.
- retain separate native resource, native font, and compiled HTML/CSS caches. Native resource caching includes repeated `data:` URI images; the font-cache budget guides eviction rather than bounding peak memory, and fonts added by the current call or pinned by registration are not evicted for space.
- enforce upstream animation limits of 90 fps for WebP/APNG and 50 fps for GIF.
- retain native Playwright and Takumi static types without eagerly importing optional engines.
- use Python 3.11 built-in exception groups and string enums.
- require Python `>=3.11,<4.0` and Entari `>=0.19.4,<0.20.0`, with release validation across Python 3.11–3.14.
- switch Markdown math to `pymdownx.arithmatex` in generic mode with `smart_dollar=True`; `$x$` and `\(x\)` remain inline, while `$ x $` stays literal and `$$...$$` / `\[...\]` require standalone paragraph or block context for display math.
- mark only parser-generated Arithmatex containers with `data-htmlrender-arithmatex`, inject KaTeX assets for browser rendering, and reject JavaScript-requiring formula documents through the Takumi source boundary.
- raise core dependency floors to AnyIO `>=4.13.0`, Markdown `>=3.11.3`, and PyMdown Extensions `>=12.3`.
- keep `HtmlRenderService` plugin-scoped through Entari DI and Launart stages, including cancellation-safe runtime drain and hosted-resource shutdown.
- keep the 0.2.0 distribution on a framework-neutral boundary: it does not include a NoneBot framework plugin dependency, initialize another host framework, or ship a migration shim for one.
- update the third-party provider example, documentation navigation, provider selection matrix, installation ranges, and versioned-docs examples for the 0.2 release line.

### Fixed

- preserve resource URL fragments and decode local URL paths before authorization, while keeping filehost request headers scoped to the exact fragment-free request URL.
- harden release workflow dispatch ([d224199](https://github.com/entanex/entari-plugin-htmlrender/commit/d2241991fd2428fa259f685d72982428834766a1) by Tacrolimus).
- strengthen distribution metadata and CI contracts for the Python/Entari support matrix and pinned native extras.

### Documentation

- document Takumi 0.4.0's supported wheel platforms, Unicode font subsets, cache and release lifecycles, and animation limits.
- distinguish published Takumi capabilities from the upstream `dev` previews of `Document`, `RasterImage`, and MathJax. This release still uses Playwright for Markdown formulas.
- include named drawings, shared-package imports, and initializer-only packages in the 0.2 migration and service documentation.

<!-- insertion marker -->
## [v0.1.0](https://github.com/entanex/entari-plugin-htmlrender/releases/tag/v0.1.0) - 2026-08-14

<small>[Compare with first commit](https://github.com/entanex/entari-plugin-htmlrender/compare/e1e984747b97aa2126a869d595729720d863ddde...v0.1.0)</small>

### Chore

- inline markdown lint configuration ([8542b67](https://github.com/entanex/entari-plugin-htmlrender/commit/8542b6714d4c73a6a16f8510b30c4fddc0a2e0e1) by Tacrolimus).
- reset package metadata for new repository ([c60dae2](https://github.com/entanex/entari-plugin-htmlrender/commit/c60dae21440eedd7eac642f91dd60ec7c5574058) by Tacrolimus).
- import htmlrender source baseline ([e1e9847](https://github.com/entanex/entari-plugin-htmlrender/commit/e1e984747b97aa2126a869d595729720d863ddde) by BalconyJH).

### Continuous Integration

- consolidate build and release workflows ([38dec35](https://github.com/entanex/entari-plugin-htmlrender/commit/38dec35b4cfce110b4625b41a87dc634578f8dbe) by Tacrolimus).

### Docs

- reorganize guides around public contracts ([f6db727](https://github.com/entanex/entari-plugin-htmlrender/commit/f6db727d15c1c963c90f4cf407df21c37ab1bc3f) by Tacrolimus).

### Bug Fixes

- restore CI compatibility ([dc77635](https://github.com/entanex/entari-plugin-htmlrender/commit/dc7763555a61e844e12d40ec179ce0f28c17989d) by Tacrolimus).
- harden lifecycle and distribution boundaries ([0d78ecf](https://github.com/entanex/entari-plugin-htmlrender/commit/0d78ecf667f7a4ee4610501a7e9ae97a2abb014a) by BalconyJH).

### Code Refactoring

- establish semantic rendering architecture ([d3ba187](https://github.com/entanex/entari-plugin-htmlrender/commit/d3ba187ab6a6e7113d685b177075065c79ba58bf) by Tacrolimus).
- port htmlrender to Entari ([718e644](https://github.com/entanex/entari-plugin-htmlrender/commit/718e644c2c73affccb4e51439da67382a12689c6) by BalconyJH).
