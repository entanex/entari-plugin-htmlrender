"""Real Chromium verification of the complete caller-to-provider pipeline."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
import threading
from typing import TYPE_CHECKING, ClassVar, Iterator

from PIL import Image
import pytest

from entari_plugin_htmlrender import RasterOptions, TemplateRef
from entari_plugin_htmlrender.composition import build_runtime_plan
from entari_plugin_htmlrender.config import HtmlRenderConfig
from entari_plugin_htmlrender.errors import (
    ResourceAccessDeniedError,
    RuntimeUnavailableError,
)

if TYPE_CHECKING:
    from playwright.async_api import ConsoleMessage
    from playwright.async_api import Error as PlaywrightError

    from entari_plugin_htmlrender.runtime import RenderRuntime

pytestmark = pytest.mark.requires_browser
_BROWSERS = Path(__file__).resolve().parents[3] / ".artifacts" / "playwright-browsers"
_PIXEL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c6360f8cf0000000500019d6cbc960000000049454e"
    "44ae426082"
)
_MATH_MARKDOWN = r"""
# Browser math

Inline dollar $e^{i\pi} + 1 = 0$ and round \(x^2 + y^2\).

$$
\int_0^1 x^2\,dx = \frac{1}{3}
$$

\[
\ce{2H2 + O2 -> 2H2O}
\]

```latex
$literal inline$
$$
\ce{not chemistry}
$$
```

Escaped \$5 and \$10, plus `$literal code$`.

Invalid $\unknowncommand{bad}$ remains plain text.

<span class="arithmatex" id="raw-arithmatex">not generated math</span>
"""


class _NetworkHandler(BaseHTTPRequestHandler):
    requests: ClassVar[list[str]] = []
    user_agents: ClassVar[list[str | None]] = []

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        del format, args

    def do_GET(self) -> None:
        self.requests.append(self.path)
        self.user_agents.append(self.headers.get("User-Agent"))
        if self.path == "/style.css":
            self.send_response(302)
            self.send_header("Location", "/assets/style.css")
            self.end_headers()
        elif self.path == "/assets/style.css":
            body = b"html { background-image: url('pixel.png') }"
            self.send_response(200)
            self.send_header("Content-Type", "text/css")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/assets/pixel.png":
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(_PIXEL_PNG)))
            self.end_headers()
            self.wfile.write(_PIXEL_PNG)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        self.requests.append(self.path)
        self.send_response(204)
        self.end_headers()


@pytest.fixture
def network_server() -> Iterator[str]:
    _NetworkHandler.requests = []
    _NetworkHandler.user_agents = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _NetworkHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _managed_runtime(
    *,
    allow_loopback: bool,
) -> RenderRuntime:
    private_networks = ["127.0.0.0/8"] if allow_loopback else []
    return build_runtime_plan(
        HtmlRenderConfig.model_validate(
            {
                "provider": "playwright",
                "provider_config": {
                    "storage_path": _BROWSERS,
                    "skip_browser_install": True,
                    "materialization_policy": "off",
                },
                "resources": {
                    "remote_access": {
                        "allow_private_networks": private_networks,
                    }
                },
            }
        )
    ).build_runtime()


async def test_managed_chromium_enforces_loopback_allowlist_and_redirect_base(
    network_server: str,
) -> None:
    raster = RasterOptions(width=32, height=32, device_pixel_ratio=1.0)
    denied = _managed_runtime(allow_loopback=False)
    try:
        await denied.startup()
        with pytest.raises(ResourceAccessDeniedError):
            await denied.renderer.rasterize_html(
                f'<img src="{network_server}/assets/pixel.png">',
                raster=raster,
            )
        assert _NetworkHandler.requests == []
        assert _NetworkHandler.user_agents == []

        with pytest.raises(ResourceAccessDeniedError):
            await denied.renderer.rasterize_html(
                f'<script>window.open("{network_server}/assets/pixel.png")</script>',
                raster=raster,
            )
        assert _NetworkHandler.requests == []
        assert _NetworkHandler.user_agents == []
    finally:
        await denied.aclose()

    allowed = _managed_runtime(allow_loopback=True)
    try:
        await allowed.startup()
        image = await allowed.renderer.rasterize_html(
            f'<link rel="stylesheet" href="{network_server}/style.css">',
            raster=raster,
        )
        assert image.format == "png"
        assert _NetworkHandler.requests[0] == "/style.css"
        assert "/assets/style.css" in _NetworkHandler.requests
        assert _NetworkHandler.requests[-1] == "/assets/pixel.png"
        assert _NetworkHandler.user_agents
        assert all(user_agent is None for user_agent in _NetworkHandler.user_agents)
    finally:
        await allowed.aclose()


async def test_chromium_renders_preparation_and_customized_templates(
    tmp_path: Path,
) -> None:
    template = TemplateRef(tmp_path, "card.html")
    (tmp_path / "card.html").write_text(
        "<style>body {margin:0;background:#123456;color:white}</style>"
        "{% set titles = [] %}{% do titles.append(title | badge) %}"
        "<h1>{{ titles[0] }}</h1>",
        encoding="utf-8",
    )
    runtime = build_runtime_plan(
        HtmlRenderConfig.model_validate(
            {
                "provider": "playwright",
                "provider_config": {
                    "storage_path": _BROWSERS,
                    "skip_browser_install": True,
                },
                "resources": {"local_access": {"allowed_paths": [tmp_path]}},
            }
        )
    ).build_runtime()
    raster = RasterOptions(width=160, height=80, device_pixel_ratio=1.0)
    try:
        await runtime.startup()
        prepared = await runtime.preparation.prepare_markdown("# Prepared")
        images = [
            await runtime.renderer.rasterize_html("<b>HTML</b>", raster=raster),
            await runtime.renderer.rasterize_text("Text <escaped>", raster=raster),
            await runtime.renderer.rasterize_prepared(prepared, raster=raster),
        ]
        for image in images:
            assert image.format == "png"
            assert (image.width, image.height) == (160, 80)

        card = await runtime.renderer.rasterize_template(
            template,
            {"title": "Entari"},
            filters={"badge": str.upper},
            extensions=("jinja2.ext.do",),
            raster=raster,
        )
        with Image.open(BytesIO(bytes(card))) as image:
            assert image.size == (160, 80)
            assert image.convert("RGB").getpixel((159, 79)) == (18, 52, 86)

        async with runtime.capabilities.playwright.lease_page() as page:
            await page.set_content("<main>native lease</main>")
            assert await page.locator("main").inner_text() == "native lease"
        assert page.is_closed()
    finally:
        await runtime.aclose()

    with pytest.raises(RuntimeUnavailableError):
        async with runtime.capabilities.playwright.lease_page():
            pytest.fail("closed runtime issued a page")


async def test_chromium_renders_markdown_math_end_to_end() -> None:
    runtime = build_runtime_plan(
        HtmlRenderConfig.model_validate(
            {
                "provider": "playwright",
                "provider_config": {
                    "storage_path": _BROWSERS,
                    "skip_browser_install": True,
                },
            }
        )
    ).build_runtime()
    script_errors: list[str] = []

    def record_page_error(error: PlaywrightError) -> None:
        script_errors.append(str(error))

    def record_console_error(message: ConsoleMessage) -> None:
        if message.type == "error":
            script_errors.append(message.text)

    try:
        await runtime.startup()
        prepared = await runtime.preparation.prepare_markdown(_MATH_MARKDOWN)

        async with runtime.capabilities.playwright.lease_page() as page:
            page.on("pageerror", record_page_error)
            page.on("console", record_console_error)
            await page.set_content(prepared.html, wait_until="networkidle")
            await page.wait_for_function(
                "() => document.querySelectorAll('.arithmatex .katex').length === 4",
                timeout=10_000,
            )

            generated = page.locator(".arithmatex[data-htmlrender-arithmatex]")
            assert await page.locator(".arithmatex").count() == 6
            assert await generated.count() == 5
            assert (
                await page.locator(
                    "span.arithmatex[data-htmlrender-arithmatex]"
                ).count()
                == 3
            )
            assert (
                await page.locator("div.arithmatex[data-htmlrender-arithmatex]").count()
                == 2
            )
            assert await page.locator(".arithmatex .katex").count() == 4
            assert await page.locator(".arithmatex .katex-display").count() == 2
            assert await page.locator(".katex-error").count() == 0

            annotations = await page.locator(
                '.arithmatex annotation[encoding="application/x-tex"]'
            ).all_text_contents()
            assert len(annotations) == 4
            assert any("e^{i\\pi} + 1 = 0" in text for text in annotations)
            assert any("x^2 + y^2" in text for text in annotations)
            assert any(r"\frac{1}{3}" in text for text in annotations)
            assert any(r"\ce{2H2 + O2 -> 2H2O}" in text for text in annotations)

            mhchem_mathml = (
                await page.locator("div.arithmatex")
                .nth(1)
                .locator(".katex-mathml")
                .text_content()
            )
            assert mhchem_mathml is not None
            assert "H" in mhchem_mathml
            assert "O" in mhchem_mathml

            latex_code = await page.locator(".codehilite code").text_content()
            assert latex_code is not None
            assert "$literal inline$" in latex_code
            assert r"\ce{not chemistry}" in latex_code
            assert (
                await page.locator(
                    ".codehilite code .arithmatex[data-htmlrender-arithmatex]"
                ).count()
                == 0
            )

            escaped = page.locator("p").filter(has_text="Escaped $5 and $10")
            assert await escaped.count() == 1
            assert await escaped.locator(".arithmatex").count() == 0
            assert await escaped.locator("code").text_content() == "$literal code$"

            invalid = page.locator(
                "span.arithmatex[data-htmlrender-arithmatex]"
            ).filter(has_text=r"\unknowncommand{bad}")
            assert await invalid.count() == 1
            assert await invalid.locator(".katex").count() == 0
            assert await invalid.text_content() == r"\unknowncommand{bad}"

            raw = page.locator("#raw-arithmatex")
            assert await raw.get_attribute("data-htmlrender-arithmatex") is None
            assert await raw.locator(".katex").count() == 0
            assert await raw.text_content() == "not generated math"
            assert script_errors == []

        image = await runtime.renderer.rasterize_markdown(
            _MATH_MARKDOWN,
            raster=RasterOptions(
                width=720,
                height=900,
                device_pixel_ratio=1.0,
            ),
        )
        assert image.format == "png"
        payload = bytes(image)
        assert payload.startswith(b"\x89PNG\r\n\x1a\n")
        with Image.open(BytesIO(payload)) as rendered:
            assert rendered.size == (720, 900)
            assert rendered.convert("RGB").getextrema() != ((255, 255),) * 3
    finally:
        await runtime.aclose()
