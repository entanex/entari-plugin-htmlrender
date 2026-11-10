"""Real Chromium verification of the complete caller-to-provider pipeline."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
import pytest

from entari_plugin_htmlrender import RasterOptions, TemplateRef
from entari_plugin_htmlrender.composition import build_runtime_plan
from entari_plugin_htmlrender.config import HtmlRenderConfig
from entari_plugin_htmlrender.errors import RuntimeUnavailableError

if TYPE_CHECKING:
    from playwright.async_api import ConsoleMessage
    from playwright.async_api import Error as PlaywrightError

pytestmark = pytest.mark.requires_browser
_BROWSERS = Path(__file__).resolve().parents[3] / ".artifacts" / "playwright-browsers"
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
