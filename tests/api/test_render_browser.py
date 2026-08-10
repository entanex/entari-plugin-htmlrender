from __future__ import annotations

from pathlib import Path

from entari_plugin_htmlrender.preparation import TemplateRef
from entari_plugin_htmlrender.resources.models import (
    FileResourceRef,
    PackageResourceRef,
    RemoteResourceRef,
)


def test_caller_sources_are_explicit_value_objects() -> None:
    template = TemplateRef(Path("templates"), "cards/profile.html")
    local = FileResourceRef(Path.cwd() / "styles/theme.css")
    package = PackageResourceRef("example_assets", "styles/theme.css")
    remote = RemoteResourceRef("https://assets.example/theme.css")

    assert template.name == "cards/profile.html"
    assert local.path.is_absolute()
    assert package.name == "styles/theme.css"
    assert remote.url.startswith("https://")
