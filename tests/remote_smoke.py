from __future__ import annotations

import asyncio
from base64 import b64decode
from io import BytesIO
import os
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, cast
from urllib.error import HTTPError
from urllib.request import urlopen

from PIL import Image, ImageChops, ImageStat

from entari_plugin_htmlrender import (
    RasterOptions,
    ResourceMaterializationPolicy,
    TemplateRef,
)
from entari_plugin_htmlrender.composition import build_runtime_plan
from entari_plugin_htmlrender.config import HtmlRenderConfig
from entari_plugin_htmlrender.resources import FileResourceRef

if TYPE_CHECKING:
    from collections.abc import Iterable

    from entari_plugin_htmlrender.adapters.resources import HostedAssetHttpServer

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_TEMPLATE_DIR = _PROJECT_ROOT / "tests" / "templates"
_IMAGE_FILE = _PROJECT_ROOT / "tests" / "resources" / "test_template_filter.png"
_KATEX_FONT_CSS = (
    _PROJECT_ROOT
    / "src"
    / "entari_plugin_htmlrender"
    / "templates"
    / "markdown"
    / "katex"
    / "katex.min.b64_fonts.css"
)
_ARTIFACT_DIR = _PROJECT_ROOT / "tests" / ".artifacts"
_FONT_DATA_RE = re.compile(r"data:font/woff2;base64,([^\")]+)")
_MARKDOWN_SENTINEL = (17, 199, 83)
_FILEHOST_BIND_HOST = "0.0.0.0"  # noqa: S104 - cross-container smoke server
_FILEHOST_BIND_PORT = int(os.environ.get("FILEHOST_BIND_PORT", "9012"))
_FILEHOST_PUBLIC_URL = os.environ.get(
    "FILEHOST_PUBLIC_URL",
    f"http://render:{_FILEHOST_BIND_PORT}/_htmlrender/assets/",
)
_FILEHOST_REQUEST_HEADER = "X-HTMLRender-Filehost-Request"
_FILEHOST_REQUEST_TOKEN = "remote-smoke-filehost-token"


def _remote_resource_policy() -> str:
    policy = os.environ.get("REMOTE_RESOURCE_POLICY", "memory").strip().lower()
    if policy not in {"filehost", "memory"}:
        raise RuntimeError(f"Unsupported remote resource policy: {policy!r}")
    return policy


def _playwright_config(policy: str) -> dict[str, object]:
    ws_endpoint = os.environ.get(
        "PLAYWRIGHT_WS_ENDPOINT", "ws://playwright:53333/playwright"
    )
    return {
        "engine": "chromium",
        "connect_ws": {"endpoint": ws_endpoint},
        "skip_browser_install": True,
        "remote_local_resource_policy": policy,
    }


def _mean_abs_diff(rendered: Image.Image, expected: Image.Image) -> float:
    rendered_rgb = rendered.convert("RGB")
    expected_rgb = expected.convert("RGB")
    if rendered_rgb.size != expected_rgb.size:
        expected_rgb = expected_rgb.resize(rendered_rgb.size)

    diff = ImageChops.difference(rendered_rgb, expected_rgb)
    stat = ImageStat.Stat(diff)
    return sum(stat.mean) / len(stat.mean)


def _assert_png(payload: bytes, *, label: str) -> Image.Image:
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError(f"{label} did not produce PNG output")
    image = Image.open(BytesIO(payload))
    image.load()
    if image.width <= 0 or image.height <= 0:
        raise RuntimeError(f"{label} produced an empty image")
    return image


def _assert_color_coverage(
    image: Image.Image,
    *,
    label: str,
    expected: tuple[int, int, int],
    minimum_pixels: int,
    tolerance: int = 3,
) -> int:
    pixels = cast(
        "Iterable[tuple[int, int, int]]",
        image.convert("RGB").get_flattened_data(),
    )
    matching = sum(
        1
        for pixel in pixels
        if all(
            abs(actual - target) <= tolerance
            for actual, target in zip(pixel, expected, strict=True)
        )
    )
    if matching < minimum_pixels:
        raise RuntimeError(
            f"{label} did not load its sentinel asset: "
            f"expected at least {minimum_pixels} matching pixels, got {matching}"
        )
    return matching


def _prepare_local_fixtures(root: Path) -> tuple[Path, Path]:
    relative_image = root / "relative.png"
    background_image = root / "background.png"
    markdown_image = root / "markdown-relative.png"
    shutil.copyfile(_IMAGE_FILE, relative_image)
    shutil.copyfile(_IMAGE_FILE, background_image)
    Image.new("RGB", (320, 180), _MARKDOWN_SENTINEL).save(markdown_image)
    shutil.copyfile(
        _TEMPLATE_DIR / "remote_filehost.html.jinja2",
        root / "remote_filehost.html.jinja2",
    )

    font_match = _FONT_DATA_RE.search(_KATEX_FONT_CSS.read_text(encoding="utf-8"))
    if font_match is None:
        raise RuntimeError("Could not locate an embedded WOFF2 fixture")
    (root / "smoke.woff2").write_bytes(b64decode(font_match.group(1)))

    markdown = root / "document.md"
    markdown.write_text(
        "![remote relative image](markdown-relative.png)",
        encoding="utf-8",
    )
    stylesheet = root / "text.css"
    stylesheet.write_text(
        """
        @font-face {
            font-family: "RemoteSmoke";
            src: url("smoke.woff2") format("woff2");
        }
        html, body {
            margin: 0;
            min-height: 600px;
        }
        .main-box {
            box-sizing: border-box;
            min-height: 600px;
            padding: 32px;
            color: white;
            background: #111 url("background.png") center / cover no-repeat;
            font-family: "RemoteSmoke", sans-serif;
        }
        """,
        encoding="utf-8",
    )
    return markdown, stylesheet


def _http_status(url: str) -> int:
    try:
        with urlopen(url, timeout=5) as response:  # noqa: S310 - local smoke server
            return response.status
    except HTTPError as error:
        return error.code


async def _assert_filehost_assets(server: HostedAssetHttpServer) -> int:
    entries = tuple(server.store._entries.values())
    if not entries:
        raise RuntimeError("Remote rendering did not publish any filehost assets")
    invalid_guards = [
        asset.name
        for asset in entries
        if asset.headers.get(_FILEHOST_REQUEST_HEADER) != _FILEHOST_REQUEST_TOKEN
    ]
    if invalid_guards:
        raise RuntimeError(f"Invalid filehost guards: {invalid_guards!r}")

    suffixes = {Path(asset.name).suffix.lower() for asset in entries}
    missing = {".css", ".png", ".woff2"} - suffixes
    if missing:
        raise RuntimeError(
            f"Remote rendering did not publish required filehost asset types: {missing}"
        )

    first = entries[0]
    status = await asyncio.to_thread(
        _http_status,
        f"http://127.0.0.1:{_FILEHOST_BIND_PORT}/_htmlrender/assets/"
        f"{first.namespace}/{first.name}",
    )
    if status != 403:
        raise RuntimeError(
            f"Unauthenticated filehost request returned {status}, expected 403"
        )
    return len(entries)


async def _main() -> None:
    policy = _remote_resource_policy()
    with TemporaryDirectory(prefix=f"htmlrender-{policy}-smoke-") as temporary:
        fixture_root = Path(temporary)
        markdown_path, stylesheet_path = _prepare_local_fixtures(fixture_root)
        config = HtmlRenderConfig.model_validate(
            {
                "provider": "playwright",
                "startup": "off",
                "provider_config": _playwright_config(policy),
                "resources": {
                    "local_access": {"allowed_paths": [str(fixture_root)]},
                    "filehost": {
                        "bind_host": _FILEHOST_BIND_HOST,
                        "bind_port": _FILEHOST_BIND_PORT,
                        "public_base_url": _FILEHOST_PUBLIC_URL,
                        "request_header_name": _FILEHOST_REQUEST_HEADER,
                        "request_header_value": _FILEHOST_REQUEST_TOKEN,
                    },
                },
            }
        )
        plan = build_runtime_plan(config)
        runtime = plan.build_runtime()
        filehost_server = plan.hosted_asset_server

        _ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        if filehost_server is not None:
            await filehost_server.startup()
        filehost_assets = 0
        try:
            await runtime.startup()
            html_artifact = await runtime.renderer.rasterize_html(
                "<html><body><h1>remote smoke</h1></body></html>",
                raster=RasterOptions(device_pixel_ratio=1.0),
            )
            html_bytes = bytes(html_artifact)
            _assert_png(html_bytes, label="plain HTML")

            asset_graph_bytes = bytes(
                await runtime.renderer.rasterize_html(
                    """
                    <html>
                      <head><link rel="stylesheet" href="text.css" /></head>
                      <body><div class="main-box">remote asset graph</div></body>
                    </html>
                    """,
                    base_url=f"{fixture_root.as_uri().rstrip('/')}/",
                    raster=RasterOptions(
                        width=1200,
                        height=600,
                        device_pixel_ratio=1.0,
                    ),
                    materialization_policy=ResourceMaterializationPolicy.STRICT,
                )
            )
            _assert_png(asset_graph_bytes, label="linked CSS asset graph")
            (_ARTIFACT_DIR / f"remote_{policy}_asset_graph.png").write_bytes(
                asset_graph_bytes
            )

            text_bytes = bytes(
                await runtime.renderer.rasterize_text(
                    "remote font and background smoke",
                    stylesheet=FileResourceRef(stylesheet_path),
                    raster=RasterOptions(width=1200, device_pixel_ratio=1.0),
                )
            )
            _assert_png(text_bytes, label="text CSS assets")
            (_ARTIFACT_DIR / f"remote_{policy}_text.png").write_bytes(text_bytes)

            markdown_bytes = bytes(
                await runtime.renderer.rasterize_markdown(
                    FileResourceRef(markdown_path),
                    raster=RasterOptions(width=1200, device_pixel_ratio=1.0),
                )
            )
            markdown_rendered = _assert_png(
                markdown_bytes,
                label="Markdown relative image",
            )
            markdown_pixels = _assert_color_coverage(
                markdown_rendered,
                label="Markdown relative image",
                expected=_MARKDOWN_SENTINEL,
                minimum_pixels=10_000,
            )
            (_ARTIFACT_DIR / f"remote_{policy}_markdown.png").write_bytes(
                markdown_bytes
            )

            template_bytes = bytes(
                await runtime.renderer.rasterize_template(
                    TemplateRef(fixture_root, "remote_filehost.html.jinja2"),
                    {
                        "title": "remote template resource smoke",
                        "avatar": Path("relative.png"),
                    },
                    raster=RasterOptions(
                        width=1200,
                        height=600,
                        device_pixel_ratio=1.0,
                    ),
                    materialization_policy=ResourceMaterializationPolicy.STRICT,
                )
            )
            (_ARTIFACT_DIR / f"remote_{policy}_template.png").write_bytes(
                template_bytes
            )

            rendered = _assert_png(template_bytes, label="template relative image")
            expected = Image.open(_IMAGE_FILE)
            diff_score = _mean_abs_diff(rendered, expected)
            if diff_score > 8.0:
                raise RuntimeError(
                    f"Rendered template differs too much from fixture: {diff_score:.2f}"
                )

            if policy == "filehost":
                if filehost_server is None:
                    raise RuntimeError("filehost policy did not compose its server")
                filehost_assets = await _assert_filehost_assets(filehost_server)

            print(  # noqa: T201
                f"remote {policy.upper()} smoke passed: "
                f"html={len(html_bytes)}, asset_graph={len(asset_graph_bytes)}, "
                f"text={len(text_bytes)}, "
                f"markdown={len(markdown_bytes)}, template={len(template_bytes)}, "
                f"markdown_pixels={markdown_pixels}, "
                f"template_diff={diff_score:.2f}, filehost_assets={filehost_assets}"
            )
        finally:
            try:
                await runtime.aclose()
            finally:
                if filehost_server is not None:
                    await filehost_server.aclose()


if __name__ == "__main__":
    asyncio.run(_main())
