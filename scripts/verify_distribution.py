#!/usr/bin/env python3
"""Verify built distributions and exercise them outside the source tree."""

from __future__ import annotations

import argparse
from base64 import urlsafe_b64encode
import csv
from email import message_from_bytes
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Final
import zipfile

if TYPE_CHECKING:
    from email.message import Message

PACKAGE_NAME: Final = "entari-plugin-htmlrender"
PACKAGE_IMPORT: Final = "entari_plugin_htmlrender"
TAKUMI_VERSION: Final = "0.2.0"
PILLOW_MINIMUM_VERSION: Final = "12.0.0"
SKIA_MINIMUM_VERSION: Final = "144.0.post2"
EXPECTED_EXTRAS: Final = frozenset(
    {
        "all",
        "filehost",
        "pillow",
        "playwright",
        "prometheus",
        "sentry",
        "skia",
        "takumi",
    }
)
OPTIONAL_REQUIREMENTS: Final = {
    "filehost": ("aiohttp>=3.12.0", "py-machineid>=0.8.0"),
    "pillow": (f"pillow>={PILLOW_MINIMUM_VERSION}",),
    "playwright": ("playwright>=1.60.0",),
    "prometheus": ("prometheus-client>=0.20.0",),
    "sentry": ("sentry-sdk>=2.0.0",),
    "skia": (f"skia-python>={SKIA_MINIMUM_VERSION}",),
    "takumi": (f"takumi-py=={TAKUMI_VERSION}",),
}
BASE_REQUIREMENTS: Final = (
    "anyio>=4.12.0",
    "arclet-entari[pydantic]>=0.18.6,<0.19.0",
    "exceptiongroup>=1.3.0",
    "jinja2>=3.0.3",
    "markdown>=3.10.0",
    "pygments>=2.10.0",
    "pymdown-extensions>=11.0",
    "python-markdown-math>=0.8",
    "typing-extensions>=4.15.0",
)
REQUIRES_PYTHON_FORMS: Final = frozenset({">=3.10,<4.0", "<4.0,>=3.10"})
PACKAGE_RESOURCES: Final = (
    "entari_plugin_htmlrender/templates/markdown/github-markdown-light.css",
    "entari_plugin_htmlrender/templates/markdown/markdown.html",
    "entari_plugin_htmlrender/templates/markdown/pygments-default.css",
    "entari_plugin_htmlrender/templates/markdown/katex/katex.min.b64_fonts.css",
    "entari_plugin_htmlrender/templates/markdown/katex/katex.min.js",
    "entari_plugin_htmlrender/templates/markdown/katex/mathtex-script-type.min.js",
    "entari_plugin_htmlrender/templates/markdown/katex/mhchem.min.js",
    "entari_plugin_htmlrender/templates/text/text.css",
    "entari_plugin_htmlrender/templates/text/text.html",
)
FORBIDDEN_ARCHIVE_PATH_PARTS: Final = frozenset(
    {
        ".artifacts",
        ".bzr",
        ".cache",
        ".entari",
        ".git",
        ".hatch",
        ".hg",
        ".idea",
        ".jj",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".svn",
        ".tox",
        ".venv",
        ".vscode",
        "__pycache__",
        "build",
        "dist",
        "htmlcov",
        "site",
    }
)
FORBIDDEN_ARCHIVE_FILES: Final = frozenset({".coverage", ".ds_store"})
FORBIDDEN_ARCHIVE_SUFFIXES: Final = (".pyc", ".pyo")

_BASE_SMOKE = r"""
import asyncio
from importlib.metadata import version
from importlib.resources import files
from importlib.util import find_spec
import json
import os
from pathlib import Path, PurePosixPath

import entari_plugin_htmlrender as htmlrender
from entari_plugin_htmlrender.composition import build_runtime_plan
from entari_plugin_htmlrender.config import HtmlRenderConfig
from entari_plugin_htmlrender.resources import PackageResourceRef

expected_version = os.environ["HTMLRENDER_EXPECTED_VERSION"]
expected_resources = json.loads(os.environ["HTMLRENDER_EXPECTED_RESOURCES"])
repository_root = Path(os.environ["HTMLRENDER_REPOSITORY_ROOT"]).resolve()


def check(condition: object, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


module_path = Path(htmlrender.__file__).resolve()
check(
    not module_path.is_relative_to(repository_root),
    f"Smoke imported the source checkout instead of the installed wheel: {module_path}",
)
check(
    version("entari-plugin-htmlrender") == expected_version,
    "Installed distribution version does not match the built artifact",
)
for optional_module in (
    "PIL",
    "machineid",
    "playwright",
    "prometheus_client",
    "sentry_sdk",
    "skia",
    "takumi_py",
):
    check(
        find_spec(optional_module) is None,
        f"Bare core install unexpectedly contains {optional_module!r}",
    )

package_root = files("entari_plugin_htmlrender")
for resource_name in expected_resources:
    relative = PurePosixPath(resource_name).relative_to("entari_plugin_htmlrender")
    resource = package_root.joinpath(*relative.parts)
    check(resource.is_file(), f"Installed package resource is missing: {resource_name}")
    check(bool(resource.read_bytes()), f"Installed package resource is empty: {resource_name}")

parsed = htmlrender.parse_html("<main><p>wheel smoke</p></main>")
check(parsed.html.startswith("<main>"), "Pure HTML parsing failed")


async def main() -> None:
    template_root = Path(htmlrender.__file__).resolve().parent / "templates" / "text"
    config = HtmlRenderConfig.model_validate(
        {
            "resources": {
                "local_access": {
                    "allowed_paths": [template_root],
                }
            }
        }
    )
    runtime = build_runtime_plan(config).build_runtime()
    await runtime.startup()
    try:
        check(
            runtime.renderer.supported_operations == frozenset(),
            "Core runtime unexpectedly exposes provider-backed raster operations",
        )
        text = await runtime.templates.render(
            htmlrender.TemplateRef(template_root, "text.html"),
            {
                "css": "body { color: #123456; }",
                "text": "wheel <smoke> & Unicode 字符",
            },
        )
        check(
            "wheel &lt;smoke&gt; &amp; Unicode 字符" in text.content,
            "Installed template renderer did not preserve escaping and Unicode",
        )
        stylesheet = await runtime.resources.fetch_text(
            PackageResourceRef(
                "entari_plugin_htmlrender",
                "templates/text/text.css",
            )
        )
        check(".main-box" in stylesheet, "Installed package resource fetch failed")
        check(
            runtime.capabilities.available_names == frozenset(),
            "Core runtime unexpectedly exposes provider-specific capabilities",
        )
    finally:
        await runtime.aclose()


asyncio.run(main())
"""

_ENTARI_PLUGIN_SMOKE = r"""
import os
import sys

from arclet.entari import load_config, load_plugin


def check(condition: object, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


load_config(os.environ["HTMLRENDER_ENTARI_CONFIG"])
plugin = load_plugin("entari_plugin_htmlrender")
check(plugin is not None, "Entari could not load entari_plugin_htmlrender")
check(plugin.id == "entari_plugin_htmlrender", "Entari loaded an unexpected plugin id")
check(not plugin.is_static, "HTMLRender must remain hot-unloadable")
for heavy_module in ("playwright", "skia", "takumi_py"):
    check(heavy_module not in sys.modules, f"Plugin load eagerly imported {heavy_module!r}")
"""

_TAKUMI_SMOKE = r"""
import asyncio
from importlib.metadata import version
import os
import struct

from entari_plugin_htmlrender import RasterOptions
from entari_plugin_htmlrender.composition import build_runtime_plan
from entari_plugin_htmlrender.config import HtmlRenderConfig


def check(condition: object, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


check(
    version("takumi-py") == os.environ["HTMLRENDER_EXPECTED_TAKUMI_VERSION"],
    "Installed takumi-py version does not match the pinned provider",
)


async def main() -> None:
    runtime = build_runtime_plan(
        HtmlRenderConfig.model_validate({"provider": "takumi"})
    ).build_runtime()
    await runtime.startup()
    try:
        capability = runtime.capabilities.takumi
        async with capability.lease_session() as session:
            rendered = await session.render_html(
                '<div style="width:8px;height:4px;background:#ff0000"></div>',
                width=8,
                height=4,
                device_pixel_ratio=1.0,
            )
        check(rendered.startswith(b"\x89PNG\r\n\x1a\n"), "Takumi did not return PNG")
        check(struct.unpack(">II", rendered[16:24]) == (8, 4), "Takumi dimensions differ")
        artifact = await runtime.renderer.rasterize_text(
            "installed Takumi smoke",
            raster=RasterOptions(width=180, device_pixel_ratio=1.0),
        )
        check(bytes(artifact).startswith(b"\x89PNG\r\n\x1a\n"), "Text smoke failed")
        check(artifact.width == 180, "Text smoke returned an unexpected width")
    finally:
        await runtime.aclose()


asyncio.run(main())
"""

_GRAPHICS_SMOKE = r"""
import asyncio

from entari_plugin_htmlrender.composition import build_runtime_plan
from entari_plugin_htmlrender.config import GraphicsSettings, HtmlRenderConfig
from entari_plugin_htmlrender.graphics import (
    FillRect,
    PixelRect,
    RasterScene,
    RGBAColor,
)


def check(condition: object, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


async def main() -> None:
    scene = RasterScene(
        8,
        4,
        commands=(FillRect(PixelRect(1, 1, 3, 2), RGBAColor(255, 0, 0, 128)),),
    )
    for backend in ("pillow", "skia"):
        runtime = build_runtime_plan(
            HtmlRenderConfig(
                graphics=GraphicsSettings(
                    backend=backend,
                    max_pixels=1024,
                    max_concurrency=1,
                )
            )
        ).build_runtime()
        await runtime.startup()
        try:
            artifact = await runtime.graphics.rasterize(scene)
            check(
                bytes(artifact).startswith(b"\x89PNG\r\n\x1a\n"),
                f"{backend} did not return PNG",
            )
            check(artifact.format == "png", f"{backend} returned the wrong format")
            check(
                (artifact.width, artifact.height) == (8, 4),
                f"{backend} raster dimensions differ",
            )
        finally:
            await runtime.aclose()


asyncio.run(main())
"""


class DistributionVerificationError(RuntimeError):
    """A built artifact does not satisfy the release contract."""


def _log(message: str) -> None:
    sys.stdout.write(f"{message}\n")
    sys.stdout.flush()


def _normalize_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _normalize_requirement(requirement: str) -> str:
    return requirement.lower().replace(" ", "").replace('"', "'")


def _canonical_requirement(requirement: str) -> str:
    normalized = _normalize_requirement(requirement)
    requirement_part, separator, marker = normalized.partition(";")
    match = re.fullmatch(r"([a-z0-9_.-]+(?:\[[a-z0-9_,.-]+\])?)(.*)", requirement_part)
    if match is None:
        return normalized
    name, specifier_text = match.groups()
    specifiers = ",".join(sorted(filter(None, specifier_text.split(","))))
    suffix = f";{marker}" if separator else ""
    return f"{name}{specifiers}{suffix}"


def _only_artifact(paths: list[Path], kind: str) -> Path:
    if len(paths) != 1:
        found = ", ".join(sorted(path.name for path in paths)) or "none"
        raise DistributionVerificationError(
            f"Expected exactly one {kind}, found {len(paths)}: {found}."
        )
    return paths[0]


def _read_archive_member(archive: tarfile.TarFile, member: tarfile.TarInfo) -> bytes:
    file = archive.extractfile(member)
    if file is None:
        raise DistributionVerificationError(
            f"Could not read source distribution member {member.name!r}."
        )
    return file.read()


def _validate_archive_paths(names: list[str], *, artifact: Path) -> None:
    forbidden: list[str] = []
    for name in names:
        path = PurePosixPath(name.replace("\\", "/"))
        parts = path.parts
        folded_parts = tuple(part.casefold() for part in parts)
        leaf = folded_parts[-1] if folded_parts else ""
        if (
            path.is_absolute()
            or ".." in parts
            or any(part in FORBIDDEN_ARCHIVE_PATH_PARTS for part in folded_parts)
            or any(part.endswith(".egg-info") for part in folded_parts)
            or leaf in FORBIDDEN_ARCHIVE_FILES
            or leaf.startswith(".coverage.")
            or leaf.endswith(FORBIDDEN_ARCHIVE_SUFFIXES)
        ):
            forbidden.append(name)

    if forbidden:
        sample = ", ".join(repr(name) for name in sorted(forbidden)[:10])
        remainder = len(forbidden) - 10
        suffix = f" (and {remainder} more)" if remainder > 0 else ""
        raise DistributionVerificationError(
            f"{artifact.name} contains forbidden VCS, cache, or build artifacts: "
            f"{sample}{suffix}."
        )


def _validate_metadata(
    metadata: Message,
    *,
    expected_version: str,
    artifact: Path,
) -> None:
    name = metadata.get("Name")
    if name is None or _normalize_distribution_name(name) != PACKAGE_NAME:
        raise DistributionVerificationError(
            f"{artifact.name} has unexpected project name {name!r}."
        )
    if metadata.get("Version") != expected_version:
        raise DistributionVerificationError(
            f"{artifact.name} has unexpected version {metadata.get('Version')!r}."
        )
    requires_python = metadata.get("Requires-Python")
    if (
        requires_python is None
        or requires_python.replace(" ", "") not in REQUIRES_PYTHON_FORMS
    ):
        raise DistributionVerificationError(
            f"{artifact.name} has unexpected Requires-Python {requires_python!r}."
        )

    extras = set(metadata.get_all("Provides-Extra", []))
    if extras != EXPECTED_EXTRAS:
        raise DistributionVerificationError(
            f"{artifact.name} optional extras mismatch: "
            f"missing={sorted(EXPECTED_EXTRAS - extras)}, "
            f"unexpected={sorted(extras - EXPECTED_EXTRAS)}."
        )

    normalized = {
        _canonical_requirement(requirement)
        for requirement in metadata.get_all("Requires-Dist", [])
    }
    missing_base = {
        requirement
        for requirement in map(_canonical_requirement, BASE_REQUIREMENTS)
        if requirement not in normalized
    }
    if missing_base:
        raise DistributionVerificationError(
            f"{artifact.name} base requirements are incomplete: {sorted(missing_base)}."
        )
    expected_optional = {
        _canonical_requirement(f"{requirement};extra=='{extra}'")
        for extra, requirements in OPTIONAL_REQUIREMENTS.items()
        for requirement in requirements
    }
    expected_optional.update(
        _canonical_requirement(f"{requirement};extra=='all'")
        for requirements in OPTIONAL_REQUIREMENTS.values()
        for requirement in requirements
    )
    missing_optional = expected_optional - normalized
    if missing_optional:
        raise DistributionVerificationError(
            f"{artifact.name} optional requirements are incomplete: "
            f"{sorted(missing_optional)}."
        )
    forbidden = sorted(req for req in normalized if "nonebot" in req)
    if forbidden:
        raise DistributionVerificationError(
            f"{artifact.name} still declares NoneBot dependencies: {forbidden}."
        )


def _verify_record_entry(
    path: str,
    data: bytes,
    record: dict[str, tuple[str, str]],
) -> None:
    entry = record.get(path)
    if entry is None:
        raise DistributionVerificationError(f"Wheel RECORD omits {path!r}.")
    digest, size = entry
    expected_digest = "sha256=" + urlsafe_b64encode(
        sha256(data).digest()
    ).decode().rstrip("=")
    if digest != expected_digest or size != str(len(data)):
        raise DistributionVerificationError(f"Wheel RECORD mismatch for {path!r}.")


def _verify_wheel(wheel: Path, *, expected_version: str) -> dict[str, bytes]:
    with zipfile.ZipFile(wheel) as archive:
        corrupt = archive.testzip()
        if corrupt is not None:
            raise DistributionVerificationError(
                f"Wheel member is corrupt: {corrupt!r}."
            )
        names = archive.namelist()
        _validate_archive_paths(names, artifact=wheel)
        metadata_path = _only_artifact(
            [Path(name) for name in names if name.endswith(".dist-info/METADATA")],
            "wheel METADATA file",
        ).as_posix()
        record_path = _only_artifact(
            [Path(name) for name in names if name.endswith(".dist-info/RECORD")],
            "wheel RECORD file",
        ).as_posix()
        _validate_metadata(
            message_from_bytes(archive.read(metadata_path)),
            expected_version=expected_version,
            artifact=wheel,
        )
        record_rows = csv.reader(archive.read(record_path).decode().splitlines())
        record = {row[0]: (row[1], row[2]) for row in record_rows if len(row) == 3}
        packaged = {
            name
            for name in names
            if name.startswith(f"{PACKAGE_IMPORT}/templates/")
            and not name.endswith("/")
        }
        expected = set(PACKAGE_RESOURCES)
        if packaged != expected:
            raise DistributionVerificationError(
                f"Wheel resource mismatch: missing={sorted(expected - packaged)}, "
                f"unexpected={sorted(packaged - expected)}."
            )
        resources: dict[str, bytes] = {}
        for name in PACKAGE_RESOURCES:
            data = archive.read(name)
            if not data:
                raise DistributionVerificationError(f"Wheel resource is empty: {name}.")
            _verify_record_entry(name, data, record)
            resources[name] = data
        return resources


def _verify_sdist(
    sdist: Path,
    *,
    expected_version: str,
    wheel_resources: dict[str, bytes],
) -> None:
    with tarfile.open(sdist, mode="r:gz") as archive:
        members = archive.getmembers()
        _validate_archive_paths(
            [member.name for member in members],
            artifact=sdist,
        )
        metadata_member = _only_artifact(
            [
                Path(member.name)
                for member in members
                if member.name.endswith("/PKG-INFO")
            ],
            "source distribution PKG-INFO file",
        ).as_posix()
        _validate_metadata(
            message_from_bytes(
                _read_archive_member(archive, archive.getmember(metadata_member))
            ),
            expected_version=expected_version,
            artifact=sdist,
        )
        for resource_name, wheel_data in wheel_resources.items():
            matches = [
                member
                for member in members
                if member.isfile() and member.name.endswith(f"/{resource_name}")
            ]
            if len(matches) != 1:
                raise DistributionVerificationError(
                    f"Source distribution expected one {resource_name!r}, found {len(matches)}."
                )
            if _read_archive_member(archive, matches[0]) != wheel_data:
                raise DistributionVerificationError(
                    f"Wheel and source distribution disagree for {resource_name!r}."
                )


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python3")


def _run(command: list[str], *, cwd: Path, env: dict[str, str], label: str) -> None:
    _log(f"==> {label}")
    try:
        subprocess.run(command, cwd=cwd, env=env, check=True)  # noqa: S603
    except subprocess.CalledProcessError as error:
        raise DistributionVerificationError(
            f"{label} failed with exit code {error.returncode}."
        ) from error


def _create_venv(
    root: Path,
    *,
    name: str,
    python_version: str,
    uv: str,
    env: dict[str, str],
) -> tuple[Path, Path]:
    venv = root / name
    run_dir = root / f"{name}-run"
    run_dir.mkdir()
    _run(
        [uv, "venv", "--python", python_version, str(venv)],
        cwd=run_dir,
        env=env,
        label=f"Create isolated {name} environment",
    )
    return _venv_python(venv), run_dir


def _install(
    python: Path,
    artifact: str,
    *,
    uv: str,
    cwd: Path,
    env: dict[str, str],
    label: str,
) -> None:
    _run(
        [uv, "pip", "install", "--python", str(python), artifact],
        cwd=cwd,
        env=env,
        label=label,
    )


def _run_install_smokes(
    wheel: Path,
    sdist: Path,
    *,
    expected_version: str,
    python_version: str,
    uv: str,
    repository_root: Path,
    smoke_sdist: bool,
) -> None:
    with TemporaryDirectory(prefix="htmlrender-dist-smoke-") as temporary:
        root = Path(temporary).resolve()
        env = os.environ.copy()
        for inherited in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
            env.pop(inherited, None)
        env.update(
            {
                "HOME": str(root / "home"),
                "HTMLRENDER_ENTARI_CONFIG": str(root / "missing-entari.yml"),
                "HTMLRENDER_EXPECTED_RESOURCES": json.dumps(PACKAGE_RESOURCES),
                "HTMLRENDER_EXPECTED_TAKUMI_VERSION": TAKUMI_VERSION,
                "HTMLRENDER_EXPECTED_VERSION": expected_version,
                "HTMLRENDER_REPOSITORY_ROOT": str(repository_root),
                "PYTHONNOUSERSITE": "1",
                "UV_NO_PROGRESS": "1",
                "XDG_CACHE_HOME": str(root / "xdg-cache"),
                "XDG_CONFIG_HOME": str(root / "xdg-config"),
                "XDG_DATA_HOME": str(root / "xdg-data"),
            }
        )

        wheel_python, wheel_run = _create_venv(
            root,
            name="wheel",
            python_version=python_version,
            uv=uv,
            env=env,
        )
        _install(
            wheel_python,
            str(wheel.resolve()),
            uv=uv,
            cwd=wheel_run,
            env=env,
            label="Install wheel core",
        )
        for label, smoke in (
            ("Run installed-wheel core smoke", _BASE_SMOKE),
            ("Run installed-wheel Entari plugin-load smoke", _ENTARI_PLUGIN_SMOKE),
        ):
            _run([str(wheel_python), "-c", smoke], cwd=wheel_run, env=env, label=label)

        _install(
            wheel_python,
            f"{wheel.resolve()}[takumi]",
            uv=uv,
            cwd=wheel_run,
            env=env,
            label="Install wheel Takumi extra",
        )
        _run(
            [str(wheel_python), "-c", _TAKUMI_SMOKE],
            cwd=wheel_run,
            env=env,
            label="Run installed-wheel Takumi smoke",
        )
        _install(
            wheel_python,
            f"{wheel.resolve()}[pillow,skia]",
            uv=uv,
            cwd=wheel_run,
            env=env,
            label="Install wheel graphics extras",
        )
        _run(
            [str(wheel_python), "-c", _GRAPHICS_SMOKE],
            cwd=wheel_run,
            env=env,
            label="Run installed-wheel graphics smoke",
        )

        if not smoke_sdist:
            return
        sdist_python, sdist_run = _create_venv(
            root,
            name="sdist",
            python_version=python_version,
            uv=uv,
            env=env,
        )
        _install(
            sdist_python,
            str(sdist.resolve()),
            uv=uv,
            cwd=sdist_run,
            env=env,
            label="Build and install source distribution",
        )
        for label, smoke in (
            ("Run installed-sdist core smoke", _BASE_SMOKE),
            ("Run installed-sdist Entari plugin-load smoke", _ENTARI_PLUGIN_SMOKE),
        ):
            _run([str(sdist_python), "-c", smoke], cwd=sdist_run, env=env, label=label)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist_dir", nargs="?", default=Path("dist"), type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--python", default="3.12")
    parser.add_argument("--uv", default=os.environ.get("UV", "uv"))
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--wheel-only-smoke", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    dist_dir = args.dist_dir.expanduser().resolve()
    if not dist_dir.is_dir():
        raise DistributionVerificationError(
            f"Distribution directory does not exist: {dist_dir}."
        )
    wheel = _only_artifact(list(dist_dir.glob("*.whl")), "wheel")
    sdist = _only_artifact(list(dist_dir.glob("*.tar.gz")), "source distribution")
    _log(f"==> Verify archive metadata and package resources in {dist_dir}")
    wheel_resources = _verify_wheel(wheel, expected_version=args.expected_version)
    _verify_sdist(
        sdist,
        expected_version=args.expected_version,
        wheel_resources=wheel_resources,
    )
    if not args.metadata_only:
        _run_install_smokes(
            wheel,
            sdist,
            expected_version=args.expected_version,
            python_version=args.python,
            uv=args.uv,
            repository_root=Path(__file__).resolve().parents[1],
            smoke_sdist=not args.wheel_only_smoke,
        )
    _log("Distribution verification passed.")


if __name__ == "__main__":
    try:
        main()
    except DistributionVerificationError as error:
        sys.stderr.write(f"Distribution verification failed: {error}\n")
        raise SystemExit(1) from None
